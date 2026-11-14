#!/usr/bin/env python3
"""
Uploads output/video.mp4 to YouTube (Short or long-form separated) with:
  - YouTube Analytics API v2 sync & closed-loop learning feedback
  - Pre-upload QC threshold guard & duplicate-upload protection
  - Clean SEO tags/categoryId (zero #viral tag spam)
  - Custom thumbnail upload + retry/backoff + structured publish_logs

Needs 3 secrets: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN. If missing, skips quietly.

Optional env vars:
  YT_PRIVACY            private | unlisted | public   (default: public)
  YT_CATEGORY           override YouTube category id
  YT_SYNTHETIC          1 = declare "altered/synthetic content" (default: 1)
  MAX_SHORTS_PER_DAY    daily Shorts/Reels upload cap (default: 2)
  MAX_LONG_PER_DAY      daily Long-form upload cap (default: 1)
  MAX_UPLOADS_PER_DAY   overall safety cap per UTC day (default: 4)
  QC_STRICT             1 = block upload if QC score < QC_MIN_SCORE (default: 1)
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    import growth_engine
except ImportError:
    growth_engine = None

TOKEN_URL = os.environ.get("YT_TOKEN_URL", "https://oauth2.googleapis.com/token")
UPLOAD_URL = os.environ.get("YT_UPLOAD_URL", "https://www.googleapis.com/upload/youtube/v3/videos")
THUMB_URL = os.environ.get("YT_THUMB_URL", "https://www.googleapis.com/upload/youtube/v3/thumbnails/set")
VIDEO, META, THUMB, STATE = (
    Path("output/video.mp4"),
    Path("output/metadata.json"),
    Path("output/thumbnail.jpg"),
    Path("state.json"),
)


def summary(text: str) -> None:
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def load_state() -> dict:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _log_publish(state: dict, entry: dict) -> None:
    logs = list(state.get("publish_logs") or [])
    logs.append({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry})
    state["publish_logs"] = logs[-100:]
    save_state(state)


def get_access_token() -> str:
    r = requests.post(
        TOKEN_URL,
        data={
            "client_id": os.environ["YT_CLIENT_ID"],
            "client_secret": os.environ["YT_CLIENT_SECRET"],
            "refresh_token": os.environ["YT_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if not r.ok:
        hint = ""
        if "invalid_grant" in r.text:
            hint = (
                "\nHint: the refresh token was revoked or expired. If your OAuth consent screen is "
                "still in 'Testing' mode, tokens expire after 7 days - publish it to 'In production' "
                "and create a new token."
            )
        sys.exit(f"Could not refresh the YouTube access token: {r.status_code} {r.text[:300]}{hint}")
    return r.json()["access_token"]


def _norm_words(text: str) -> set[str]:
    stop = {"the", "and", "for", "with", "that", "this", "shorts", "video"}
    return {w for w in re.findall(r"[a-z0-9\u0080-\uffff]{3,}", (text or "").lower()) if w not in stop}


def is_duplicate_upload(meta: dict, state: dict, threshold: float = 0.72) -> bool:
    """Prevents accidentally uploading duplicate or near-identical videos already published."""
    title_cand = _norm_words(meta.get("title", ""))
    topic_cand = _norm_words(meta.get("topic", ""))
    lang = meta.get("language", "en")
    for prev in (state.get("videos") or [])[-120:]:
        if prev.get("language", "en") != lang:
            continue
        prev_title = _norm_words(prev.get("title", ""))
        prev_topic = _norm_words(prev.get("topic", ""))
        if title_cand and prev_title:
            jac_t = len(title_cand & prev_title) / max(1, len(title_cand | prev_title))
            if jac_t >= threshold:
                return True
        if topic_cand and prev_topic:
            jac_p = len(topic_cand & prev_topic) / max(1, len(topic_cand | prev_topic))
            if jac_p >= threshold:
                return True
    return False


def check_qc_gate(meta: dict) -> tuple[bool, str]:
    """Verifies quality score meets minimum publishing bar before touching YouTube API quota."""
    strict = os.environ.get("QC_STRICT", "1") == "1"
    min_score = float(os.environ.get("QC_MIN_SCORE", "6.5"))
    qc = meta.get("qc") or {}
    if not strict or not qc:
        return True, "QC passed or no gate data"
    score = float(qc.get("overall_score") or 0.0)
    passed = qc.get("passed", True)
    if not passed or score < min_score:
        return False, f"QC score {score}/10 below threshold {min_score}"
    return True, f"QC passed ({score}/10)"


def build_body(meta: dict, synthetic: bool) -> dict:
    fmt = meta.get("format", "short")
    is_short = fmt in ("short", "story", "animated")
    lang = meta.get("language", "en")
    seo = meta.get("seo") or {}
    desc = str(meta.get("description") or "").strip()
    raw_title = str(seo.get("selected_title") or meta.get("title") or "Untitled").strip()

    if is_short:
        if "#shorts" not in raw_title.lower():
            title = raw_title[:88] + " #Shorts"
        else:
            title = raw_title[:100]
        if "#shorts" not in desc.lower():
            desc += "\n\n#Shorts #Storytelling"
    else:
        title = raw_title[:100]

    seo_tags = [str(t).strip() for t in (seo.get("tags") or []) if str(t).strip()]
    base_tags = [str(h).lstrip("#").strip() for h in (meta.get("hashtags") or []) if "viral" not in str(h).lower()]
    kw_tags = [str(k).strip() for k in (seo.get("search_keywords") or []) if str(k).strip()]
    combined_tags = list(
        dict.fromkeys([t for t in (base_tags + seo_tags + kw_tags) if t and "viral" not in t.lower()])
    )[:18]
    if is_short and "Shorts" not in combined_tags:
        combined_tags.insert(0, "Shorts")

    # Resolve category cleanly while staying compatible with custom YT_CATEGORY override
    cat_id = os.environ.get("YT_CATEGORY") or seo.get("category_id") or "24"

    status = {
        "privacyStatus": os.environ.get("YT_PRIVACY", "public"),
        "selfDeclaredMadeForKids": False,
    }
    if synthetic:
        status["containsSyntheticMedia"] = True
    return {
        "snippet": {
            "title": title,
            "description": desc[:4900],
            "tags": combined_tags,
            "categoryId": str(cat_id),
            "defaultLanguage": lang,
            "defaultAudioLanguage": lang,
        },
        "status": status,
    }


def start_session(token: str, body: dict, size: int) -> requests.Response:
    return requests.post(
        UPLOAD_URL,
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(size),
            "X-Upload-Content-Type": "video/mp4",
        },
        data=json.dumps(body),
        timeout=60,
    )


def set_thumbnail(token: str, video_id: str, thumb_path: Path = None) -> bool:
    tp = thumb_path or THUMB
    if not tp.exists():
        return False
    for attempt in range(2):
        try:
            r = requests.post(
                THUMB_URL,
                params={"videoId": video_id, "uploadType": "media"},
                headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"},
                data=tp.read_bytes(),
                timeout=120,
            )
            if r.ok:
                print(f"Thumbnail set ({tp.name}).")
                return True
            summary(f"Thumbnail not set ({r.status_code}). Custom thumbnails require channel verification.")
            return False
        except requests.RequestException as e:
            print(f"Thumbnail upload attempt {attempt + 1} error (non-fatal): {e}")
            time.sleep(3)
    return False


def _upload_one(video_path: Path, meta_path: Path, token: str, synthetic: bool, state: dict, cap: int) -> bool:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    fmt = meta.get("format", "short")
    is_long = fmt == "long"

    uploads = state.get("uploads", [])
    if sum(1 for u in uploads if str(u).startswith(today)) >= cap:
        msg = f"Global daily safety limit reached ({cap} uploads today)."
        summary(f"### Upload skipped\n{msg}")
        _log_publish(state, {"status": "skipped_daily_cap", "format": fmt, "title": meta.get("title"), "reason": msg})
        return False

    # Separated Short vs Long daily caps
    type_key = "uploads_long" if is_long else "uploads_short"
    type_cap = int(os.environ.get("MAX_LONG_PER_DAY" if is_long else "MAX_SHORTS_PER_DAY", "1" if is_long else "2"))
    type_uploads = state.get(type_key, [])
    if sum(1 for u in type_uploads if str(u).startswith(today)) >= type_cap:
        msg = f"Daily {'Long-Form' if is_long else 'Short'} cap reached ({type_cap}/day)."
        summary(f"### Upload skipped\n{msg}")
        _log_publish(state, {"status": "skipped_type_cap", "format": fmt, "title": meta.get("title"), "reason": msg})
        return False

    # Duplicate guard
    if is_duplicate_upload(meta, state):
        msg = f"Duplicate title/topic blocked: {meta.get('title')}"
        summary(f"### Upload skipped (Duplicate Guard)\n{msg}")
        _log_publish(state, {"status": "skipped_duplicate", "format": fmt, "title": meta.get("title"), "reason": msg})
        return False

    # Pre-publish Quality Control Gate
    qc_ok, qc_reason = check_qc_gate(meta)
    if not qc_ok:
        summary(f"### Upload blocked by Quality Control\n{qc_reason}")
        _log_publish(state, {"status": "blocked_qc", "format": fmt, "title": meta.get("title"), "reason": qc_reason})
        return False

    size = video_path.stat().st_size
    body = build_body(meta, synthetic)
    r = start_session(token, body, size)
    if r.status_code == 400 and synthetic:
        print(f"Retrying without synthetic-media flag ({r.text[:150]})")
        r = start_session(token, build_body(meta, False), size)
    if r.status_code == 403 and "quota" in r.text.lower():
        summary("### YouTube upload skipped\nYouTube daily quota reached for today.")
        _log_publish(state, {"status": "skipped_quota", "format": fmt, "title": meta.get("title")})
        return False
    if not r.ok:
        summary(f"### YouTube upload refused: {r.status_code}\n{r.text[:400]}")
        _log_publish(state, {"status": "refused", "code": r.status_code, "title": meta.get("title")})
        return False

    session_url = r.headers["Location"]
    for attempt in range(3):
        try:
            with open(video_path, "rb") as fh:
                up = requests.put(
                    session_url,
                    data=fh,
                    timeout=1800,
                    headers={"Content-Type": "video/mp4", "Content-Length": str(size)},
                )
            if up.ok:
                res = up.json()
                vid = res["id"]
                wanted = os.environ.get("YT_PRIVACY", "public")
                actual = res.get("status", {}).get("privacyStatus", wanted)
                kind = "long-form video" if is_long else "Short"
                lang = meta.get("language", "en")
                summary(
                    f"### YouTube upload done ({kind} | {lang})\n**{body['snippet']['title']}**\n"
                    f"https://youtube.com/watch?v={vid} (privacy: {actual} | QC: {(meta.get('qc') or {}).get('overall_score', 'n/a')}/10)"
                )
                thumb_file = video_path.parent / "thumbnail.jpg"
                thumb_ok = set_thumbnail(token, vid, thumb_file if thumb_file.exists() else THUMB)
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                state["uploads"] = (uploads + [now])[-40:]
                state[type_key] = (type_uploads + [now])[-30:]
                state["videos"] = (
                    state.get("videos", [])
                    + [
                        {
                            "id": vid,
                            "fmt": fmt,
                            "language": lang,
                            "category": meta.get("category"),
                            "style": meta.get("style"),
                            "topic": meta.get("topic"),
                            "hook": meta.get("hook"),
                            "duration": meta.get("duration"),
                            "thumbnail_concept": (meta.get("thumbnail") or {}).get("winner"),
                            "thumbnail_set": thumb_ok,
                            "qc_score": (meta.get("qc") or {}).get("overall_score"),
                            "source": meta.get("source"),
                            "title": body["snippet"]["title"],
                            "ts": now,
                        }
                    ]
                )[-150:]
                _log_publish(
                    state,
                    {
                        "status": "published",
                        "video_id": vid,
                        "format": fmt,
                        "language": lang,
                        "title": body["snippet"]["title"],
                        "qc_score": (meta.get("qc") or {}).get("overall_score"),
                    },
                )
                return True
            print(f"Upload attempt {attempt + 1} failed: {up.status_code} {up.text[:300]}")
        except requests.RequestException as e:
            print(f"Upload attempt {attempt + 1} error: {e}")
        time.sleep(5 * (attempt + 1))

    _log_publish(state, {"status": "failed_retries", "format": fmt, "title": meta.get("title")})
    sys.exit("YouTube upload failed after 3 attempts.")


def main() -> None:
    needed = ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
    if not all(os.environ.get(k) for k in needed):
        print("YouTube secrets not set - skipping upload.")
        return
    if not VIDEO.exists() or not META.exists():
        sys.exit("output/video.mp4 or output/metadata.json is missing.")

    state = load_state()
    cap = int(os.environ.get("MAX_UPLOADS_PER_DAY", "4"))
    token = get_access_token()
    synthetic = os.environ.get("YT_SYNTHETIC", "1") == "1"

    # Sync YouTube Analytics API v2 & extract channel learnings before uploading
    if growth_engine:
        try:
            snap = growth_engine.fetch_youtube_analytics(token, state)
            learnings = growth_engine.analyze_channel_learnings(state)
            save_state(state)
            if snap.get("videos"):
                print(f"Analytics synced for {len(snap['videos'])} videos. Top style learnings: {learnings.get('winning_styles', [])}")
        except Exception as e:
            print(f"Analytics sync note (non-fatal): {type(e).__name__}: {e}")

    targets = [(VIDEO, META)]
    for lang_dir in sorted(Path("output").glob("lang_*")):
        lv, lm = lang_dir / "video.mp4", lang_dir / "metadata.json"
        if lv.exists() and lm.exists():
            targets.append((lv, lm))

    for vpath, mpath in targets:
        if not _upload_one(vpath, mpath, token, synthetic, state, cap):
            break


if __name__ == "__main__":
    main()
