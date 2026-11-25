#!/usr/bin/env python3
"""
Authorized & Open-License Multi-Source Media Ingestion Adapters.

Supported sources (all routed through the fail-closed LicenseGate before download):
1. Official Open-License Video APIs:
   - Pexels Video API (Pexels License)
   - Pixabay Video API (Pixabay Content License)
   - Wikimedia Commons MediaWiki API (CC0 / Public Domain / CC-BY)
   - Internet Archive Advanced Search + Metadata API (Public Domain / CC0)
2. Official Open-License Audio/Music APIs:
   - Openverse Audio API (CC0 / CC-BY commercial & modifiable only)
   - Freesound API (CC0 / CC-BY only)
3. Authorized YouTube & Instagram Creator Sources:
   - Permission Manifest JSON (owned YouTube Studio exports, creator-approved local/direct files)
   - Own-Account Instagram Graph API (`/{ig_id}/media` — strictly your own account, zero scraping)
   - Optional YouTube Data API v3 ownership/Creative Commons metadata verification
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from .ledger import compute_sha256
from .license_gate import VerifiedAsset, verify_asset_license

USER_AGENT = "RaptarLicensedMediaAddon/1.0 (https://github.com/TheRaptar/Automated-video-creation-)"
IG_API_VERSION = os.environ.get("IG_API_VERSION", "v23.0")
IG_GRAPH_BASE = f"https://graph.facebook.com/{IG_API_VERSION}"
YT_API_BASE = os.environ.get("YT_API_BASE", "https://www.googleapis.com/youtube/v3").rstrip("/")


def _strip_html(raw: str) -> str:
    return re.sub(r"<[^>]+>", "", str(raw or "")).strip()


# ---------------------------------------------------------------------------
# 1. Pexels Video API (Official)
# ---------------------------------------------------------------------------
def fetch_pexels_videos(
    query: str,
    limit: int = 5,
    orientation: str = "portrait",
    api_key: str = "",
    http_get: Optional[Callable[..., Any]] = None,
) -> List[VerifiedAsset]:
    key = (api_key or os.environ.get("PEXELS_API_KEY", "")).strip()
    if not key:
        return []
    getter = http_get or requests.get
    out: List[VerifiedAsset] = []
    try:
        r = getter(
            "https://api.pexels.com/videos/search",
            params={"query": query, "per_page": max(limit * 2, 8), "orientation": orientation},
            headers={"Authorization": key, "User-Agent": USER_AGENT},
            timeout=25,
        )
        if not getattr(r, "ok", False):
            return []
        for v in r.json().get("videos", []):
            files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("link")]
            if not files:
                continue
            # Prefer crisp HD (720p-1080p) without huge 4K downloads
            files.sort(key=lambda f: abs((int(f.get("width") or 0)) - 1080))
            best = files[0]
            user = v.get("user") or {}
            asset = VerifiedAsset(
                asset_id=f"pexels_{v.get('id')}",
                media_type="video",
                source_provider="pexels",
                external_id=str(v.get("id", "")),
                title=f"Pexels video {v.get('id')} ({query})",
                creator=str(user.get("name") or "Pexels Creator"),
                source_url=str(v.get("url") or f"https://www.pexels.com/video/{v.get('id')}/"),
                download_url=str(best["link"]),
                license_code="PEXELS",
                allow_commercial=True,
                allow_derivatives=True,
                duration_sec=float(v.get("duration") or 0.0),
                width=int(best.get("width") or 0),
                height=int(best.get("height") or 0),
            )
            if verify_asset_license(asset).approved:
                out.append(asset)
            if len(out) >= limit:
                break
    except Exception as exc:
        print(f"  [sources:pexels] skipped: {type(exc).__name__}")
    return out


# ---------------------------------------------------------------------------
# 2. Pixabay Video API (Official)
# ---------------------------------------------------------------------------
def fetch_pixabay_videos(
    query: str,
    limit: int = 5,
    api_key: str = "",
    http_get: Optional[Callable[..., Any]] = None,
) -> List[VerifiedAsset]:
    key = (api_key or os.environ.get("PIXABAY_API_KEY", "")).strip()
    if not key:
        return []
    getter = http_get or requests.get
    out: List[VerifiedAsset] = []
    try:
        r = getter(
            "https://pixabay.com/api/videos/",
            params={"key": key, "q": query, "per_page": max(limit * 2, 8), "safesearch": "true"},
            headers={"User-Agent": USER_AGENT},
            timeout=25,
        )
        if not getattr(r, "ok", False):
            return []
        for hit in r.json().get("hits", []):
            vids = hit.get("videos") or {}
            chosen = None
            for sz in ("large", "medium", "small", "tiny"):
                cand = vids.get(sz) or {}
                if cand.get("url"):
                    chosen = cand
                    break
            if not chosen:
                continue
            asset = VerifiedAsset(
                asset_id=f"pixabay_{hit.get('id')}",
                media_type="video",
                source_provider="pixabay",
                external_id=str(hit.get("id", "")),
                title=str(hit.get("tags") or f"Pixabay video {hit.get('id')}"),
                creator=str(hit.get("user") or "Pixabay Creator"),
                source_url=str(hit.get("pageURL") or f"https://pixabay.com/videos/id-{hit.get('id')}/"),
                download_url=str(chosen["url"]),
                license_code="PIXABAY",
                allow_commercial=True,
                allow_derivatives=True,
                duration_sec=float(hit.get("duration") or 0.0),
                width=int(chosen.get("width") or 0),
                height=int(chosen.get("height") or 0),
            )
            if verify_asset_license(asset).approved:
                out.append(asset)
            if len(out) >= limit:
                break
    except Exception as exc:
        print(f"  [sources:pixabay] skipped: {type(exc).__name__}")
    return out


# ---------------------------------------------------------------------------
# 3. Wikimedia Commons API (Verified CC0 / Public Domain / CC-BY Video)
# ---------------------------------------------------------------------------
def fetch_wikimedia_commons_videos(
    query: str,
    limit: int = 4,
    http_get: Optional[Callable[..., Any]] = None,
) -> List[VerifiedAsset]:
    getter = http_get or requests.get
    out: List[VerifiedAsset] = []
    try:
        r = getter(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrnamespace": "6",  # File namespace
                "gsrsearch": f"{query} filetype:video",
                "gsrlimit": str(max(limit * 3, 10)),
                "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=25,
        )
        if not getattr(r, "ok", False):
            return []
        pages = ((r.json().get("query") or {}).get("pages") or {}).values()
        for page in pages:
            infos = page.get("imageinfo") or []
            if not infos:
                continue
            ii = infos[0]
            mime = str(ii.get("mime") or "").lower()
            dl_url = str(ii.get("url") or "")
            if not dl_url or not any(k in mime for k in ("video/", "webm", "mp4", "ogg")):
                continue
            ext = ii.get("extmetadata") or {}
            lic = _strip_html((ext.get("LicenseShortName") or {}).get("value", ""))
            artist = _strip_html((ext.get("Artist") or {}).get("value", "")) or "Wikimedia Commons Contributor"
            title = str(page.get("title") or "").replace("File:", "").strip()
            asset = VerifiedAsset(
                asset_id=f"wikimedia_{page.get('pageid')}",
                media_type="video",
                source_provider="wikimedia",
                external_id=str(page.get("pageid", "")),
                title=title or query,
                creator=artist[:120],
                source_url=str(ii.get("descriptionurl") or dl_url),
                download_url=dl_url,
                license_code=lic,
                allow_commercial=True,
                allow_derivatives=True,
                width=int(ii.get("width") or 0),
                height=int(ii.get("height") or 0),
            )
            if verify_asset_license(asset).approved:
                out.append(asset)
            if len(out) >= limit:
                break
    except Exception as exc:
        print(f"  [sources:wikimedia] skipped: {type(exc).__name__}")
    return out


# ---------------------------------------------------------------------------
# 4. Internet Archive API (Verified Public Domain / CC0 Classic Cinema)
# ---------------------------------------------------------------------------
def fetch_internet_archive_videos(
    query: str,
    limit: int = 3,
    http_get: Optional[Callable[..., Any]] = None,
) -> List[VerifiedAsset]:
    getter = http_get or requests.get
    out: List[VerifiedAsset] = []
    try:
        search_q = (
            f"({query}) AND mediatype:(movies) AND "
            f"(licenseurl:*publicdomain* OR licenseurl:*zero/1.0* OR rights:*public*)"
        )
        r = getter(
            "https://archive.org/advancedsearch.php",
            params={
                "q": search_q,
                "fl[]": ["identifier", "title", "creator", "licenseurl"],
                "rows": str(max(limit * 3, 8)),
                "output": "json",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=25,
        )
        if not getattr(r, "ok", False):
            return []
        docs = ((r.json().get("response") or {}).get("docs") or [])
        for doc in docs:
            ident = str(doc.get("identifier") or "").strip()
            if not ident:
                continue
            lic_url = str(doc.get("licenseurl") or "").lower()
            if "zero/1.0" in lic_url:
                lic_code = "CC0-1.0"
            elif "publicdomain" in lic_url or "mark/1.0" in lic_url:
                lic_code = "PUBLIC-DOMAIN"
            else:
                continue

            # Fetch item metadata to find a clean downloadable MP4
            mr = getter(
                f"https://archive.org/metadata/{ident}",
                headers={"User-Agent": USER_AGENT},
                timeout=20,
            )
            if not getattr(mr, "ok", False):
                continue
            mp4_name = None
            for f in (mr.json().get("files") or []):
                name = str(f.get("name") or "")
                size_bytes = int(f.get("size") or 0)
                if name.lower().endswith(".mp4") and (size_bytes == 0 or size_bytes < 120_000_000):
                    mp4_name = name
                    break
            if not mp4_name:
                continue

            creator_raw = doc.get("creator")
            if isinstance(creator_raw, list):
                creator = ", ".join(str(x) for x in creator_raw[:2])
            else:
                creator = str(creator_raw or "Public Domain Archive")

            asset = VerifiedAsset(
                asset_id=f"archive_{ident}",
                media_type="video",
                source_provider="archive",
                external_id=ident,
                title=str(doc.get("title") or ident),
                creator=creator[:120],
                source_url=f"https://archive.org/details/{ident}",
                download_url=f"https://archive.org/download/{ident}/{mp4_name}",
                license_code=lic_code,
                allow_commercial=True,
                allow_derivatives=True,
            )
            if verify_asset_license(asset).approved:
                out.append(asset)
            if len(out) >= limit:
                break
    except Exception as exc:
        print(f"  [sources:archive] skipped: {type(exc).__name__}")
    return out


# ---------------------------------------------------------------------------
# 5. Openverse & Freesound Audio APIs (Commercial-Safe CC0 / CC-BY Music)
# ---------------------------------------------------------------------------
def fetch_openverse_audio(
    query: str,
    limit: int = 3,
    http_get: Optional[Callable[..., Any]] = None,
) -> List[VerifiedAsset]:
    getter = http_get or requests.get
    out: List[VerifiedAsset] = []
    try:
        r = getter(
            "https://api.openverse.org/v1/audio/",
            params={
                "q": query,
                "license": "cc0,pdm,by",
                "license_type": "commercial,modification",
                "page_size": str(max(limit * 2, 6)),
            },
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        if not getattr(r, "ok", False):
            return []
        for item in r.json().get("results", []):
            dl = str(item.get("url") or "")
            if not dl:
                continue
            lic = str(item.get("license") or "").upper()
            ver = str(item.get("license_version") or "4.0").strip()
            lic_code = "CC0-1.0" if lic in ("CC0", "PDM") else f"CC-{lic}-{ver}"
            asset = VerifiedAsset(
                asset_id=f"openverse_{item.get('id')}",
                media_type="audio",
                source_provider="openverse",
                external_id=str(item.get("id", "")),
                title=str(item.get("title") or query),
                creator=str(item.get("creator") or "Openverse Artist"),
                source_url=str(item.get("foreign_landing_url") or dl),
                download_url=dl,
                license_code=lic_code,
                allow_commercial=True,
                allow_derivatives=True,
                duration_sec=float(item.get("duration") or 0) / 1000.0,
            )
            if verify_asset_license(asset).approved:
                out.append(asset)
            if len(out) >= limit:
                break
    except Exception as exc:
        print(f"  [sources:openverse] skipped: {type(exc).__name__}")
    return out


def fetch_freesound_audio(
    query: str,
    limit: int = 3,
    api_key: str = "",
    http_get: Optional[Callable[..., Any]] = None,
) -> List[VerifiedAsset]:
    key = (api_key or os.environ.get("FREESOUND_API_KEY", "")).strip()
    if not key:
        return []
    getter = http_get or requests.get
    out: List[VerifiedAsset] = []
    try:
        r = getter(
            "https://freesound.org/apiv2/search/text/",
            params={
                "query": query,
                "filter": 'license:"Creative Commons 0" OR license:"Attribution"',
                "fields": "id,name,username,license,url,previews,duration",
                "page_size": str(max(limit * 2, 6)),
                "token": key,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        if not getattr(r, "ok", False):
            return []
        for item in r.json().get("results", []):
            previews = item.get("previews") or {}
            dl = str(previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3") or "")
            if not dl:
                continue
            raw_lic = str(item.get("license") or "")
            low_lic = raw_lic.lower()
            if "publicdomain/zero" in low_lic or "cc0" in low_lic or "creative commons 0" in low_lic:
                lic_code = "CC0-1.0"
            elif "by-nc" in low_lic or "noncommercial" in low_lic:
                lic_code = "CC-BY-NC-4.0"
            elif "by/3.0" in low_lic or "attribution 3.0" in low_lic:
                lic_code = "CC-BY-3.0"
            elif "by/4.0" in low_lic or "attribution" in low_lic:
                lic_code = "CC-BY-4.0"
            else:
                lic_code = raw_lic
            asset = VerifiedAsset(
                asset_id=f"freesound_{item.get('id')}",
                media_type="audio",
                source_provider="freesound",
                external_id=str(item.get("id", "")),
                title=str(item.get("name") or query),
                creator=str(item.get("username") or "Freesound Artist"),
                source_url=str(item.get("url") or dl),
                download_url=dl,
                license_code=lic_code,
                allow_commercial=True,
                allow_derivatives=True,
                duration_sec=float(item.get("duration") or 0.0),
            )
            if verify_asset_license(asset).approved:
                out.append(asset)
            if len(out) >= limit:
                break
    except Exception as exc:
        print(f"  [sources:freesound] skipped: {type(exc).__name__}")
    return out


# ---------------------------------------------------------------------------
# 6. Authorized YouTube Metadata Verification (Official YouTube Data API v3)
# ---------------------------------------------------------------------------
def verify_youtube_video_metadata(
    video_id: str,
    expected_channel_id: str = "",
    require_cc_if_not_owned: bool = False,
    api_key: str = "",
    oauth_token: str = "",
    http_get: Optional[Callable[..., Any]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Cross-checks a creator-supplied YouTube video ID against the official YouTube
    Data API v3 to confirm channel ownership or Creative Commons status.
    Never downloads from YouTube watch URLs.
    """
    vid = str(video_id or "").strip()
    tok = (oauth_token or "").strip()
    key = (api_key or os.environ.get("YT_API_KEY", "")).strip()
    if not vid or not (tok or key):
        return False, {"reason": "Missing video_id or YouTube API credentials"}

    getter = http_get or requests.get
    params: Dict[str, str] = {"part": "snippet,status", "id": vid}
    headers: Dict[str, str] = {"User-Agent": USER_AGENT}
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    else:
        params["key"] = key

    try:
        r = getter(f"{YT_API_BASE}/videos", params=params, headers=headers, timeout=20)
        if not getattr(r, "ok", False):
            return False, {"reason": f"YouTube API HTTP {getattr(r, 'status_code', '?')}"}
        items = r.json().get("items") or []
        if not items:
            return False, {"reason": f"YouTube video '{vid}' not found"}
        item = items[0]
        snip = item.get("snippet") or {}
        st = item.get("status") or {}
        channel_id = str(snip.get("channelId") or "")
        yt_license = str(st.get("license") or "")
        info = {
            "video_id": vid,
            "channel_id": channel_id,
            "channel_title": str(snip.get("channelTitle") or ""),
            "title": str(snip.get("title") or ""),
            "youtube_license": yt_license,
        }
        if expected_channel_id and channel_id == expected_channel_id:
            info["verified_by"] = "youtube_channel_ownership"
            return True, info
        if require_cc_if_not_owned and yt_license == "creativeCommon":
            info["verified_by"] = "youtube_creative_common"
            return True, info
        if expected_channel_id and channel_id != expected_channel_id:
            info["reason"] = f"Channel mismatch: expected {expected_channel_id}, got {channel_id}"
            return False, info
        return True, info
    except Exception as exc:
        return False, {"reason": f"YouTube metadata check error: {type(exc).__name__}"}


# ---------------------------------------------------------------------------
# 7. Own-Account Instagram Graph API Fetcher (Strictly Authenticated Owner Media)
# ---------------------------------------------------------------------------
def fetch_own_instagram_videos(
    token: str = "",
    ig_id: str = "",
    limit: int = 5,
    http_get: Optional[Callable[..., Any]] = None,
) -> List[VerifiedAsset]:
    """
    Fetches VIDEO/REEL media owned by YOUR authenticated Instagram Business/Creator
    account via the official Meta Graph API (`/{ig_id}/media`).
    Never accesses or downloads third-party accounts.
    """
    parent_dir = str(Path(__file__).resolve().parent.parent)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    tok = (token or os.environ.get("IG_ACCESS_TOKEN", "")).strip()
    account_id = (ig_id or os.environ.get("IG_USER_ID", "")).strip()
    if not tok:
        try:
            import upload_instagram
            tok = upload_instagram.get_token()
        except Exception:
            return []
    if not account_id and http_get is None:
        try:
            import upload_instagram
            account_id = upload_instagram.get_instagram_account(tok)
        except Exception:
            return []
    if not (tok and account_id):
        return []

    getter = http_get or requests.get
    out: List[VerifiedAsset] = []
    try:
        r = getter(
            f"{IG_GRAPH_BASE}/{account_id}/media",
            params={
                "fields": "id,caption,media_type,media_product_type,media_url,permalink,timestamp",
                "limit": str(max(limit * 3, 12)),
                "access_token": tok,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=25,
        )
        if not getattr(r, "ok", False):
            return []
        for item in r.json().get("data", []):
            mtype = str(item.get("media_type") or "").upper()
            murl = str(item.get("media_url") or "")
            if mtype != "VIDEO" or not murl:
                continue
            mid = str(item.get("id") or "")
            caption = str(item.get("caption") or f"Own Instagram Video {mid}").splitlines()[0][:90]
            asset = VerifiedAsset(
                asset_id=f"own_ig_{mid}",
                media_type="video",
                source_provider="own_instagram_api",
                external_id=mid,
                title=caption,
                creator=f"Own Instagram Account ({account_id})",
                source_url=str(item.get("permalink") or f"https://www.instagram.com/"),
                download_url=murl,
                permission_type="self_owned",
                license_code="SELF-OWNED",
                proof_ref=f"instagram_graph_own_account:{account_id}:{mid}",
                allow_commercial=True,
                allow_derivatives=True,
            )
            if verify_asset_license(asset).approved:
                out.append(asset)
            if len(out) >= limit:
                break
    except Exception as exc:
        print(f"  [sources:own_ig] skipped: {type(exc).__name__}")
    return out


# ---------------------------------------------------------------------------
# 8. Creator Permission Manifest Loader (YouTube / Instagram / Local Approved)
# ---------------------------------------------------------------------------
def load_permission_manifest(
    manifest_path: Path,
    verify_youtube_api: bool = False,
    yt_api_key: str = "",
    yt_oauth_token: str = "",
    ig_token: str = "",
    http_get: Optional[Callable[..., Any]] = None,
) -> Tuple[List[VerifiedAsset], List[VerifiedAsset]]:
    """
    Loads a JSON Permission Manifest for owned or creator-approved YouTube, Instagram,
    or local videos, passing every item through the fail-closed LicenseGate.
    Returns (approved_assets, rejected_assets).
    """
    mp = Path(manifest_path)
    raw = json.loads(mp.read_text(encoding="utf-8"))
    items = raw.get("assets", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
    base_dir = mp.parent

    approved: List[VerifiedAsset] = []
    rejected: List[VerifiedAsset] = []

    for idx, entry in enumerate(items):
        if not isinstance(entry, dict):
            continue
        platform = str(entry.get("platform") or "local").strip().lower()
        provider = f"manifest_{platform}" if platform in ("youtube", "instagram", "local") else "manifest_local"
        local_raw = str(entry.get("local_path") or "").strip()
        if local_raw and not Path(local_raw).is_absolute():
            local_resolved = str((base_dir / local_raw).resolve())
        else:
            local_resolved = local_raw

        dl_url = str(entry.get("download_url") or "").strip()

        # If an own Instagram media_id is listed without local_path, resolve via official Graph API
        if platform == "instagram" and entry.get("ig_media_id") and not local_resolved and not dl_url:
            ig_tok = (ig_token or os.environ.get("IG_ACCESS_TOKEN", "")).strip()
            if ig_tok:
                getter = http_get or requests.get
                try:
                    r = getter(
                        f"{IG_GRAPH_BASE}/{entry['ig_media_id']}",
                        params={"fields": "id,media_type,media_url,permalink", "access_token": ig_tok},
                        timeout=15,
                    )
                    if getattr(r, "ok", False):
                        d = r.json()
                        if str(d.get("media_type") or "").upper() == "VIDEO":
                            dl_url = str(d.get("media_url") or "")
                except Exception:
                    pass

        asset = VerifiedAsset(
            asset_id=str(entry.get("asset_id") or f"manifest_{idx + 1}"),
            media_type=str(entry.get("media_type") or "video").lower(),
            source_provider=provider,
            external_id=str(entry.get("youtube_video_id") or entry.get("ig_media_id") or entry.get("asset_id") or f"m{idx+1}"),
            title=str(entry.get("title") or f"Creator Asset {idx + 1}"),
            creator=str(entry.get("creator_name") or entry.get("creator") or ""),
            source_url=str(entry.get("source_url") or ""),
            download_url=dl_url,
            local_path=local_resolved,
            license_code=str(entry.get("license_code") or ""),
            permission_type=str(entry.get("permission_type") or ""),
            proof_ref=str(entry.get("proof_ref") or ""),
            allow_commercial=bool(entry.get("allow_commercial", False)),
            allow_derivatives=bool(entry.get("allow_derivatives", False)),
            expires_at=str(entry.get("expires_at") or ""),
            attribution_text=str(entry.get("attribution_text") or ""),
            extra={k: v for k, v in entry.items() if k in ("youtube_video_id", "expected_channel_id", "ig_media_id")},
        )

        # Optional live YouTube Data API ownership / CC cross-check
        if verify_youtube_api and platform == "youtube" and entry.get("youtube_video_id"):
            ok, yt_info = verify_youtube_video_metadata(
                video_id=str(entry["youtube_video_id"]),
                expected_channel_id=str(entry.get("expected_channel_id") or ""),
                require_cc_if_not_owned=(asset.permission_type.lower() == "verified_cc_by"),
                api_key=yt_api_key,
                oauth_token=yt_oauth_token,
                http_get=http_get,
            )
            if not ok:
                asset.verification_status = "rejected"
                asset.verification_reason = f"YouTube API verification failed: {yt_info.get('reason', 'mismatch')}"
                rejected.append(asset)
                continue
            asset.extra["youtube_api_verified"] = yt_info

        decision = verify_asset_license(asset)
        if decision.approved:
            approved.append(asset)
        else:
            rejected.append(asset)

    return approved, rejected


# ---------------------------------------------------------------------------
# 9. Fail-Closed Verified Asset Downloader (Refuses Unapproved Assets)
# ---------------------------------------------------------------------------
def download_verified_asset(
    asset: VerifiedAsset,
    dest_dir: Path,
    http_get: Optional[Callable[..., Any]] = None,
) -> Path:
    """
    Downloads (or stages from local_path) an ALREADY-APPROVED asset and computes its
    SHA-256 checksum. Raises PermissionError if verification_status != 'approved'.
    """
    if asset.verification_status != "approved":
        raise PermissionError(
            f"Refusing to download unapproved asset '{asset.asset_id}': {asset.verification_reason}"
        )

    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", asset.asset_id)

    if asset.local_path and Path(asset.local_path).exists():
        src = Path(asset.local_path)
        ext = src.suffix or (".mp3" if asset.media_type == "audio" else ".mp4")
        dst = dest_dir / f"{safe_id}{ext}"
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        asset.local_path = str(dst)
        asset.sha256 = compute_sha256(dst)
        return dst

    if not asset.download_url:
        raise ValueError(f"Approved asset '{asset.asset_id}' has no reachable local_path or download_url.")

    ext = ".mp3" if asset.media_type == "audio" else ".mp4"
    low_u = asset.download_url.lower().split("?")[0]
    for cand_ext in (".mp4", ".webm", ".mov", ".mp3", ".wav", ".ogg"):
        if low_u.endswith(cand_ext):
            ext = cand_ext
            break
    dst = dest_dir / f"{safe_id}{ext}"

    getter = http_get or requests.get
    with getter(asset.download_url, stream=True, timeout=60, headers={"User-Agent": USER_AGENT}) as r:
        if not getattr(r, "ok", False):
            raise RuntimeError(f"Download failed ({getattr(r, 'status_code', '?')}) for {asset.asset_id}")
        with open(dst, "wb") as fh:
            for chunk in r.iter_content(chunk_size=131072):
                if chunk:
                    fh.write(chunk)

    if not dst.exists() or dst.stat().st_size < 512:
        raise RuntimeError(f"Downloaded file for {asset.asset_id} is empty or corrupted.")

    asset.local_path = str(dst)
    asset.sha256 = compute_sha256(dst)
    return dst
