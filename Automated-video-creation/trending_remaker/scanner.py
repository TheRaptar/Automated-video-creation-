"""
High-Velocity Viral Trend Scanner for the Trending-Topic Auto-Remaker.

Sources (100% official & public-safe — zero unauthorized video scraping):
  1. Official YouTube Data API v3:
     - `videos?chart=mostPopular` across target regions (e.g. IN, US)
     - `search?order=viewCount` for niche/keyword high-velocity videos
  2. Zero-key Public Fallback:
     - Reuses existing read-only `trends.google_trends` (IN/US) & `trends.wikipedia_top`
     - Public Reddit hot JSON (optional best-effort, fail-soft)

Computes a composite `viral_score` from views/hour velocity, engagement ratio,
and recency, then deduplicates against existing `history.json` (read-only) and
`trending_remaker_history.json`.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import requests

PARENT_DIR = Path(__file__).resolve().parent.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

USER_AGENT = "RaptarTrendingRemaker/1.0 (+https://github.com/TheRaptar/Automated-video-creation-)"
YT_API_BASE = "https://www.googleapis.com/youtube/v3"

# Standard YouTube Data API v3 category IDs for optional niche filtering
YOUTUBE_CATEGORY_IDS: Dict[str, str] = {
    "film": "1",
    "autos": "2",
    "music": "10",
    "pets": "15",
    "sports": "17",
    "gaming": "20",
    "people": "22",
    "comedy": "23",
    "entertainment": "24",
    "news": "25",
    "howto": "26",
    "education": "27",
    "science": "28",
    "tech": "28",
}


@dataclass
class ViralSignal:
    signal_id: str
    source: str                      # youtube_most_popular | youtube_niche_search | google_trends | wikipedia_top
    title: str
    channel_or_origin: str = ""
    region: str = "US"
    category: str = ""
    source_url: str = ""
    published_at: str = ""
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    duration_sec: int = 0
    is_short_form: bool = True
    views_per_hour: float = 0.0
    engagement_rate: float = 0.0
    viral_score: float = 0.0
    tags: List[str] = field(default_factory=list)
    summary_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _parse_iso8601_duration(iso: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", str(iso or ""))
    if not m:
        return 0
    h, mn, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mn * 60 + s


def _hours_since(published_at: str) -> float:
    if not published_at:
        return 24.0
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
        return max(1.0, delta_h)
    except Exception:
        return 24.0


def compute_viral_score(
    view_count: int,
    like_count: int = 0,
    comment_count: int = 0,
    published_at: str = "",
    is_short_form: bool = True,
) -> Dict[str, float]:
    """
    Ranks videos by log-scaled view velocity (views/hour), engagement ratio,
    and recency bonus so breakout trends outrank stale legacy uploads.
    """
    hours = _hours_since(published_at)
    vph = float(view_count) / hours
    eng = float(like_count + comment_count * 3) / float(max(view_count, 1))
    recency_boost = 1.25 if hours <= 48 else (1.10 if hours <= 168 else 0.90)
    short_bonus = 1.08 if is_short_form else 1.0
    velocity_pts = math.log10(max(vph, 1.0) + 1.0) * 20.0
    engagement_pts = min(eng * 250.0, 25.0)
    score = round((velocity_pts + engagement_pts) * recency_boost * short_bonus, 2)
    return {
        "views_per_hour": round(vph, 1),
        "engagement_rate": round(eng, 4),
        "viral_score": score,
    }


def _parse_yt_video_items(
    items: List[Dict[str, Any]],
    source: str,
    region: str,
    category_label: str = "",
) -> List[ViralSignal]:
    signals: List[ViralSignal] = []
    for it in items:
        vid = str(it.get("id") or "")
        if isinstance(vid, dict):
            vid = str(vid.get("videoId") or "")
        snip = it.get("snippet") or {}
        stats = it.get("statistics") or {}
        cdet = it.get("contentDetails") or {}

        title = str(snip.get("title") or "").strip()
        if not title:
            continue
        views = int(stats.get("viewCount") or 0)
        likes = int(stats.get("likeCount") or 0)
        comments = int(stats.get("commentCount") or 0)
        dur = _parse_iso8601_duration(str(cdet.get("duration") or ""))
        is_short = (0 < dur <= 65) or ("#shorts" in title.lower())
        pub_at = str(snip.get("publishedAt") or "")
        metrics = compute_viral_score(views, likes, comments, pub_at, is_short)

        raw_tags = snip.get("tags") or []
        clean_tags = [str(t).strip() for t in raw_tags if str(t).strip()][:12]
        desc_first = str(snip.get("description") or "").splitlines()[0][:180] if snip.get("description") else ""

        signals.append(
            ViralSignal(
                signal_id=f"{source}_{vid or abs(hash(title))}",
                source=source,
                title=title,
                channel_or_origin=str(snip.get("channelTitle") or ""),
                region=region,
                category=category_label or str(snip.get("categoryId") or ""),
                source_url=f"https://www.youtube.com/watch?v={vid}" if vid else "",
                published_at=pub_at,
                view_count=views,
                like_count=likes,
                comment_count=comments,
                duration_sec=dur,
                is_short_form=is_short,
                views_per_hour=metrics["views_per_hour"],
                engagement_rate=metrics["engagement_rate"],
                viral_score=metrics["viral_score"],
                tags=clean_tags,
                summary_hint=desc_first,
            )
        )
    return signals


def scan_youtube_most_popular(
    regions: Optional[List[str]] = None,
    niche: str = "",
    limit_per_region: int = 12,
    api_key: str = "",
    http_get: Optional[Callable[..., Any]] = None,
) -> List[ViralSignal]:
    """Queries official YouTube Data API v3 `videos?chart=mostPopular`."""
    key = (api_key or os.environ.get("YT_API_KEY", "")).strip()
    if not key:
        return []
    getter = http_get or requests.get
    reg_list = [r.strip().upper() for r in (regions or ["IN", "US"]) if r.strip()]
    cat_id = YOUTUBE_CATEGORY_IDS.get(niche.strip().lower(), "")
    out: List[ViralSignal] = []

    for reg in reg_list:
        params: Dict[str, Any] = {
            "part": "snippet,statistics,contentDetails",
            "chart": "mostPopular",
            "regionCode": reg,
            "maxResults": str(min(max(limit_per_region, 1), 25)),
            "key": key,
        }
        if cat_id:
            params["videoCategoryId"] = cat_id
        try:
            r = getter(f"{YT_API_BASE}/videos", params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
            if not getattr(r, "ok", False):
                continue
            items = r.json().get("items") or []
            out.extend(_parse_yt_video_items(items, "youtube_most_popular", reg, niche or cat_id))
        except Exception as exc:
            print(f"  [scanner:yt_popular:{reg}] skipped: {type(exc).__name__}")
    return out


def scan_youtube_niche_top(
    query: str,
    days: int = 7,
    region: str = "US",
    limit: int = 10,
    api_key: str = "",
    http_get: Optional[Callable[..., Any]] = None,
) -> List[ViralSignal]:
    """Queries official YouTube Data API v3 `search?order=viewCount` enriched with `videos` stats."""
    key = (api_key or os.environ.get("YT_API_KEY", "")).strip()
    if not key or not query.strip():
        return []
    getter = http_get or requests.get
    since = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        r = getter(
            f"{YT_API_BASE}/search",
            params={
                "part": "snippet",
                "type": "video",
                "order": "viewCount",
                "q": query.strip(),
                "regionCode": region.upper(),
                "publishedAfter": since,
                "maxResults": str(min(max(limit, 1), 20)),
                "safeSearch": "moderate",
                "key": key,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        if not getattr(r, "ok", False):
            return []
        ids = [
            str((it.get("id") or {}).get("videoId") or "")
            for it in (r.json().get("items") or [])
            if (it.get("id") or {}).get("videoId")
        ]
        if not ids:
            return []

        r2 = getter(
            f"{YT_API_BASE}/videos",
            params={
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(ids[:20]),
                "key": key,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        if not getattr(r2, "ok", False):
            return []
        return _parse_yt_video_items(r2.json().get("items") or [], "youtube_niche_search", region.upper(), query.strip())
    except Exception as exc:
        print(f"  [scanner:yt_niche] skipped: {type(exc).__name__}")
        return []


def scan_public_fallback_trends(
    regions: Optional[List[str]] = None,
    query: str = "",
    offline: bool = False,
) -> List[ViralSignal]:
    """
    Zero-key fallback trend discovery using existing read-only `trends.py` helpers
    (Google Trends RSS + Wikipedia Top Views) when YT_API_KEY is absent.
    """
    if offline:
        topic_seed = query.strip() or "Why Deep Ocean Creatures Glow in Total Darkness"
        return [
            ViralSignal(
                signal_id="offline_seed_1",
                source="offline_fallback",
                title=topic_seed,
                channel_or_origin="Offline Trend Seed",
                region="US",
                category=query.strip() or "Science & Mystery",
                view_count=500_000,
                like_count=25_000,
                comment_count=1_200,
                duration_sec=45,
                is_short_form=True,
                views_per_hour=12_500.0,
                engagement_rate=0.057,
                viral_score=88.5,
                tags=[w.lower() for w in re.findall(r"[A-Za-z0-9]{4,}", topic_seed)][:6],
                summary_hint="Offline deterministic trend fixture.",
            )
        ]

    out: List[ViralSignal] = []
    try:
        import trends as existing_trends
    except Exception:
        existing_trends = None

    reg_list = [r.strip().upper() for r in (regions or ["IN", "US"]) if r.strip()]
    if existing_trends is not None:
        for reg in reg_list:
            try:
                for idx, item in enumerate(existing_trends.google_trends(reg)[:8]):
                    title = str(item.get("title") or "").strip()
                    if not title:
                        continue
                    traffic_raw = str(item.get("traffic") or "50000")
                    digits = re.sub(r"[^0-9]", "", traffic_raw)
                    est_views = int(digits) if digits else 50_000
                    metrics = compute_viral_score(est_views, int(est_views * 0.04), int(est_views * 0.005), "", True)
                    out.append(
                        ViralSignal(
                            signal_id=f"gtrends_{reg}_{idx}_{abs(hash(title)) % 100000}",
                            source="google_trends",
                            title=title,
                            channel_or_origin=f"Google Trends {reg}",
                            region=reg,
                            category=query.strip() or "Trending",
                            view_count=est_views,
                            duration_sec=45,
                            is_short_form=True,
                            views_per_hour=metrics["views_per_hour"],
                            engagement_rate=metrics["engagement_rate"],
                            viral_score=metrics["viral_score"],
                            tags=[w.lower() for w in re.findall(r"[A-Za-z0-9]{3,}", title)][:8],
                            summary_hint=str(item.get("news") or "")[:160],
                        )
                    )
            except Exception:
                pass

        try:
            for idx, witem in enumerate(existing_trends.wikipedia_top()[:6]):
                title = str(witem.get("title") or "").strip()
                if not title:
                    continue
                views = int(witem.get("views") or 100_000)
                metrics = compute_viral_score(views, int(views * 0.03), int(views * 0.004), "", True)
                out.append(
                    ViralSignal(
                        signal_id=f"wiki_{idx}_{abs(hash(title)) % 100000}",
                        source="wikipedia_top",
                        title=title,
                        channel_or_origin="Wikipedia Top Views",
                        region="GLOBAL",
                        category=query.strip() or "Knowledge",
                        view_count=views,
                        duration_sec=50,
                        is_short_form=True,
                        views_per_hour=metrics["views_per_hour"],
                        engagement_rate=metrics["engagement_rate"],
                        viral_score=metrics["viral_score"],
                        tags=[w.lower() for w in re.findall(r"[A-Za-z0-9]{3,}", title)][:8],
                    )
                )
        except Exception:
            pass

    if query.strip() and out:
        q_words = set(re.findall(r"[a-z0-9]{3,}", query.lower()))
        for sig in out:
            t_words = set(re.findall(r"[a-z0-9]{3,}", (sig.title + " " + sig.summary_hint).lower()))
            if q_words & t_words:
                sig.viral_score = round(sig.viral_score + 15.0, 2)

    return out


def _load_seen_topics(remaker_history_path: Optional[Path] = None) -> Set[str]:
    """Reads existing history.json (read-only) + trending_remaker_history.json for deduplication."""
    seen: Set[str] = set()
    candidates = [
        PARENT_DIR / "history.json",
        remaker_history_path or (PARENT_DIR / "trending_remaker_history.json"),
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            items = raw if isinstance(raw, list) else (raw.get("entries") or raw.get("videos") or [])
            for entry in items:
                if not isinstance(entry, dict):
                    continue
                for k in ("topic", "title", "source_title", "remake_topic"):
                    val = str(entry.get(k) or "").strip().lower()
                    if val:
                        seen.add(re.sub(r"[^a-z0-9]+", " ", val).strip())
        except Exception:
            continue
    return seen


def rank_and_dedupe_signals(
    signals: List[ViralSignal],
    top_k: int = 10,
    remaker_history_path: Optional[Path] = None,
) -> List[ViralSignal]:
    """Deduplicates by normalized title & past history, then ranks by viral_score desc."""
    seen = _load_seen_topics(remaker_history_path)
    unique: List[ViralSignal] = []
    batch_keys: Set[str] = set()

    for sig in sorted(signals, key=lambda s: (s.viral_score, s.view_count), reverse=True):
        norm = re.sub(r"[^a-z0-9]+", " ", sig.title.lower()).strip()
        if not norm or norm in batch_keys or norm in seen:
            continue
        batch_keys.add(norm)
        unique.append(sig)
        if len(unique) >= max(1, top_k):
            break
    return unique


def discover_viral_signals(
    regions: Optional[List[str]] = None,
    niche: str = "",
    query: str = "",
    days: int = 7,
    top_k: int = 10,
    api_key: str = "",
    offline: bool = False,
    remaker_history_path: Optional[Path] = None,
    http_get: Optional[Callable[..., Any]] = None,
) -> List[ViralSignal]:
    """Unified entry point: official YouTube Data API first, zero-key public fallback second."""
    signals: List[ViralSignal] = []
    if not offline:
        if query.strip():
            reg0 = (regions or ["US"])[0]
            signals.extend(
                scan_youtube_niche_top(
                    query=query,
                    days=days,
                    region=reg0,
                    limit=max(top_k, 10),
                    api_key=api_key,
                    http_get=http_get,
                )
            )
        signals.extend(
            scan_youtube_most_popular(
                regions=regions,
                niche=niche,
                limit_per_region=max(top_k, 10),
                api_key=api_key,
                http_get=http_get,
            )
        )
    if not signals:
        signals.extend(scan_public_fallback_trends(regions=regions, query=query or niche, offline=offline))
    return rank_and_dedupe_signals(signals, top_k=top_k, remaker_history_path=remaker_history_path)
