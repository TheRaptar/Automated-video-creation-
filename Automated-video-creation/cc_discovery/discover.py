"""
Most-Viewed CC-BY & Licensed Creator Discovery Ranker.

100% official APIs and fail-closed LicenseGate verification — zero unauthorized scraping:
  1. Official YouTube Data API v3 (`videoLicense=creativeCommon`, `order=viewCount`)
     with mandatory double-check of `status.license == 'creativeCommon'` on `videos` endpoint.
     Exports a structured `cc_by_discovery_manifest.json` + verified CC-BY attribution metadata
     (never scrapes `youtube.com/watch`).
  2. Popularity-ranked Internet Archive (`downloads desc`, Public Domain / CC0 / CC-BY).
  3. Wikimedia Commons, Pexels, Pixabay, and creator Permission Manifest assets — every single
     item verified via `licensed_media.license_gate.verify_asset_license`.
"""

from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

PARENT_DIR = Path(__file__).resolve().parent.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from licensed_media.license_gate import VerifiedAsset, verify_asset_license
from licensed_media.sources import (
    fetch_pexels_videos,
    fetch_pixabay_videos,
    fetch_wikimedia_commons_videos,
    load_permission_manifest,
)

USER_AGENT = "RaptarCCDiscovery/1.0 (+https://github.com/TheRaptar/Automated-video-creation-)"
YT_API_BASE = "https://www.googleapis.com/youtube/v3"


@dataclass
class RankedCCReference:
    """Verified YouTube CC-BY discovery record (metadata + attribution; never scraped)."""
    video_id: str
    title: str
    channel_title: str
    channel_id: str
    source_url: str
    published_at: str
    view_count: int
    like_count: int
    comment_count: int
    license_status: str          # Must be 'creativeCommon'
    attribution_line: str
    popularity_score: float
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RankedLicensedClip:
    """Verified downloadable/local licensed clip ranked by engagement & visual quality."""
    asset: VerifiedAsset
    popularity_metric: int
    popularity_score: float
    ranking_reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "popularity_metric": self.popularity_metric,
            "popularity_score": self.popularity_score,
            "ranking_reason": self.ranking_reason,
            "asset": self.asset.to_dict(),
        }


def _score_popularity(views_or_downloads: int, width: int = 0, height: int = 0, bonus: float = 0.0) -> float:
    pop_pts = math.log10(max(views_or_downloads, 1) + 1.0) * 18.0
    res_pts = 10.0 if max(width, height) >= 1080 else (6.0 if max(width, height) >= 720 else 2.0)
    return round(pop_pts + res_pts + bonus, 2)


def discover_youtube_cc_by_most_viewed(
    query: str,
    days: int = 30,
    limit: int = 10,
    api_key: str = "",
    http_get: Optional[Callable[..., Any]] = None,
) -> List[RankedCCReference]:
    """
    Discovers the most-viewed Creative Commons (CC-BY) YouTube videos via official
    YouTube Data API v3 (`videoLicense=creativeCommon&order=viewCount`) and strictly
    double-verifies `status.license == 'creativeCommon'` on each item before returning.
    """
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
                "videoLicense": "creativeCommon",
                "order": "viewCount",
                "q": query.strip(),
                "publishedAfter": since,
                "maxResults": str(min(max(limit * 2, 10), 25)),
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
                "part": "snippet,statistics,status",
                "id": ",".join(ids[:25]),
                "key": key,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        if not getattr(r2, "ok", False):
            return []

        ranked: List[RankedCCReference] = []
        for it in (r2.json().get("items") or []):
            status = it.get("status") or {}
            # STRICT DOUBLE-CHECK: never accept standard YouTube license even if search returned it
            if str(status.get("license") or "") != "creativeCommon":
                continue
            vid = str(it.get("id") or "")
            snip = it.get("snippet") or {}
            stats = it.get("statistics") or {}
            title = str(snip.get("title") or "").strip()
            chan = str(snip.get("channelTitle") or "YouTube Creator").strip()
            chan_id = str(snip.get("channelId") or "").strip()
            views = int(stats.get("viewCount") or 0)
            likes = int(stats.get("likeCount") or 0)
            comments = int(stats.get("commentCount") or 0)
            src_url = f"https://www.youtube.com/watch?v={vid}"
            eng_bonus = min((float(likes + comments * 3) / float(max(views, 1))) * 180.0, 20.0)
            score = _score_popularity(views, 1920, 1080, bonus=eng_bonus)
            attr = f'"{title}" by {chan} (CC-BY-3.0 / YouTube Creative Commons) — {src_url}'
            ranked.append(
                RankedCCReference(
                    video_id=vid,
                    title=title,
                    channel_title=chan,
                    channel_id=chan_id,
                    source_url=src_url,
                    published_at=str(snip.get("publishedAt") or ""),
                    view_count=views,
                    like_count=likes,
                    comment_count=comments,
                    license_status="creativeCommon",
                    attribution_line=attr,
                    popularity_score=score,
                    tags=[str(t).strip() for t in (snip.get("tags") or []) if str(t).strip()][:10],
                )
            )
        ranked.sort(key=lambda x: (x.popularity_score, x.view_count), reverse=True)
        return ranked[: max(1, limit)]
    except Exception as exc:
        print(f"  [cc_discovery:youtube_cc] skipped: {type(exc).__name__}")
        return []


def discover_archive_most_popular(
    query: str,
    limit: int = 5,
    http_get: Optional[Callable[..., Any]] = None,
) -> List[RankedLicensedClip]:
    """
    Queries Internet Archive Public Domain / CC0 / CC-BY movies sorted by
    `downloads desc` and verifies every item through fail-closed LicenseGate.
    """
    getter = http_get or requests.get
    q_expr = (
        f"({query}) AND mediatype:(movies) AND "
        "(licenseurl:(*publicdomain* OR *zero* OR *creativecommons.org/licenses/by/*)) "
        "AND NOT licenseurl:(*by-nc* OR *by-nd*)"
    )
    out: List[RankedLicensedClip] = []
    try:
        r = getter(
            "https://archive.org/advancedsearch.php",
            params={
                "q": q_expr,
                "fl[]": ["identifier", "title", "creator", "licenseurl", "downloads"],
                "sort[]": "downloads desc",
                "rows": str(max(limit * 3, 10)),
                "output": "json",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=25,
        )
        if not getattr(r, "ok", False):
            return []
        docs = (r.json().get("response") or {}).get("docs") or []
        for doc in docs:
            ident = str(doc.get("identifier") or "").strip()
            if not ident:
                continue
            meta_r = getter(f"https://archive.org/metadata/{ident}", headers={"User-Agent": USER_AGENT}, timeout=20)
            if not getattr(meta_r, "ok", False):
                continue
            files = meta_r.json().get("files") or []
            mp4 = next(
                (f for f in files if str(f.get("name") or "").lower().endswith(".mp4") and not str(f.get("name") or "").endswith(".ia.mp4")),
                None,
            ) or next((f for f in files if str(f.get("name") or "").lower().endswith(".mp4")), None)
            if not mp4:
                continue

            lic_url = str(doc.get("licenseurl") or "").lower()
            if "by-nc" in lic_url or "by-nd" in lic_url:
                continue
            if "zero" in lic_url:
                lic_code = "CC0-1.0"
            elif "publicdomain" in lic_url:
                lic_code = "PUBLIC-DOMAIN"
            elif "licenses/by/4.0" in lic_url:
                lic_code = "CC-BY-4.0"
            elif "licenses/by/" in lic_url:
                lic_code = "CC-BY-3.0"
            else:
                lic_code = lic_url

            downloads = int(doc.get("downloads") or 0)
            creator = doc.get("creator") or "Internet Archive Contributor"
            if isinstance(creator, list):
                creator = ", ".join(str(x) for x in creator[:2])

            asset = VerifiedAsset(
                asset_id=f"archive_top_{ident}",
                media_type="video",
                source_provider="archive",
                external_id=ident,
                title=str(doc.get("title") or ident),
                creator=str(creator)[:120],
                source_url=f"https://archive.org/details/{ident}",
                download_url=f"https://archive.org/download/{ident}/{mp4['name']}",
                license_code=lic_code,
                allow_commercial=True,
                allow_derivatives=True,
                duration_sec=float(mp4.get("length") or 0.0) if str(mp4.get("length") or "").replace(".", "", 1).isdigit() else 0.0,
            )
            if verify_asset_license(asset).approved:
                out.append(
                    RankedLicensedClip(
                        asset=asset,
                        popularity_metric=downloads,
                        popularity_score=_score_popularity(downloads, 1280, 720, bonus=6.0),
                        ranking_reason=f"Internet Archive {lic_code} ({downloads:,} downloads)",
                    )
                )
            if len(out) >= limit:
                break
    except Exception as exc:
        print(f"  [cc_discovery:archive] skipped: {type(exc).__name__}")
    return out


def discover_ranked_licensed_media(
    query: str,
    sources: Optional[List[str]] = None,
    manifest_path: Optional[Path] = None,
    verify_youtube_api: bool = False,
    days: int = 30,
    limit: int = 6,
    aspect: str = "9:16",
    yt_api_key: str = "",
    offline: bool = False,
    http_get: Optional[Callable[..., Any]] = None,
) -> Tuple[List[RankedLicensedClip], List[RankedCCReference], List[VerifiedAsset]]:
    """
    Runs ranked licensed & CC-BY discovery across all enabled sources.
    Returns: (ranked_clips, youtube_cc_references, rejected_assets)
    """
    src_list = [s.strip().lower() for s in (sources or ["youtube_cc", "archive", "wikimedia", "pexels", "pixabay"]) if s.strip()]
    orientation = "portrait" if aspect == "9:16" else ("landscape" if aspect == "16:9" else "square")

    ranked_clips: List[RankedLicensedClip] = []
    yt_cc_refs: List[RankedCCReference] = []
    rejected: List[VerifiedAsset] = []

    # 1. Creator Permission Manifest (always honored first — highest priority)
    if manifest_path and Path(manifest_path).exists():
        m_ok, m_rej = load_permission_manifest(
            manifest_path=Path(manifest_path),
            verify_youtube_api=verify_youtube_api,
            yt_api_key=yt_api_key,
            http_get=http_get,
        )
        rejected.extend(m_rej)
        for idx, a in enumerate(m_ok):
            if a.media_type == "video":
                ranked_clips.append(
                    RankedLicensedClip(
                        asset=a,
                        popularity_metric=100_000 - idx * 1000,
                        popularity_score=round(95.0 - idx * 1.5, 2),
                        ranking_reason=f"Creator-approved / manifest verified ({a.license_code})",
                    )
                )

    if not offline:
        # 2. Official YouTube Data API v3 Creative Commons (CC-BY) Discovery
        if "youtube_cc" in src_list:
            yt_cc_refs = discover_youtube_cc_by_most_viewed(
                query=query,
                days=days,
                limit=limit,
                api_key=yt_api_key,
                http_get=http_get,
            )

        # 3. Popularity-ranked Internet Archive (downloads desc)
        if "archive" in src_list:
            ranked_clips.extend(discover_archive_most_popular(query=query, limit=limit, http_get=http_get))

        # 4. Wikimedia Commons (CC0 / Public Domain / CC-BY)
        if "wikimedia" in src_list:
            for idx, a in enumerate(fetch_wikimedia_commons_videos(query=query, limit=limit, http_get=http_get)):
                ranked_clips.append(
                    RankedLicensedClip(
                        asset=a,
                        popularity_metric=max(a.width * a.height, 1000),
                        popularity_score=_score_popularity(25_000 - idx * 2000, a.width, a.height, bonus=5.0),
                        ranking_reason=f"Wikimedia Commons verified ({a.license_code})",
                    )
                )

        # 5. Pexels & Pixabay Popular Open-License Clips
        if "pexels" in src_list:
            for idx, a in enumerate(fetch_pexels_videos(query=query, limit=limit, orientation=orientation, http_get=http_get)):
                ranked_clips.append(
                    RankedLicensedClip(
                        asset=a,
                        popularity_metric=max(a.width * a.height, 1000),
                        popularity_score=_score_popularity(40_000 - idx * 3000, a.width, a.height, bonus=4.0),
                        ranking_reason=f"Pexels popular open-license ({a.width}x{a.height})",
                    )
                )
        if "pixabay" in src_list:
            for idx, a in enumerate(fetch_pixabay_videos(query=query, limit=limit, http_get=http_get)):
                ranked_clips.append(
                    RankedLicensedClip(
                        asset=a,
                        popularity_metric=max(a.width * a.height, 1000),
                        popularity_score=_score_popularity(35_000 - idx * 2500, a.width, a.height, bonus=3.5),
                        ranking_reason=f"Pixabay popular open-license ({a.width}x{a.height})",
                    )
                )

    ranked_clips.sort(key=lambda c: (c.popularity_score, c.popularity_metric), reverse=True)
    return ranked_clips[: max(1, limit * 2)], yt_cc_refs, rejected


def export_cc_by_manifest_template(
    yt_cc_refs: List[RankedCCReference],
    out_path: Path,
) -> Path:
    """
    Exports discovered & double-verified YouTube CC-BY videos into a Permission Manifest
    template so creators/users can attach authorized local exports or direct creator files
    (never embeds raw youtube.com/watch URLs as download_url).
    """
    assets = []
    for ref in yt_cc_refs:
        assets.append({
            "asset_id": f"yt_cc_{ref.video_id}",
            "media_type": "video",
            "platform": "youtube",
            "title": ref.title,
            "creator_name": ref.channel_title,
            "youtube_video_id": ref.video_id,
            "expected_channel_id": ref.channel_id,
            "source_url": ref.source_url,
            "local_path": "",  # Supply creator-exported or authorized local file path before rendering
            "license_code": "VERIFIED-CC-BY",
            "permission_type": "verified_cc_by",
            "proof_ref": f"youtube_api_cc_verified:{ref.video_id} (views={ref.view_count})",
            "allow_commercial": True,
            "allow_derivatives": True,
            "attribution_text": ref.attribution_line,
        })
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "Double-verified via YouTube Data API v3 (status.license == creativeCommon). Attach authorized local_path or creator-supplied direct file URL before rendering.",
        "assets": assets,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path
