#!/usr/bin/env python3
"""
Dual-Platform YouTube & Instagram Closed-Loop Analytics & Engagement Booster.

- Syncs YouTube video statistics (views, likes, comments) using the existing YouTube
  OAuth access token (falling back to optional YT_API_KEY if provided).
- Syncs Instagram Reels Insights (views/plays, likes, comments, shares, saved,
  avg watch time) using the existing Instagram Graph API token with graceful
  per-metric fallbacks.
- Computes a composite Engagement & Velocity Score across both platforms and updates
  bounded exploration/exploitation weights in state["weights"] across:
  (category, style, source, hook_type, duration_bucket).
- Provides scope-safe, non-fatal post-publish engagement boosters:
  YouTube auto-playlist assignment and YouTube/Instagram first-comment prompts.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import requests

YT_API_BASE = os.environ.get("YT_API_BASE", "https://www.googleapis.com/youtube/v3").rstrip("/")
IG_API_VERSION = os.environ.get("IG_API_VERSION", "v23.0")
IG_GRAPH_BASE = f"https://graph.facebook.com/{IG_API_VERSION}"


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _age_days(ts: str, now: Optional[datetime] = None) -> Optional[float]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ref = now or datetime.now(timezone.utc)
        return max(0.05, (ref - dt).total_seconds() / 86400.0)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 1. Composite Engagement Scoring
# ---------------------------------------------------------------------------
def compute_youtube_engagement_score(
    views: int,
    likes: int,
    comments: int,
    age_days: float,
) -> float:
    """
    Combines view velocity (views/day) with like rate and comment rate.
    Prevents clickbait with 0 engagement from outranking high-affinity videos.
    """
    v = max(0, int(views))
    l = max(0, int(likes))
    c = max(0, int(comments))
    days = max(0.5, float(age_days))

    velocity = v / days
    if v <= 0:
        return 0.0
    like_rate = min(0.35, l / v)
    comment_rate = min(0.15, c / v)
    # Engagement multiplier: baseline 1.0 + strong boost for likes (x6) & comments (x18)
    engagement_mult = 1.0 + (like_rate * 6.0) + (comment_rate * 18.0)
    return round(velocity * engagement_mult, 4)


def compute_instagram_engagement_score(
    plays: int,
    likes: int,
    comments: int,
    shares: int,
    saves: int,
    avg_watch_ms: int,
    age_days: float,
) -> float:
    """
    Instagram Reels ranking heavily weights watch time, shares, saves, and comments
    alongside plays/views velocity.
    """
    p = max(0, int(plays))
    l = max(0, int(likes))
    c = max(0, int(comments))
    sh = max(0, int(shares))
    sv = max(0, int(saves))
    days = max(0.5, float(age_days))

    # Even when plays insight is unavailable, reward direct interactions gracefully
    effective_views = max(p, (l + c * 3 + sh * 4 + sv * 4) * 5)
    if effective_views <= 0:
        return 0.0
    velocity = effective_views / days
    like_rate = min(0.35, l / effective_views)
    comment_rate = min(0.15, c / effective_views)
    share_rate = min(0.15, sh / effective_views)
    save_rate = min(0.20, sv / effective_views)
    # Watch time bonus: 15s average watch time gives ~1.35x boost
    watch_bonus = min(0.6, max(0.0, float(avg_watch_ms) / 40000.0))

    mult = 1.0 + (like_rate * 5.0) + (comment_rate * 15.0) + (share_rate * 22.0) + (save_rate * 20.0) + watch_bonus
    return round(velocity * mult, 4)


# ---------------------------------------------------------------------------
# 2. YouTube Statistics Sync (OAuth Token OR Optional API Key)
# ---------------------------------------------------------------------------
def sync_youtube_metrics(
    state: Dict[str, Any],
    oauth_token: str = "",
    api_key: str = "",
    http_get: Optional[Callable[..., Any]] = None,
    force: bool = False,
) -> int:
    """
    Updates views, likes, comments, and composite engagement_score for tracked
    YouTube videos in state["videos"]. Runs at most once per UTC day unless forced.
    """
    vids = [v for v in (state.get("videos") or [])[-100:] if isinstance(v, dict) and v.get("id")]
    if not vids:
        return 0
    if not force and state.get("yt_metrics_synced_date") == _today_utc():
        return 0

    token = (oauth_token or "").strip()
    key = (api_key or os.environ.get("YT_API_KEY", "")).strip()
    if not (token or key):
        return 0

    getter = http_get or requests.get
    stats_map: Dict[str, Dict[str, int]] = {}
    for i in range(0, len(vids), 50):
        ids = ",".join(str(v["id"]) for v in vids[i:i + 50])
        params: Dict[str, str] = {"part": "statistics", "id": ids}
        headers: Dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            params["key"] = key
        try:
            r = getter(f"{YT_API_BASE}/videos", params=params, headers=headers, timeout=20)
            if not getattr(r, "ok", False):
                continue
            for item in r.json().get("items", []):
                st = item.get("statistics") or {}
                stats_map[str(item["id"])] = {
                    "views": int(st.get("viewCount", 0) or 0),
                    "likes": int(st.get("likeCount", 0) or 0),
                    "comments": int(st.get("commentCount", 0) or 0),
                }
        except Exception as exc:
            print(f"  [analytics] YouTube stats sync skipped: {type(exc).__name__}")
            continue

    now = datetime.now(timezone.utc)
    updated = 0
    for v in vids:
        vid = str(v["id"])
        if vid not in stats_map:
            continue
        st = stats_map[vid]
        v["views"] = st["views"]
        v["likes"] = st["likes"]
        v["comments"] = st["comments"]
        age = _age_days(v.get("ts", ""), now=now)
        if age is not None:
            v["engagement_score"] = compute_youtube_engagement_score(
                st["views"], st["likes"], st["comments"], age
            )
        updated += 1

    if updated > 0:
        state["yt_metrics_synced_date"] = _today_utc()
        update_growth_weights(state)
        print(f"  [analytics] Synced YouTube engagement metrics for {updated} videos.")
    return updated


# ---------------------------------------------------------------------------
# 3. Instagram Reels Insights Sync (Graph API)
# ---------------------------------------------------------------------------
def _parse_ig_insights(payload: Dict[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for item in payload.get("data", []):
        name = str(item.get("name", "")).strip()
        vals = item.get("values") or []
        if not name or not vals:
            continue
        raw = vals[0].get("value", 0)
        try:
            out[name] = int(raw)
        except (TypeError, ValueError):
            pass
    return out


def sync_instagram_metrics(
    state: Dict[str, Any],
    token: str = "",
    http_get: Optional[Callable[..., Any]] = None,
    force: bool = False,
) -> int:
    """
    Fetches Instagram Reels engagement & insights (views/plays, likes, comments,
    shares, saved, ig_reels_avg_watch_time) for recent entries in state["ig_videos"].
    Degrades gracefully per metric if Meta changes metric availability or scopes.
    """
    reels = [r for r in (state.get("ig_videos") or [])[-40:] if isinstance(r, dict) and r.get("media_id")]
    if not reels or not (token or "").strip():
        return 0
    if not force and state.get("ig_metrics_synced_date") == _today_utc():
        return 0

    getter = http_get or requests.get
    now = datetime.now(timezone.utc)
    updated = 0

    for rec in reels[-25:]:  # Keep API calls light on every daily sync
        mid = str(rec["media_id"])
        likes = int(rec.get("likes", 0) or 0)
        comments = int(rec.get("comments", 0) or 0)
        plays = int(rec.get("plays", 0) or 0)
        shares = int(rec.get("shares", 0) or 0)
        saves = int(rec.get("saves", 0) or 0)
        avg_watch_ms = int(rec.get("avg_watch_ms", 0) or 0)
        touched = False

        # 1. Public engagement counts on the media node
        try:
            r_meta = getter(
                f"{IG_GRAPH_BASE}/{mid}",
                params={"fields": "like_count,comments_count", "access_token": token},
                timeout=15,
            )
            if getattr(r_meta, "ok", False):
                d = r_meta.json()
                likes = int(d.get("like_count", likes) or 0)
                comments = int(d.get("comments_count", comments) or 0)
                touched = True
        except Exception:
            pass

        # 2. Reels insights (tries modern v22/v23 metric list, falls back to core subset)
        for metric_csv in (
            "views,likes,comments,shares,saved,ig_reels_avg_watch_time",
            "plays,likes,comments,shares,saved",
            "saved,shares",
        ):
            try:
                r_ins = getter(
                    f"{IG_GRAPH_BASE}/{mid}/insights",
                    params={"metric": metric_csv, "access_token": token},
                    timeout=15,
                )
                if getattr(r_ins, "ok", False):
                    parsed = _parse_ig_insights(r_ins.json())
                    plays = parsed.get("views", parsed.get("plays", plays))
                    likes = parsed.get("likes", likes)
                    comments = parsed.get("comments", comments)
                    shares = parsed.get("shares", shares)
                    saves = parsed.get("saved", saves)
                    avg_watch_ms = parsed.get("ig_reels_avg_watch_time", avg_watch_ms)
                    touched = True
                    break
            except Exception:
                continue

        if not touched:
            continue

        rec["plays"] = plays
        rec["likes"] = likes
        rec["comments"] = comments
        rec["shares"] = shares
        rec["saves"] = saves
        rec["avg_watch_ms"] = avg_watch_ms
        age = _age_days(rec.get("ts", ""), now=now)
        if age is not None:
            rec["engagement_score"] = compute_instagram_engagement_score(
                plays, likes, comments, shares, saves, avg_watch_ms, age
            )
        updated += 1

    if updated > 0:
        state["ig_metrics_synced_date"] = _today_utc()
        update_growth_weights(state)
        print(f"  [analytics] Synced Instagram Reels insights for {updated} posts.")
    return updated


# ---------------------------------------------------------------------------
# 4. Multi-Dimensional Bandit Weight Updater (YouTube + Instagram Combined)
# ---------------------------------------------------------------------------
def update_growth_weights(
    state: Dict[str, Any],
    min_age_days: float = 1.0,
    min_samples: int = 4,
) -> Dict[str, Dict[str, float]]:
    """
    Aggregates matured engagement scores from BOTH YouTube (`videos`) and Instagram
    (`ig_videos`) to compute bounded weights (0.5..2.2) across:
    category, style, source, hook_type, duration_bucket.
    Preserves existing weights when fewer than `min_samples` scored videos exist.
    """
    now = datetime.now(timezone.utc)
    rows: List[tuple[Dict[str, Any], float]] = []

    for v in (state.get("videos") or [])[-120:]:
        if not isinstance(v, dict):
            continue
        age = _age_days(v.get("ts", ""), now=now)
        if age is None or age < min_age_days:
            continue
        score = v.get("engagement_score")
        if score is None and "views" in v:
            score = compute_youtube_engagement_score(
                int(v.get("views", 0) or 0),
                int(v.get("likes", 0) or 0),
                int(v.get("comments", 0) or 0),
                age,
            )
            v["engagement_score"] = score
        if score is not None and float(score) >= 0:
            rows.append((v, float(score)))

    for r in (state.get("ig_videos") or [])[-80:]:
        if not isinstance(r, dict):
            continue
        age = _age_days(r.get("ts", ""), now=now)
        if age is None or age < min_age_days:
            continue
        score = r.get("engagement_score")
        if score is None and any(k in r for k in ("plays", "likes", "shares", "saves")):
            score = compute_instagram_engagement_score(
                int(r.get("plays", 0) or 0),
                int(r.get("likes", 0) or 0),
                int(r.get("comments", 0) or 0),
                int(r.get("shares", 0) or 0),
                int(r.get("saves", 0) or 0),
                int(r.get("avg_watch_ms", 0) or 0),
                age,
            )
            r["engagement_score"] = score
        if score is not None and float(score) >= 0:
            rows.append((r, float(score)))

    if len(rows) < min_samples:
        return state.get("weights") or {}

    overall = (sum(s for _, s in rows) / len(rows)) or 1.0
    existing = state.get("weights") if isinstance(state.get("weights"), dict) else {}
    weights: Dict[str, Dict[str, float]] = {k: dict(v) for k, v in existing.items() if isinstance(v, dict)}

    for dim in ("category", "style", "source", "hook_type", "duration_bucket"):
        groups: Dict[str, List[float]] = {}
        for rec, sc in rows:
            val = rec.get(dim)
            if val:
                groups.setdefault(str(val), []).append(sc)
        dim_weights = dict(weights.get(dim, {}))
        for k, vals in groups.items():
            if len(vals) >= 2:
                rel = (sum(vals) / len(vals)) / overall
                dim_weights[k] = round(min(2.2, max(0.5, rel)), 2)
        if dim_weights:
            weights[dim] = dim_weights

    state["weights"] = weights
    return weights


# ---------------------------------------------------------------------------
# 5. Scope-Safe Post-Publish Engagement Boosters (Playlists & First Comment)
#    All functions are strictly non-fatal: if OAuth lacks optional scopes, they
#    log cleanly and never fail a video upload.
# ---------------------------------------------------------------------------
def maybe_assign_youtube_playlist(
    token: str,
    video_id: str,
    playlist_name: str,
    state: Dict[str, Any],
    http_get: Optional[Callable[..., Any]] = None,
    http_post: Optional[Callable[..., Any]] = None,
) -> Optional[str]:
    """Best-effort assigns a YouTube video to a genre/language series playlist."""
    if not (token and video_id and playlist_name):
        return None
    if os.environ.get("YT_AUTO_PLAYLIST", "1") != "1":
        return None

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    playlists = state.setdefault("playlists", {})
    if not isinstance(playlists, dict):
        playlists = {}
        state["playlists"] = playlists

    playlist_id = playlists.get(playlist_name)
    getter = http_get or requests.get
    poster = http_post or requests.post

    if not playlist_id:
        try:
            r_list = getter(
                f"{YT_API_BASE}/playlists",
                params={"part": "snippet", "mine": "true", "maxResults": "50"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            if getattr(r_list, "ok", False):
                for item in r_list.json().get("items", []):
                    title = (item.get("snippet") or {}).get("title", "")
                    if title.strip().lower() == playlist_name.strip().lower():
                        playlist_id = item.get("id")
                        break
        except Exception:
            pass

    if not playlist_id:
        try:
            r_create = poster(
                f"{YT_API_BASE}/playlists",
                params={"part": "snippet,status"},
                headers=headers,
                json={
                    "snippet": {
                        "title": playlist_name[:140],
                        "description": f"Watch every episode in our {playlist_name} series!",
                    },
                    "status": {"privacyStatus": "public"},
                },
                timeout=20,
            )
            if getattr(r_create, "ok", False):
                playlist_id = r_create.json().get("id")
            else:
                print(f"  [playlist] Skipped auto-create ({getattr(r_create, 'status_code', '?')} — scope optional).")
                return None
        except Exception as exc:
            print(f"  [playlist] Skipped auto-create: {type(exc).__name__}")
            return None

    if not playlist_id:
        return None

    playlists[playlist_name] = playlist_id
    try:
        r_add = poster(
            f"{YT_API_BASE}/playlistItems",
            params={"part": "snippet"},
            headers=headers,
            json={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
            timeout=20,
        )
        if getattr(r_add, "ok", False):
            print(f"  [playlist] Added video {video_id} -> '{playlist_name}' ({playlist_id})")
            return playlist_id
        print(f"  [playlist] Skipped item add ({getattr(r_add, 'status_code', '?')}).")
    except Exception as exc:
        print(f"  [playlist] Skipped item add: {type(exc).__name__}")
    return None


def maybe_post_youtube_first_comment(
    token: str,
    video_id: str,
    comment_text: str,
    http_post: Optional[Callable[..., Any]] = None,
) -> bool:
    """Best-effort posts an engagement debate prompt as the first YouTube comment."""
    if not (token and video_id and comment_text):
        return False
    if os.environ.get("AUTO_FIRST_COMMENT", "1") != "1":
        return False
    poster = http_post or requests.post
    try:
        r = poster(
            f"{YT_API_BASE}/commentThreads",
            params={"part": "snippet"},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {"snippet": {"textOriginal": comment_text[:500]}},
                }
            },
            timeout=20,
        )
        if getattr(r, "ok", False):
            print(f"  [engagement] Posted first YouTube comment on {video_id}.")
            return True
        print(f"  [engagement] YouTube first comment skipped ({getattr(r, 'status_code', '?')} — optional scope).")
    except Exception as exc:
        print(f"  [engagement] YouTube first comment skipped: {type(exc).__name__}")
    return False


def maybe_post_instagram_first_comment(
    token: str,
    media_id: str,
    comment_text: str,
    http_post: Optional[Callable[..., Any]] = None,
) -> bool:
    """Best-effort posts an engagement debate prompt as the first Instagram Reel comment."""
    if not (token and media_id and comment_text):
        return False
    if os.environ.get("AUTO_FIRST_COMMENT", "1") != "1":
        return False
    poster = http_post or requests.post
    try:
        r = poster(
            f"{IG_GRAPH_BASE}/{media_id}/comments",
            data={"message": comment_text[:500], "access_token": token},
            timeout=20,
        )
        if getattr(r, "ok", False):
            print(f"  [engagement] Posted first Instagram comment on {media_id}.")
            return True
        print(f"  [engagement] Instagram first comment skipped ({getattr(r, 'status_code', '?')} — optional scope).")
    except Exception as exc:
        print(f"  [engagement] Instagram first comment skipped: {type(exc).__name__}")
    return False
