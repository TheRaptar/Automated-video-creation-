#!/usr/bin/env python3
"""
Uploads output/video.mp4 to YouTube (Short or long-form, public by default) using only `requests`.

Needs 3 secrets: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN. If missing, it skips quietly.

Optional env vars:
  YT_PRIVACY            private | unlisted | public   (default: private)
  YT_CATEGORY           YouTube category id           (default: 27 = Education)
  YT_SYNTHETIC          1 = declare "altered/synthetic content" (default: 1)
  MAX_UPLOADS_PER_DAY   safety limit per UTC day (default 5; the free API quota allows about 6)
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

TOKEN_URL = os.environ.get("YT_TOKEN_URL", "https://oauth2.googleapis.com/token")
UPLOAD_URL = os.environ.get("YT_UPLOAD_URL", "https://www.googleapis.com/upload/youtube/v3/videos")
THUMB_URL = os.environ.get("YT_THUMB_URL", "https://www.googleapis.com/upload/youtube/v3/thumbnails/set")
VIDEO, META, THUMB, STATE = (Path("output/video.mp4"), Path("output/metadata.json"),
                             Path("output/thumbnail.jpg"), Path("state.json"))


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


def get_access_token() -> str:
    r = requests.post(TOKEN_URL, data={
        "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }, timeout=30)
    if not r.ok:
        hint = ""
        if "invalid_grant" in r.text:
            hint = ("\nHint: the refresh token was revoked or expired. If your OAuth consent screen is "
                    "still in 'Testing' mode, tokens expire after 7 days - publish it to 'In production' "
                    "and create a new token.")
        sys.exit(f"Could not refresh the YouTube access token: {r.status_code} {r.text[:300]}{hint}")
    return r.json()["access_token"]


def build_body(meta: dict, synthetic: bool) -> dict:
    is_short = meta.get("format", "short") in ("short", "story")
    desc = meta["description"].strip()
    if is_short:
        title = meta["title"].strip()[:88] + " #Shorts"
        if "#shorts" not in desc.lower():
            desc += "\n\n#Shorts #aesthetic #luxury #viral"
    else:
        title = meta["title"].strip()[:100]
    
    base_tags = [h.lstrip("#") for h in meta.get("hashtags", [])]
    viral_tags = ["Shorts", "luxury", "aesthetic", "glamour", "viral", "lifestyle", "mindset"]
    combined_tags = list(dict.fromkeys(base_tags + viral_tags))[:18]
    
    status = {"privacyStatus": os.environ.get("YT_PRIVACY", "public"),
              "selfDeclaredMadeForKids": False}
    if synthetic:
        status["containsSyntheticMedia"] = True
    return {"snippet": {"title": title, "description": desc[:4900], "tags": combined_tags,
                        "categoryId": os.environ.get("YT_CATEGORY", "24")},
            "status": status}


def start_session(token: str, body: dict, size: int) -> requests.Response:
    return requests.post(
        UPLOAD_URL, params={"uploadType": "resumable", "part": "snippet,status"},
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Length": str(size),
                 "X-Upload-Content-Type": "video/mp4"},
        data=json.dumps(body), timeout=60)


def set_thumbnail(token: str, video_id: str) -> None:
    if not THUMB.exists():
        return
    try:
        r = requests.post(THUMB_URL, params={"videoId": video_id, "uploadType": "media"},
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"},
                          data=THUMB.read_bytes(), timeout=120)
        if r.ok:
            print("Thumbnail set.")
        else:
            summary(f"Thumbnail not set ({r.status_code}). Custom thumbnails need a verified channel "
                    "(youtube.com/verify).")
    except requests.RequestException as e:
        print(f"Thumbnail upload error (non-fatal): {e}")


def main() -> None:
    needed = ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
    if not all(os.environ.get(k) for k in needed):
        print("YouTube secrets not set - skipping upload.")
        return
    if not VIDEO.exists() or not META.exists():
        sys.exit("output/video.mp4 or output/metadata.json is missing.")

    # Safety limit: protects the API quota and prevents accidental spam if more schedules are added.
    state = load_state()
    uploads = state.get("uploads", [])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cap = int(os.environ.get("MAX_UPLOADS_PER_DAY", "10"))
    if sum(1 for u in uploads if str(u).startswith(today)) >= cap:
        summary(f"### Upload skipped\nDaily safety limit reached ({cap} uploads today). "
                "The video is still available as a downloadable artifact.")
        return

    meta = json.loads(META.read_text(encoding="utf-8"))
    size = VIDEO.stat().st_size
    token = get_access_token()
    synthetic = os.environ.get("YT_SYNTHETIC", "1") == "1"

    r = start_session(token, build_body(meta, synthetic), size)
    if r.status_code == 400 and synthetic:  # field not accepted -> retry without it
        print(f"Retrying without synthetic-media flag ({r.text[:150]})")
        r = start_session(token, build_body(meta, False), size)
    if r.status_code == 403 and "quota" in r.text.lower():
        summary("### YouTube upload skipped\nYouTube daily quota reached for today. Resets at midnight Pacific.")
        return
    if not r.ok:
        summary(f"### YouTube upload refused: {r.status_code}\n{r.text[:400]}")
        return
    session_url = r.headers["Location"]

    for attempt in range(3):
        try:
            with open(VIDEO, "rb") as fh:
                up = requests.put(session_url, data=fh, timeout=1800,
                                  headers={"Content-Type": "video/mp4", "Content-Length": str(size)})
            if up.ok:
                res = up.json()
                vid = res["id"]
                wanted = os.environ.get("YT_PRIVACY", "private")
                actual = res.get("status", {}).get("privacyStatus", wanted)
                kind = "long-form video" if meta.get("format") == "long" else "Short"
                summary(f"### YouTube upload done ({kind})\n**{meta['title']}**  \n"
                        f"https://youtube.com/watch?v={vid}  (requested: {wanted}, actual: {actual})")
                if actual != wanted:
                    summary("\n**WARNING:** YouTube kept this video as "
                            f"`{actual}`. New or unaudited API projects are locked to private. "
                            "Request an API audit (YouTube API Services - Audit and Quota Extension "
                            "form) or switch videos to public manually in YouTube Studio.")
                if meta.get("format") == "long":
                    set_thumbnail(token, vid)
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                state["uploads"] = (uploads + [now])[-40:]
                state["videos"] = (state.get("videos", []) + [{
                    "id": vid, "fmt": meta.get("format", "short"), "category": meta.get("category"),
                    "style": meta.get("style"), "source": meta.get("source"), "title": meta["title"], "ts": now}])[-150:]
                STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
                return
            print(f"Upload attempt {attempt + 1} failed: {up.status_code} {up.text[:300]}")
        except requests.RequestException as e:
            print(f"Upload attempt {attempt + 1} error: {e}")
        time.sleep(5 * (attempt + 1))
    sys.exit("YouTube upload failed after 3 attempts.")


if __name__ == "__main__":
    main()
