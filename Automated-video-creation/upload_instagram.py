#!/usr/bin/env python3
"""
Publishes output/video.mp4 as an Instagram Reel ("Instagram API with Instagram Login"; no Facebook Page needed).

Flow: temporary public URL on Cloudinary (free tier) -> create Reel container -> wait until processed
      -> publish -> delete the temporary file.
Long-form (landscape) videos are skipped - Reels are vertical.

Secrets: IG_ACCESS_TOKEN, CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
Recommended: IG_TOKEN_PASSPHRASE (any long random text). It lets the script keep the 60-day token
refreshed automatically: the refreshed token is stored ENCRYPTED in ig_token.enc.
Optional: IG_API_VERSION (default v23.0), MAX_IG_POSTS_PER_DAY (default 4)
"""
import base64
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

IG = os.environ.get("IG_API_BASE", f"https://graph.instagram.com/{os.environ.get('IG_API_VERSION', 'v23.0')}")
IG_ROOT = os.environ.get("IG_ROOT_BASE", "https://graph.instagram.com")
CLOUD = os.environ.get("CLOUDINARY_BASE", "https://api.cloudinary.com/v1_1")
VIDEO, META, STATE, TOKEN_FILE = (Path("output/video.mp4"), Path("output/metadata.json"),
                                  Path("state.json"), Path("ig_token.enc"))


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


# ------------------------------------------------------------ token (auto-refreshed, stored encrypted)
def _fernet():
    phrase = os.environ.get("IG_TOKEN_PASSPHRASE", "")
    if not phrase:
        return None
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        print("cryptography package missing - token cannot be stored.")
        return None
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(phrase.encode()).digest()))


def get_token():
    secret = os.environ["IG_ACCESS_TOKEN"].strip()
    fp = hashlib.sha256(secret.encode()).hexdigest()[:16]     # detects when you replace the secret
    f = _fernet()
    if f and TOKEN_FILE.exists():
        try:
            d = json.loads(f.decrypt(TOKEN_FILE.read_bytes()))
            if d.get("fp") == fp:
                return d["token"], fp, f
        except Exception:
            print("Stored token unreadable - using the secret.")
    return secret, fp, f


def refresh_token(token: str, fp: str, f) -> str:
    try:
        r = requests.get(f"{IG_ROOT}/refresh_access_token", timeout=30,
                         params={"grant_type": "ig_refresh_token", "access_token": token})
    except requests.RequestException as e:
        print(f"Token refresh skipped ({type(e).__name__}).")
        return token
    if not r.ok:                                             # e.g. token younger than 24h: fine
        print(f"Token refresh not needed/possible now: {r.status_code} {r.text[:120]}")
        return token
    new = r.json().get("access_token", token)
    days = int(r.json().get("expires_in", 0)) // 86400
    if f:
        TOKEN_FILE.write_bytes(f.encrypt(json.dumps({"fp": fp, "token": new}).encode()))
        print(f"Instagram token refreshed (valid ~{days} days) and stored encrypted.")
    else:
        summary("**Note:** add the secret IG_TOKEN_PASSPHRASE so the refreshed Instagram token can be kept. "
                f"Without it, the token expires ~{days or 60} days after you created it.")
    return new


# ------------------------------------------------------------ temporary public URL (Cloudinary free tier)
def _sign(params: dict, secret: str) -> str:
    to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return hashlib.sha1((to_sign + secret).encode()).hexdigest()


def cloud_upload(path: Path):
    cloud, key, secret = (os.environ["CLOUDINARY_CLOUD_NAME"], os.environ["CLOUDINARY_API_KEY"],
                          os.environ["CLOUDINARY_API_SECRET"])
    ts = int(time.time())
    signed = {"public_id": f"reel_{ts}", "timestamp": ts}
    with open(path, "rb") as fh:
        r = requests.post(f"{CLOUD}/{cloud}/video/upload", timeout=900, files={"file": fh},
                          data={**signed, "api_key": key, "signature": _sign(signed, secret)})
    if not r.ok:
        sys.exit(f"Cloudinary upload failed: {r.status_code} {r.text[:300]}")
    j = r.json()
    return j["secure_url"], j["public_id"]


def cloud_delete(public_id: str) -> None:
    try:
        cloud, key, secret = (os.environ["CLOUDINARY_CLOUD_NAME"], os.environ["CLOUDINARY_API_KEY"],
                              os.environ["CLOUDINARY_API_SECRET"])
        signed = {"public_id": public_id, "timestamp": int(time.time())}
        requests.post(f"{CLOUD}/{cloud}/video/destroy", timeout=60,
                      data={**signed, "api_key": key, "signature": _sign(signed, secret)})
    except Exception as e:
        print(f"(could not delete temporary file: {type(e).__name__})")


# ------------------------------------------------------------ Instagram
def api(method: str, path: str, token: str, **params):
    fn = requests.get if method == "GET" else requests.post
    kw = {"params": params} if method == "GET" else {"data": params}
    r = fn(f"{IG}/{path}", timeout=90, headers={"Authorization": f"Bearer {token}"}, **kw)
    try:
        j = r.json()
    except ValueError:
        j = {"raw": r.text[:300]}
    if not r.ok or "error" in j:
        sys.exit(f"Instagram API error on {path}: {r.status_code} {json.dumps(j)[:500]}")
    return j


def build_caption(meta: dict) -> str:
    return f"{meta['title'].strip()}\n\n{meta['description'].strip()}\n\nFollow for more! #reels"[:2200]


def main() -> None:
    needed = ("IG_ACCESS_TOKEN", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
    if not all(os.environ.get(k) for k in needed):
        print("Instagram/Cloudinary secrets not set - skipping Instagram.")
        return
    if not VIDEO.exists() or not META.exists():
        sys.exit("output/video.mp4 or output/metadata.json is missing.")
    meta = json.loads(META.read_text(encoding="utf-8"))
    if meta.get("format") == "long":
        print("Long-form video - not posted to Instagram (Reels are vertical).")
        return

    state = load_state()
    posts = state.get("ig_posts", [])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cap = int(os.environ.get("MAX_IG_POSTS_PER_DAY", "4"))
    if sum(1 for p in posts if str(p).startswith(today)) >= cap:
        summary(f"### Instagram skipped\nDaily safety limit reached ({cap} posts today).")
        return

    token, fp, f = get_token()
    token = refresh_token(token, fp, f)
    me = api("GET", "me", token, fields="user_id,username")
    ig_id = str(me.get("user_id") or me.get("id"))

    url, public_id = cloud_upload(VIDEO)
    try:
        container = api("POST", f"{ig_id}/media", token, media_type="REELS", video_url=url,
                        caption=build_caption(meta), share_to_feed="true")["id"]
        for _ in range(60):                                  # up to ~10 minutes
            st = api("GET", container, token, fields="status_code,status")
            code = st.get("status_code")
            if code == "FINISHED":
                break
            if code in ("ERROR", "EXPIRED"):
                sys.exit(f"Instagram could not process the video: {json.dumps(st)}")
            time.sleep(10)
        else:
            sys.exit("Instagram took too long to process the video.")
        media = api("POST", f"{ig_id}/media_publish", token, creation_id=container)["id"]
    finally:
        cloud_delete(public_id)

    link = ""
    try:
        link = api("GET", media, token, fields="permalink").get("permalink", "")
    except SystemExit:
        pass
    summary(f"### Instagram Reel published\n**{meta['title']}**  \n{link or media}")
    state["ig_posts"] = (posts + [datetime.now(timezone.utc).isoformat(timespec="seconds")])[-40:]
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
