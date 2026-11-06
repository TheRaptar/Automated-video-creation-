#!/usr/bin/env python3
"""
Uploads output/video.mp4 to YouTube as a Short, using only `requests` (no Google libraries).

Needs 3 secrets (see README): YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN.
If they are missing, the script skips quietly so the rest of the workflow still succeeds.

Optional env vars:
  YT_PRIVACY     private | unlisted | public   (default: private)
  YT_CATEGORY    YouTube category id           (default: 27 = Education)
  YT_SYNTHETIC   1 = declare "altered/synthetic content" (default: 1)
"""
import json
import os
import sys
import time
from pathlib import Path

import requests

TOKEN_URL = os.environ.get("YT_TOKEN_URL", "https://oauth2.googleapis.com/token")
UPLOAD_URL = os.environ.get("YT_UPLOAD_URL", "https://www.googleapis.com/upload/youtube/v3/videos")
VIDEO, META = Path("output/video.mp4"), Path("output/metadata.json")


def summary(text: str) -> None:
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


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
    title = meta["title"].strip()[:88] + " #Shorts"
    desc = meta["description"].strip()
    if "#shorts" not in desc.lower():
        desc += "\n\n#Shorts"
    tags = [h.lstrip("#") for h in meta.get("hashtags", [])][:15]
    status = {"privacyStatus": os.environ.get("YT_PRIVACY", "private"),
              "selfDeclaredMadeForKids": False}
    if synthetic:
        status["containsSyntheticMedia"] = True
    return {"snippet": {"title": title, "description": desc[:4900], "tags": tags,
                        "categoryId": os.environ.get("YT_CATEGORY", "27")},
            "status": status}


def start_session(token: str, body: dict, size: int) -> requests.Response:
    return requests.post(
        UPLOAD_URL, params={"uploadType": "resumable", "part": "snippet,status"},
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Length": str(size),
                 "X-Upload-Content-Type": "video/mp4"},
        data=json.dumps(body), timeout=60)


def main() -> None:
    needed = ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
    if not all(os.environ.get(k) for k in needed):
        print("YouTube secrets not set - skipping upload.")
        return
    if not VIDEO.exists() or not META.exists():
        sys.exit("output/video.mp4 or output/metadata.json is missing.")

    meta = json.loads(META.read_text(encoding="utf-8"))
    size = VIDEO.stat().st_size
    token = get_access_token()
    synthetic = os.environ.get("YT_SYNTHETIC", "1") == "1"

    r = start_session(token, build_body(meta, synthetic), size)
    if r.status_code == 400 and synthetic:  # field not accepted -> retry without it
        print(f"Retrying without synthetic-media flag ({r.text[:150]})")
        r = start_session(token, build_body(meta, False), size)
    if r.status_code == 403 and "quota" in r.text.lower():
        sys.exit("YouTube daily quota exceeded. It resets at midnight Pacific time.")
    if not r.ok:
        sys.exit(f"YouTube refused the upload: {r.status_code} {r.text[:500]}")
    session_url = r.headers["Location"]

    for attempt in range(3):
        try:
            with open(VIDEO, "rb") as fh:
                up = requests.put(session_url, data=fh, timeout=600,
                                  headers={"Content-Type": "video/mp4", "Content-Length": str(size)})
            if up.ok:
                res = up.json()
                vid = res["id"]
                wanted = os.environ.get("YT_PRIVACY", "private")
                actual = res.get("status", {}).get("privacyStatus", wanted)
                summary(f"### YouTube upload done\n**{meta['title']}**  \n"
                        f"https://youtube.com/shorts/{vid}  (requested: {wanted}, actual: {actual})")
                if actual != wanted:
                    summary("\n**WARNING:** YouTube kept this video as "
                            f"`{actual}`. New or unaudited API projects are locked to private. "
                            "Request an API audit (YouTube API Services - Audit and Quota Extension "
                            "form) or switch videos to public manually in YouTube Studio.")
                return
            print(f"Upload attempt {attempt + 1} failed: {up.status_code} {up.text[:300]}")
        except requests.RequestException as e:
            print(f"Upload attempt {attempt + 1} error: {e}")
        time.sleep(5 * (attempt + 1))
    sys.exit("YouTube upload failed after 3 attempts.")


if __name__ == "__main__":
    main()
