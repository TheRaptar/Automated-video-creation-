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
    is_short = meta.get("format", "short") in ("short", "story", "animated")
    lang = meta.get("language", "en")
    desc = meta["description"].strip()
    if is_short:
        title = meta["title"].strip()[:88] + " #Shorts"
        if "#shorts" not in desc.lower():
            desc += "\n\n#Shorts #AIAnimation #viral"
    else:
        title = meta["title"].strip()[:100]

    base_tags = [h.lstrip("#") for h in meta.get("hashtags", [])]
    viral_tags = ["Shorts", "AIAnimation", "storytelling", "viral", "animation"]
    combined_tags = list(dict.fromkeys(base_tags + viral_tags))[:18]

    status = {"privacyStatus": os.environ.get("YT_PRIVACY", "public"),
              "selfDeclaredMadeForKids": False}
    if synthetic:
        status["containsSyntheticMedia"] = True
    return {"snippet": {"title": title, "description": desc[:4900], "tags": combined_tags,
                        "categoryId": os.environ.get("YT_CATEGORY", "24"),
                        "defaultLanguage": lang, "defaultAudioLanguage": lang},
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


def _upload_one(video_path: Path, meta_path: Path, token: str, synthetic: bool, state: dict, cap: int) -> bool:
    uploads = state.get("uploads", [])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if sum(1 for u in uploads if str(u).startswith(today)) >= cap:
        summary(f"### Upload skipped\nDaily safety limit reached ({cap} uploads today).")
        return False

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    size = video_path.stat().st_size
    r = start_session(token, build_body(meta, synthetic), size)
    if r.status_code == 400 and synthetic:
        print(f"Retrying without synthetic-media flag ({r.text[:150]})")
        r = start_session(token, build_body(meta, False), size)
    if r.status_code == 403 and "quota" in r.text.lower():
        summary("### YouTube upload skipped\nYouTube daily quota reached for today.")
        return False
    if not r.ok:
        summary(f"### YouTube upload refused: {r.status_code}\n{r.text[:400]}")
        return False
    session_url = r.headers["Location"]

    for attempt in range(3):
        try:
            with open(video_path, "rb") as fh:
                up = requests.put(session_url, data=fh, timeout=1800,
                                  headers={"Content-Type": "video/mp4", "Content-Length": str(size)})
            if up.ok:
                res = up.json()
                vid = res["id"]
                wanted = os.environ.get("YT_PRIVACY", "private")
                actual = res.get("status", {}).get("privacyStatus", wanted)
                kind = "long-form video" if meta.get("format") == "long" else "Short"
                lang = meta.get("language", "en")
                summary(f"### YouTube upload done ({kind} | {lang})\n**{meta['title']}**  \n"
                        f"https://youtube.com/watch?v={vid}  (requested: {wanted}, actual: {actual})")
                if meta.get("format") == "long":
                    set_thumbnail(token, vid)
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                state["uploads"] = (uploads + [now])[-40:]
                state["videos"] = (state.get("videos", []) + [{
                    "id": vid, "fmt": meta.get("format", "short"), "language": lang,
                    "category": meta.get("category"), "style": meta.get("style"),
                    "source": meta.get("source"), "title": meta["title"], "ts": now}])[-150:]
                STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
                return True
            print(f"Upload attempt {attempt + 1} failed: {up.status_code} {up.text[:300]}")
        except requests.RequestException as e:
            print(f"Upload attempt {attempt + 1} error: {e}")
        time.sleep(5 * (attempt + 1))
    sys.exit("YouTube upload failed after 3 attempts.")


def main() -> None:
    needed = ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
    if not all(os.environ.get(k) for k in needed):
        print("YouTube secrets not set - skipping upload.")
        return
    if not VIDEO.exists() or not META.exists():
        sys.exit("output/video.mp4 or output/metadata.json is missing.")

    state = load_state()
    cap = int(os.environ.get("MAX_UPLOADS_PER_DAY", "10"))
    token = get_access_token()
    synthetic = os.environ.get("YT_SYNTHETIC", "1") == "1"

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
