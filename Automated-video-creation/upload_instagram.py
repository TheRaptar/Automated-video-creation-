
#!/usr/bin/env python3
"""
Publishes output/video.mp4 as an Instagram Reel using
Meta Instagram API - Unified Login.

Flow:
1. Validate the Unified Login access token.
2. Retrieve assigned Instagram professional accounts.
3. Verify the configured Instagram account.
4. Upload video temporarily to Cloudinary.
5. Create an Instagram Reel container.
6. Wait until Instagram finishes processing.
7. Publish the Reel.
8. Delete the temporary Cloudinary video.

Required GitHub Secrets:
    IG_ACCESS_TOKEN
    CLOUDINARY_CLOUD_NAME
    CLOUDINARY_API_KEY
    CLOUDINARY_API_SECRET

Optional GitHub Secrets / Variables:
    IG_USER_ID                 (defaults to your account ID)
    IG_API_VERSION             (defaults to v23.0)
    MAX_IG_POSTS_PER_DAY       (defaults to 4)
    CLOUDINARY_BASE            (defaults to official API URL)

Important:
    Unified Login uses graph.facebook.com.
    This script does not use the old Instagram Login
    refresh_access_token endpoint.
"""

import json
import os
import sys
import time
import hashlib

from datetime import datetime, timezone
from pathlib import Path

import requests


# ------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------

API_VERSION = os.environ.get("IG_API_VERSION", "v23.0")

GRAPH_BASE = os.environ.get(
    "META_GRAPH_BASE",
    "https://graph.facebook.com"
).rstrip("/")

IG_API = f"{GRAPH_BASE}/{API_VERSION}"

CLOUDINARY_BASE = os.environ.get(
    "CLOUDINARY_BASE",
    "https://api.cloudinary.com/v1_1"
).rstrip("/")

VIDEO = Path("output/video.mp4")
META = Path("output/metadata.json")
STATE = Path("state.json")

# Your Instagram professional account ID
DEFAULT_IG_USER_ID = "17841478445959177"

IG_USER_ID = os.environ.get(
    "IG_USER_ID",
    DEFAULT_IG_USER_ID
).strip()


# ------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------

def summary(message: str) -> None:
    print(message)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")

    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as file:
            file.write(message + "\n")


# ------------------------------------------------------------
# STATE MANAGEMENT
# ------------------------------------------------------------

def load_state() -> dict:
    try:
        if STATE.exists():
            data = json.loads(
                STATE.read_text(encoding="utf-8")
            )

            if isinstance(data, dict):
                return data

    except Exception as error:
        print(f"Could not load state: {type(error).__name__}")

    return {}


def save_state(state: dict) -> None:
    STATE.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8"
    )


# ------------------------------------------------------------
# ACCESS TOKEN
# ------------------------------------------------------------

def get_token() -> str:

    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()

    if not token:
        sys.exit("IG_ACCESS_TOKEN secret is missing.")

    if not token.startswith("EA"):
        print(
            "WARNING: The token does not start with EA. "
            "Verify that you generated it through Unified Login."
        )

    print("Instagram access token loaded.")
    print(f"Token prefix: {token[:2]}")
    print(f"Token length: {len(token)}")

    return token


# ------------------------------------------------------------
# INSTAGRAM API HELPER
# ------------------------------------------------------------

def api(method: str, path: str, token: str, **params) -> dict:

    method = method.upper()

    url = f"{IG_API}/{path.lstrip('/')}"

    headers = {
        "Authorization": f"Bearer {token}"
    }

    try:

        if method == "GET":

            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=90
            )

        elif method == "POST":

            response = requests.post(
                url,
                headers=headers,
                data=params,
                timeout=90
            )

        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

    except requests.RequestException as error:

        sys.exit(
            f"Instagram API connection failed: "
            f"{type(error).__name__}"
        )

    try:
        result = response.json()

    except ValueError:
        result = {
            "raw": response.text[:500]
        }

    if not response.ok or "error" in result:

        error_data = result.get("error", result)

        error_code = error_data.get("code")

        if error_code == 190:
            sys.exit(
                "Instagram access token is invalid, expired, "
                "or revoked. Generate a fresh Unified Login token "
                "and update IG_ACCESS_TOKEN in GitHub Secrets.\n"
                f"Details: {json.dumps(error_data)[:500]}"
            )

        sys.exit(
            f"Instagram API error on {path}: "
            f"HTTP {response.status_code}\n"
            f"{json.dumps(result)[:1000]}"
        )

    return result


# ------------------------------------------------------------
# INSTAGRAM ACCOUNT VALIDATION
# ------------------------------------------------------------

def get_instagram_account(token: str) -> str:

    print("\nChecking Unified Login account access...")

    # Unified Login returns the business integration user.
    # Instagram accounts shared with this integration are
    # available through assigned_instagram_accounts.

    accounts = api(
        "GET",
        "me/assigned_instagram_accounts",
        token,
        fields="id,username"
    )

    account_list = accounts.get("data", [])

    if not account_list:

        sys.exit(
            "No Instagram accounts were returned by Meta.\n"
            "Check that:\n"
            "1. The Instagram account is Business or Creator.\n"
            "2. The correct business portfolio was selected.\n"
            "3. The account was shared with your app.\n"
            "4. The token has instagram_basic permission."
        )

    print("\nInstagram accounts available:")

    for account in account_list:

        print(
            f"ID: {account.get('id')} | "
            f"Username: {account.get('username', 'Unknown')}"
        )

    # Find the configured Instagram account.

    selected = next(
        (
            account
            for account in account_list
            if str(account.get("id")) == str(IG_USER_ID)
        ),
        None
    )

    if not selected:

        available_ids = [
            str(account.get("id"))
            for account in account_list
        ]

        sys.exit(
            f"\nConfigured Instagram ID {IG_USER_ID} "
            f"was not found in the assigned accounts.\n"
            f"Available IDs: {available_ids}\n"
            "Update the IG_USER_ID GitHub Secret."
        )

    username = selected.get("username", "")

    print("\nInstagram account verified successfully.")
    print(f"Instagram ID: {IG_USER_ID}")
    print(f"Instagram Username: {username}")

    return str(selected["id"])


# ------------------------------------------------------------
# CLOUDINARY SIGNATURE
# ------------------------------------------------------------

def cloudinary_signature(params: dict, secret: str) -> str:

    signature_string = "&".join(
        f"{key}={params[key]}"
        for key in sorted(params)
    )

    signature_string += secret

    return hashlib.sha1(
        signature_string.encode("utf-8")
    ).hexdigest()


# ------------------------------------------------------------
# CLOUDINARY UPLOAD
# ------------------------------------------------------------

def cloud_upload(path: Path):

    cloud_name = os.environ["CLOUDINARY_CLOUD_NAME"]
    api_key = os.environ["CLOUDINARY_API_KEY"]
    api_secret = os.environ["CLOUDINARY_API_SECRET"]

    timestamp = int(time.time())

    public_id = f"instagram_reel_{timestamp}"

    signed_params = {
        "public_id": public_id,
        "timestamp": timestamp
    }

    signature = cloudinary_signature(
        signed_params,
        api_secret
    )

    upload_url = (
        f"{CLOUDINARY_BASE}/{cloud_name}/video/upload"
    )

    print("\nUploading video to Cloudinary...")

    with open(path, "rb") as video_file:

        response = requests.post(
            upload_url,
            timeout=900,
            files={
                "file": video_file
            },
            data={
                **signed_params,
                "api_key": api_key,
                "signature": signature
            }
        )

    if not response.ok:

        sys.exit(
            f"Cloudinary upload failed: "
            f"{response.status_code}\n"
            f"{response.text[:500]}"
        )

    result = response.json()

    video_url = result.get("secure_url")

    if not video_url:
        sys.exit("Cloudinary did not return a secure video URL.")

    uploaded_id = result.get("public_id", public_id)

    print("Cloudinary upload completed.")
    print("Temporary public video URL generated.")

    return video_url, uploaded_id


# ------------------------------------------------------------
# CLOUDINARY DELETE
# ------------------------------------------------------------

def cloud_delete(public_id: str) -> None:

    try:

        cloud_name = os.environ["CLOUDINARY_CLOUD_NAME"]
        api_key = os.environ["CLOUDINARY_API_KEY"]
        api_secret = os.environ["CLOUDINARY_API_SECRET"]

        timestamp = int(time.time())

        signed_params = {
            "public_id": public_id,
            "timestamp": timestamp
        }

        signature = cloudinary_signature(
            signed_params,
            api_secret
        )

        destroy_url = (
            f"{CLOUDINARY_BASE}/{cloud_name}/video/destroy"
        )

        response = requests.post(
            destroy_url,
            timeout=60,
            data={
                **signed_params,
                "api_key": api_key,
                "signature": signature
            }
        )

        if response.ok:

            result = response.json()

            print(
                "Cloudinary cleanup:",
                result.get("result", "completed")
            )

        else:

            print(
                "Cloudinary cleanup failed:",
                response.status_code,
                response.text[:200]
            )

    except Exception as error:

        print(
            "Could not delete temporary Cloudinary video:",
            type(error).__name__
        )


# ------------------------------------------------------------
# CAPTION
# ------------------------------------------------------------

def build_caption(metadata: dict) -> str:

    title = str(
        metadata.get("title", "")
    ).strip()

    description = str(
        metadata.get("description", "")
    ).strip()

    caption = (
        f"{title}\n\n"
        f"{description}\n\n"
        "Follow for more! #reels"
    )

    return caption[:2200]


# ------------------------------------------------------------
# CREATE INSTAGRAM REEL
# ------------------------------------------------------------

def create_reel(
    ig_id: str,
    token: str,
    video_url: str,
    caption: str
) -> str:

    print("\nCreating Instagram Reel container...")

    result = api(
        "POST",
        f"{ig_id}/media",
        token,
        media_type="REELS",
        video_url=video_url,
        caption=caption,
        share_to_feed="true"
    )

    container_id = result.get("id")

    if not container_id:
        sys.exit("Instagram did not return a Reel container ID.")

    print(f"Reel container created: {container_id}")

    return container_id


# ------------------------------------------------------------
# WAIT FOR INSTAGRAM PROCESSING
# ------------------------------------------------------------

def wait_for_processing(
    container_id: str,
    token: str
) -> None:

    print("\nWaiting for Instagram video processing...")

    max_attempts = 60

    for attempt in range(1, max_attempts + 1):

        status = api(
            "GET",
            container_id,
            token,
            fields="status_code,status"
        )

        code = status.get("status_code")

        message = status.get("status", "")

        print(
            f"Processing attempt {attempt}/{max_attempts}: "
            f"{code} - {message}"
        )

        if code == "FINISHED":

            print("Instagram video processing completed.")

            return

        if code in ("ERROR", "EXPIRED"):

            sys.exit(
                "Instagram could not process the video:\n"
                f"{json.dumps(status)}"
            )

        time.sleep(10)

    sys.exit(
        "Instagram took too long to process the video."
    )


# ------------------------------------------------------------
# PUBLISH REEL
# ------------------------------------------------------------

def publish_reel(
    ig_id: str,
    container_id: str,
    token: str
) -> str:

    print("\nPublishing Instagram Reel...")

    result = api(
        "POST",
        f"{ig_id}/media_publish",
        token,
        creation_id=container_id
    )

    media_id = result.get("id")

    if not media_id:
        sys.exit("Instagram did not return a published media ID.")

    print(f"Instagram Reel published successfully: {media_id}")

    return media_id


# ------------------------------------------------------------
# GET PUBLISHED REEL LINK
# ------------------------------------------------------------

def get_permalink(
    media_id: str,
    token: str
) -> str:

    try:

        result = api(
            "GET",
            media_id,
            token,
            fields="permalink"
        )

        return result.get("permalink", "")

    except SystemExit as error:

        print(
            "Could not retrieve Reel permalink:",
            str(error)[:300]
        )

        return ""


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():

    print("=" * 60)
    print("INSTAGRAM REEL AUTOMATION")
    print("Meta Instagram API - Unified Login")
    print("=" * 60)

    # Validate required secrets.

    required_secrets = (
        "IG_ACCESS_TOKEN",
        "CLOUDINARY_CLOUD_NAME",
        "CLOUDINARY_API_KEY",
        "CLOUDINARY_API_SECRET"
    )

    missing = [
        key
        for key in required_secrets
        if not os.environ.get(key, "").strip()
    ]

    if missing:

        print(
            "Instagram publishing skipped. "
            "Missing secrets:",
            ", ".join(missing)
        )

        return

    # Validate video and metadata.

    if not VIDEO.exists():

        sys.exit("output/video.mp4 is missing.")

    if not META.exists():

        sys.exit("output/metadata.json is missing.")

    try:

        metadata = json.loads(
            META.read_text(encoding="utf-8")
        )

    except Exception as error:

        sys.exit(
            f"Could not read metadata.json: "
            f"{type(error).__name__}"
        )

    if not isinstance(metadata, dict):

        sys.exit("metadata.json must contain a JSON object.")

    # Skip long-form videos.

    if metadata.get("format") == "long":

        print(
            "Long-form video detected. "
            "Skipping Instagram Reels publishing."
        )

        return

    # Daily posting safety limit.

    state = load_state()

    posts = state.get("ig_posts", [])

    if not isinstance(posts, list):
        posts = []

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    daily_limit = int(
        os.environ.get("MAX_IG_POSTS_PER_DAY", "4")
    )

    if daily_limit < 1:

        sys.exit("MAX_IG_POSTS_PER_DAY must be at least 1.")

    today_posts = sum(
        1
        for post in posts
        if str(post).startswith(today)
    )

    if today_posts >= daily_limit:

        summary(
            "### Instagram publishing skipped\n"
            f"Daily safety limit reached: {daily_limit} posts."
        )

        return

    # Get and validate token.

    token = get_token()

    # Verify the assigned Instagram account.

    ig_id = get_instagram_account(token)

    # Upload video and publish.

    video_url, public_id = cloud_upload(VIDEO)

    media_id = None

    try:

        caption = build_caption(metadata)

        container_id = create_reel(
            ig_id,
            token,
            video_url,
            caption
        )

        wait_for_processing(
            container_id,
            token
        )

        media_id = publish_reel(
            ig_id,
            container_id,
            token
        )

    finally:

        # Delete temporary Cloudinary video,
        # even if Instagram publishing fails.

        cloud_delete(public_id)

    # Retrieve published Reel URL.

    permalink = get_permalink(
        media_id,
        token
    )

    # Update posting history only after publishing.

    timestamp = datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")

    state["ig_posts"] = (
        posts + [timestamp]
    )[-40:]

    save_state(state)

    # GitHub Actions summary.

    summary(
        "### Instagram Reel published successfully\n"
        f"**Title:** {metadata.get('title', 'Untitled')}\n"
        f"**Instagram ID:** {ig_id}\n"
        f"**Media ID:** {media_id}\n"
        f"**Reel URL:** {permalink or media_id}"
    )

    print("\n" + "=" * 60)
    print("INSTAGRAM REEL PUBLISHING COMPLETED")
    print("=" * 60)


# ------------------------------------------------------------
# ENTRY POINT
# ------------------------------------------------------------

if __name__ == "__main__":
    main()
