#!/usr/bin/env python3
"""
Global Multi-Source Trend Discovery & Trend-to-Story Engine.

Collects fresh public signals legally via zero-cost official RSS feeds & public APIs:
  1. Google Trends Daily RSS (`trends.google.com/trending/rss?geo={CC}`)
  2. Google News RSS (`news.google.com/rss` localized by country/language)
  3. Wikipedia Top Pageviews REST API (multi-language, evergreen noise filtered)
  4. Hacker News Top Stories Firebase API (emerging tech/science/AI trends)
  5. Optional YouTube Data API v3 (`YT_API_KEY`) for trending videos & Shorts
  6. Optional best-effort Reddit RSS (gracefully skipped on cloud HTTP 429/403)

Note on platform API honesty:
  X (Twitter), Instagram Reels, and TikTok do not offer unrestricted free public
  trend APIs; this engine relies strictly on reliable, legal, zero-cost public
  endpoints and honors configurable caching (`hourly`, `daily`, `weekly`).
"""

from __future__ import annotations

import email.utils
import json
import math
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote

import requests

USER_AGENT = "RaptarTrendStudio/2.0 (https://github.com/TheRaptar/Automated-video-creation-)"

GLOBAL_REGIONS = ["US", "IN", "GB", "CA", "AU", "JP", "KR", "DE", "FR", "BR", "ID", "AE"]

WIKI_SKIP_PREFIXES = (
    "Main_Page", "Special:", "Wikipedia:", "Portal:", "File:", "Category:",
    "Help:", "Template:", "Deaths_in_", "List_of_", "YouTube", "Google",
    "Facebook", "Instagram", "Pornhub", "XHamster", "ChatGPT", "United_States",
)

TREND_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "funny_animals": {
        "keywords": ("lion", "dog", "cat", "pet", "animal", "zoo", "wildlife", "squirrel", "monkey", "funny", "cute"),
        "default_style": "animated_comedy",
        "recommended_seconds": 45,
        "story_frame": "original funny anthropomorphic animal comedy inspired by this trend",
    },
    "emotional_animals": {
        "keywords": ("rescue", "puppy", "elephant", "bird", "dog", "cat", "animal", "wildlife", "loyalty", "heartwarming"),
        "default_style": "fable",
        "recommended_seconds": 60,
        "story_frame": "heartwarming original animal friendship story with emotional payoff",
    },
    "cartoon": {
        "keywords": ("cartoon", "animation", "pixar", "disney", "comic", "character", "toon", "movie"),
        "default_style": "animated_comedy",
        "recommended_seconds": 50,
        "story_frame": "vibrant 3D/2D cartoon adventure featuring original quirky characters",
    },
    "anime": {
        "keywords": ("anime", "manga", "japan", "studio", "shonen", "cyberpunk", "samurai", "fantasy"),
        "default_style": "animated_anime",
        "recommended_seconds": 60,
        "story_frame": "dramatic cinematic anime original short story with vivid skies and twist",
    },
    "children": {
        "keywords": ("kids", "children", "school", "magic", "fairy", "dragon", "space", "dinosaur", "story"),
        "default_style": "fable",
        "recommended_seconds": 90,
        "story_frame": "wholesome children's animated fable with gentle humor and positive lesson",
    },
    "comedy": {
        "keywords": ("meme", "viral", "funny", "comedy", "laugh", "prank", "challenge", "roast", "twist"),
        "default_style": "animated_comedy",
        "recommended_seconds": 35,
        "story_frame": "fast-paced punchy animated comedy sketch with original characters",
    },
    "fantasy_adventure": {
        "keywords": ("myth", "legend", "kingdom", "ancient", "magic", "dragon", "quest", "temple", "treasure"),
        "default_style": "animated_myth",
        "recommended_seconds": 180,
        "story_frame": "epic fantasy adventure saga across multiple cinematic chapters",
    },
    "action": {
        "keywords": ("action", "hero", "battle", "race", "superhero", "car", "chase", "mission", "sport", "match"),
        "default_style": "scifi",
        "recommended_seconds": 55,
        "story_frame": "high-energy animated action sequence with original heroes and dynamic camera cuts",
    },
    "inspirational": {
        "keywords": ("inspire", "success", "dream", "courage", "never give up", "record", "win", "achieve", "motivation"),
        "default_style": "animated_myth",
        "recommended_seconds": 50,
        "story_frame": "uplifting original parable turning real human determination into timeless animation",
    },
    "educational": {
        "keywords": ("science", "space", "nasa", "ocean", "history", "physics", "brain", "discover", "study", "earth"),
        "default_style": "fact",
        "recommended_seconds": 120,
        "story_frame": "clear, engaging animated explainer story turning verified science into visual storytelling",
    },
    "technology": {
        "keywords": ("ai", "robot", "tech", "apple", "google", "chip", "quantum", "software", "open source", "rocket", "cyber"),
        "default_style": "scifi",
        "recommended_seconds": 90,
        "story_frame": "futuristic animated story explaining emerging technology through original characters",
    },
    "entertainment": {
        "keywords": ("film", "movie", "music", "game", "gaming", "series", "show", "trailer", "box office", "award"),
        "default_style": "animated_comedy",
        "recommended_seconds": 45,
        "story_frame": "original satirical/cinematic animated story inspired by pop-culture themes without copying IP",
    },
    "current_events": {
        "keywords": ("world", "climate", "economy", "summit", "global", "city", "news", "launch", "milestone"),
        "default_style": "fact",
        "recommended_seconds": 90,
        "story_frame": "fact-checked, balanced animated visual explainer avoiding rumors or impersonation",
    },
    "festival_seasonal": {
        "keywords": ("diwali", "christmas", "new year", "pongal", "holi", "eid", "halloween", "lunar", "spring", "winter", "festival"),
        "default_style": "animated_myth",
        "recommended_seconds": 60,
        "story_frame": "festive cultural animated tale celebrating seasonal traditions with original characters",
    },
    "shorts_formats": {
        "keywords": ("what if", "top 3", "pov", "secret", "hidden", "vs", "challenge", "reaction", "twist"),
        "default_style": "animated_comedy",
        "recommended_seconds": 30,
        "story_frame": "ultra-tight 15-30s hook-twist-payoff vertical Short format",
    },
}

CADENCE_SECONDS = {
    "hourly": 3600,
    "daily": 86400,
    "weekly": 604800,
}


@dataclass
class TrendItem:
    title: str
    source: str
    region: str
    category: str
    freshness_score: float
    growth_score: float
    combined_score: float
    traffic_hint: str = ""
    published_ts: float = 0.0
    summary: str = ""
    recommended_seconds: int = 45
    recommended_style: str = "animated_comedy"
    requires_fact_verification: bool = False
    original_story_angle: str = ""
    sources_seen: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _http_get(url: str, params: Optional[dict] = None, timeout: int = 12) -> Optional[requests.Response]:
    try:
        r = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        return r if r.ok else None
    except requests.RequestException:
        return None


def _parse_rfc_date(date_str: str) -> float:
    if not date_str:
        return time.time()
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return time.time()


def _parse_traffic_volume(raw: str) -> float:
    m = re.search(r"(\d[\d,]*)\s*([kKmM]?)", raw or "")
    if not m:
        return 1000.0
    val = float(m.group(1).replace(",", ""))
    unit = m.group(2).lower()
    if unit == "k":
        val *= 1_000.0
    elif unit == "m":
        val *= 1_000_000.0
    return max(100.0, val)


def _classify_category(text: str, preferred_category: str = "") -> str:
    low = (text or "").lower()
    if preferred_category and preferred_category in TREND_CATEGORIES:
        if any(k in low for k in TREND_CATEGORIES[preferred_category]["keywords"]):
            return preferred_category
    best_cat, best_hits = "", 0
    for cat, meta in TREND_CATEGORIES.items():
        hits = sum(1 for k in meta["keywords"] if k in low)
        if hits > best_hits:
            best_cat, best_hits = cat, hits
    if best_cat:
        return best_cat
    return preferred_category if preferred_category in TREND_CATEGORIES else "entertainment"


def fetch_google_trends_rss(geo: str = "US", limit: int = 15) -> List[Dict[str, Any]]:
    r = _http_get(f"https://trends.google.com/trending/rss?geo={geo}")
    if not r:
        return []
    ns = {"ht": "https://trends.google.com/trending/rss"}
    out: List[Dict[str, Any]] = []
    try:
        root = ET.fromstring(r.text)
        for item in root.findall(".//item")[:limit]:
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            traffic = (item.findtext("ht:approx_traffic", "", ns) or "").strip()
            pub_ts = _parse_rfc_date(item.findtext("pubDate", ""))
            news_title = (item.findtext("ht:news_item/ht:news_item_title", "", ns) or "").strip()
            out.append({
                "title": title,
                "source": "google_trends",
                "region": geo,
                "traffic": traffic,
                "volume": _parse_traffic_volume(traffic),
                "published_ts": pub_ts,
                "summary": news_title,
            })
    except ET.ParseError:
        pass
    return out


def fetch_google_news_rss(geo: str = "US", lang: str = "en", query: str = "", limit: int = 15) -> List[Dict[str, Any]]:
    hl = f"{lang}-{geo}" if len(lang) == 2 and len(geo) == 2 else "en-US"
    ceid = f"{geo}:{lang}" if len(lang) == 2 and len(geo) == 2 else "US:en"
    if query:
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl={hl}&gl={geo}&ceid={ceid}"
    else:
        url = f"https://news.google.com/rss?hl={hl}&gl={geo}&ceid={ceid}"
    r = _http_get(url)
    if not r:
        return []
    out: List[Dict[str, Any]] = []
    try:
        root = ET.fromstring(r.text)
        for item in root.findall(".//item")[:limit]:
            raw_title = (item.findtext("title") or "").strip()
            title = raw_title.split(" - ")[0].strip() if " - " in raw_title else raw_title
            if not title:
                continue
            pub_ts = _parse_rfc_date(item.findtext("pubDate", ""))
            out.append({
                "title": title,
                "source": "google_news",
                "region": geo,
                "traffic": "news_headline",
                "volume": 25_000.0,
                "published_ts": pub_ts,
                "summary": raw_title,
            })
    except ET.ParseError:
        pass
    return out


def fetch_wikipedia_top(lang: str = "en", limit: int = 15) -> List[Dict[str, Any]]:
    wiki_lang = lang if lang in ("en", "hi", "ta", "es", "fr", "de", "ja", "ko", "pt", "ar", "id") else "en"
    for offset_days in (1, 2):
        day = (datetime.now(timezone.utc) - timedelta(days=offset_days)).strftime("%Y/%m/%d")
        r = _http_get(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{wiki_lang}.wikipedia/all-access/{day}")
        if not r:
            continue
        try:
            articles = r.json()["items"][0]["articles"]
            out = []
            for art in articles:
                name = art.get("article", "")
                if any(name.startswith(p) for p in WIKI_SKIP_PREFIXES):
                    continue
                views = int(art.get("views", 0))
                if views < 15_000 and wiki_lang == "en":
                    continue
                out.append({
                    "title": name.replace("_", " "),
                    "source": f"wikipedia_{wiki_lang}",
                    "region": "ALL",
                    "traffic": f"{views:,} views",
                    "volume": float(views),
                    "published_ts": time.time() - offset_days * 86400 * 0.5,
                    "summary": f"Trending encyclopedia topic ({views:,} daily views)",
                })
                if len(out) >= limit:
                    break
            if out:
                return out
        except Exception:
            continue
    return []


def fetch_hackernews_top(limit: int = 10) -> List[Dict[str, Any]]:
    r = _http_get("https://hacker-news.firebaseio.com/v0/topstories.json")
    if not r:
        return []
    out: List[Dict[str, Any]] = []
    try:
        ids = r.json()[:limit]
        for sid in ids:
            ir = _http_get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=6)
            if not ir:
                continue
            item = ir.json() or {}
            title = (item.get("title") or "").strip()
            score = int(item.get("score") or 0)
            if title and score >= 40:
                out.append({
                    "title": title,
                    "source": "hacker_news",
                    "region": "ALL",
                    "traffic": f"{score} pts",
                    "volume": float(score * 300),
                    "published_ts": float(item.get("time") or time.time()),
                    "summary": f"Emerging technology/science discussion ({score} points)",
                })
    except Exception:
        pass
    return out


def fetch_youtube_trending(region: str = "US", limit: int = 10) -> List[Dict[str, Any]]:
    api_key = os.environ.get("YT_API_KEY", "").strip()
    if not api_key:
        return []
    r = _http_get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"key": api_key, "part": "snippet,statistics", "chart": "mostPopular", "regionCode": region, "maxResults": limit},
    )
    if not r:
        return []
    out: List[Dict[str, Any]] = []
    try:
        for it in r.json().get("items", []):
            title = (it.get("snippet", {}).get("title") or "").strip()
            views = int(it.get("statistics", {}).get("viewCount") or 0)
            if title:
                out.append({
                    "title": title,
                    "source": "youtube_trending",
                    "region": region,
                    "traffic": f"{views:,} views",
                    "volume": float(views),
                    "published_ts": time.time() - 3600 * 6,
                    "summary": f"YouTube popular video in {region}",
                })
    except Exception:
        pass
    return out


def fetch_reddit_rss_best_effort(subreddit: str = "animation", limit: int = 8) -> List[Dict[str, Any]]:
    """Best-effort Reddit RSS reader; gracefully skips if Reddit rate-limits cloud IPs (HTTP 429/403)."""
    r = _http_get(f"https://www.reddit.com/r/{subreddit}/hot.rss?limit={limit}", timeout=6)
    if not r:
        return []
    out: List[Dict[str, Any]] = []
    try:
        root = ET.fromstring(r.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns)[:limit]:
            title = (entry.findtext("atom:title", "", ns) or "").strip()
            if title:
                out.append({
                    "title": title,
                    "source": f"reddit_r_{subreddit}",
                    "region": "ALL",
                    "traffic": "community_hot",
                    "volume": 15_000.0,
                    "published_ts": time.time() - 7200,
                    "summary": f"Reddit r/{subreddit} discussion",
                })
    except ET.ParseError:
        pass
    return out


def _normalize_topic_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _is_safe_and_original_candidate(title: str) -> bool:
    """Filters out unsafe tragedy exploitation, explicit content, or spammy strings."""
    low = (title or "").lower()
    blocked = ("porn", "xxx", "suicide", "gore", "beheading", "mass shooting", "nsfw")
    return bool(low and len(low) >= 3 and not any(b in low for b in blocked))


def recommend_duration_for_trend(category: str, title: str, target_format: str = "auto") -> int:
    """Automatically selects ideal video duration based on topic complexity and format."""
    if target_format in ("short_15", "shorts_formats"):
        return 25
    if target_format == "short":
        return 45
    if target_format == "medium":
        return 120
    if target_format == "long":
        return 360
    if target_format == "epic_long":
        return 600
    base = TREND_CATEGORIES.get(category, {}).get("recommended_seconds", 45)
    if len(title.split()) >= 7 and category in ("educational", "fantasy_adventure", "technology"):
        return max(base, 120)
    return int(base)


class TrendDiscoveryEngine:
    """
    Multi-region, rate-limit-aware Trend Discovery & Ranking Engine.
    Caches snapshots according to `cadence` (`hourly`, `daily`, `weekly`) and
    deduplicates against previously generated topics.
    """

    def __init__(self, cache_path: Optional[Path] = None, cadence: str = "daily") -> None:
        self.cache_path = Path(cache_path) if cache_path else Path("trend_cache.json")
        self.cadence = cadence if cadence in CADENCE_SECONDS else "daily"

    def _load_cache(self) -> Dict[str, Any]:
        try:
            if self.cache_path.exists():
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def _save_cache(self, payload: Dict[str, Any]) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def discover(
        self,
        region: str = "ALL",
        lang: str = "en",
        category: str = "",
        seen_topics: Optional[Sequence[str]] = None,
        limit: int = 12,
        offline: bool = False,
        force_refresh: bool = False,
    ) -> List[TrendItem]:
        """Discovers, ranks, deduplicates, and returns top fresh TrendItems."""
        seen_norm = {_normalize_topic_key(s) for s in (seen_topics or []) if s}
        cache_key = f"{region}:{lang}:{category or 'any'}"
        ttl = CADENCE_SECONDS.get(self.cadence, 86400)

        if not force_refresh and not offline:
            cache = self._load_cache()
            entry = cache.get(cache_key)
            if entry and (time.time() - float(entry.get("ts", 0))) < ttl:
                cached = [TrendItem(**it) for it in entry.get("items", [])]
                filtered = [t for t in cached if _normalize_topic_key(t.title) not in seen_norm]
                if filtered:
                    return filtered[:limit]

        raw_signals: List[Dict[str, Any]] = []
        if offline:
            now = time.time()
            raw_signals = [
                {
                    "title": "Tiny clever animal builds impossible golden tower with teamwork",
                    "source": "offline_seed", "region": "ALL", "traffic": "50K+",
                    "volume": 50_000.0, "published_ts": now - 1800,
                    "summary": "Offline viral animal comedy seed for testing",
                },
                {
                    "title": "Deep ocean glowing creature discovered near volcanic ridge",
                    "source": "offline_seed", "region": "ALL", "traffic": "80K+",
                    "volume": 80_000.0, "published_ts": now - 3600,
                    "summary": "Offline science & wonder story seed",
                },
                {
                    "title": "Open-source autonomous robot learns to paint animated murals",
                    "source": "offline_seed", "region": "ALL", "traffic": "40K+",
                    "volume": 40_000.0, "published_ts": now - 5400,
                    "summary": "Offline technology & animation seed",
                },
            ]
        else:
            geos = ["US", "IN", "GB", "JP"] if region.upper() == "ALL" else [region.upper()[:2]]
            for g in geos:
                raw_signals.extend(fetch_google_trends_rss(geo=g, limit=10))
            raw_signals.extend(fetch_google_news_rss(geo=geos[0], lang=lang, query=category.replace("_", " ") if category else "", limit=12))
            raw_signals.extend(fetch_wikipedia_top(lang=lang, limit=12))
            if not category or category in ("technology", "educational", "current_events", "action"):
                raw_signals.extend(fetch_hackernews_top(limit=8))
            raw_signals.extend(fetch_youtube_trending(region=geos[0], limit=8))
            # Optional best-effort Reddit RSS
            if category in ("anime", "cartoon", "funny_animals"):
                raw_signals.extend(fetch_reddit_rss_best_effort("animation", limit=5))

        # Deduplicate & merge cross-source convergence
        merged: Dict[str, Dict[str, Any]] = {}
        for sig in raw_signals:
            title = str(sig.get("title") or "").strip()
            if not _is_safe_and_original_candidate(title):
                continue
            key = _normalize_topic_key(title)
            if not key or key in seen_norm:
                continue
            if key not in merged:
                merged[key] = {**sig, "sources_seen": [sig["source"]]}
            else:
                if sig["source"] not in merged[key]["sources_seen"]:
                    merged[key]["sources_seen"].append(sig["source"])
                merged[key]["volume"] = max(float(merged[key]["volume"]), float(sig.get("volume", 0)))
                merged[key]["published_ts"] = max(float(merged[key]["published_ts"]), float(sig.get("published_ts", 0)))

        now_ts = time.time()
        ranked: List[TrendItem] = []
        for entry in merged.values():
            age_hours = max(0.25, (now_ts - float(entry.get("published_ts", now_ts))) / 3600.0)
            # Exponential recency decay favors genuinely fresh rising trends over old staples
            freshness = round(10.0 * math.exp(-age_hours / 36.0), 2)
            vol_score = min(10.0, math.log10(max(100.0, float(entry.get("volume", 1000.0)))) * 1.6)
            convergence_bonus = min(3.0, (len(entry["sources_seen"]) - 1) * 1.5)
            growth = round(min(10.0, vol_score * 0.75 + convergence_bonus), 2)

            cat = _classify_category(f"{entry['title']} {entry.get('summary', '')}", preferred_category=category)
            cat_match_bonus = 2.0 if (category and cat == category) else 0.0
            combined = round(freshness * 0.45 + growth * 0.45 + cat_match_bonus, 2)

            cat_meta = TREND_CATEGORIES.get(cat, TREND_CATEGORIES["entertainment"])
            rec_sec = recommend_duration_for_trend(cat, entry["title"])
            ranked.append(TrendItem(
                title=entry["title"],
                source=entry["source"],
                region=entry.get("region", region),
                category=cat,
                freshness_score=freshness,
                growth_score=growth,
                combined_score=combined,
                traffic_hint=str(entry.get("traffic") or ""),
                published_ts=float(entry.get("published_ts") or now_ts),
                summary=str(entry.get("summary") or ""),
                recommended_seconds=rec_sec,
                recommended_style=cat_meta["default_style"],
                requires_fact_verification=(cat in ("current_events", "educational", "technology")),
                original_story_angle=(
                    f"Create an original animated story ({cat_meta['story_frame']}) loosely inspired by "
                    f"'{entry['title']}' using completely original characters (no impersonation or copyrighted clips)."
                ),
                sources_seen=list(entry["sources_seen"]),
            ))

        ranked.sort(key=lambda x: -x.combined_score)

        if not offline and ranked:
            cache = self._load_cache()
            cache[cache_key] = {"ts": now_ts, "items": [t.to_dict() for t in ranked[:25]]}
            self._save_cache(cache)

        return ranked[:limit]


if __name__ == "__main__":
    eng = TrendDiscoveryEngine(cadence="hourly")
    items = eng.discover(region="ALL", lang="en", limit=8)
    print(json.dumps([i.to_dict() for i in items], indent=2, ensure_ascii=False))
