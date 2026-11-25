"""
Standalone CLI for the Optional Licensed-Media Downloader & Transformative Editor.

This add-on is 100% independent of Raptar's existing pipeline (`make_video.py`,
`daily.yml`, `server.ts`, `upload_youtube.py`, `upload_instagram.py`).

Examples:
  # 1. Open-license APIs (Pexels, Pixabay, Wikimedia Commons, Internet Archive) — dry-run only
  python -m licensed_media.cli --mode open --query "ocean wildlife documentary" --sources pexels,pixabay,wikimedia,archive

  # 2. Verify-only audit of a Permission Manifest (downloads nothing, publishes nothing)
  python -m licensed_media.cli --mode manifest --manifest licensed_media/permission_manifest.example.json --verify-only

  # 3. Own-account Instagram Graph API + licensed open music, render without uploading
  python -m licensed_media.cli --mode own_ig --topic "Behind the scenes reel" --music openverse

  # 4. Hybrid mode (manifest + open APIs) with explicit opt-in publish to YouTube
  python -m licensed_media.cli --mode hybrid --manifest my_permissions.json --query "space nebula" --publish youtube
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from .editor import handoff_and_publish, produce_transformative_video
from .license_gate import VerifiedAsset
from .sources import (
    download_verified_asset,
    fetch_freesound_audio,
    fetch_internet_archive_videos,
    fetch_openverse_audio,
    fetch_own_instagram_videos,
    fetch_pexels_videos,
    fetch_pixabay_videos,
    fetch_wikimedia_commons_videos,
    load_permission_manifest,
)


def _orientation_for_aspect(aspect: str) -> str:
    if aspect == "9:16":
        return "portrait"
    if aspect == "16:9":
        return "landscape"
    return "square"


def collect_candidates(args: argparse.Namespace) -> Tuple[List[VerifiedAsset], List[VerifiedAsset], List[VerifiedAsset]]:
    """
    Collects pre-verified video and audio assets according to `--mode`.
    Returns: (approved_videos, approved_audio, rejected_assets)
    """
    approved_videos: List[VerifiedAsset] = []
    approved_audio: List[VerifiedAsset] = []
    rejected: List[VerifiedAsset] = []

    mode = (args.mode or "open").strip().lower()
    orientation = _orientation_for_aspect(args.aspect)
    query = (args.query or args.topic or "nature cinematic").strip()
    sources = [s.strip().lower() for s in (args.sources or "pexels,pixabay,wikimedia,archive").split(",") if s.strip()]
    per_source = max(2, (args.max_clips + max(len(sources), 1) - 1) // max(len(sources), 1))

    # 1. Permission Manifest (creator-approved / self-owned YouTube, Instagram, local/cloud)
    if mode in ("manifest", "hybrid"):
        if not args.manifest:
            raise ValueError("--manifest is required when --mode is 'manifest' or 'hybrid'.")
        m_approved, m_rejected = load_permission_manifest(
            manifest_path=Path(args.manifest),
            verify_youtube_api=bool(args.verify_youtube_api),
            yt_api_key=os.environ.get("YT_API_KEY", ""),
            ig_token=os.environ.get("IG_ACCESS_TOKEN", ""),
        )
        for a in m_approved:
            if a.media_type == "audio":
                approved_audio.append(a)
            else:
                approved_videos.append(a)
        rejected.extend(m_rejected)

    # 2. Own-Account Instagram Graph API (strictly own account)
    if mode in ("own_ig", "hybrid"):
        ig_token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
        if ig_token:
            ig_assets = fetch_own_instagram_videos(
                token=ig_token,
                ig_id=os.environ.get("IG_USER_ID", ""),
                limit=args.max_clips,
            )
            for a in ig_assets:
                if a.verification_status == "approved":
                    approved_videos.append(a)
                else:
                    rejected.append(a)
        elif mode == "own_ig":
            print("[WARN] IG_ACCESS_TOKEN not set; cannot fetch own-account Instagram videos.")

    # 3. Official Open-License Video APIs
    if mode in ("open", "hybrid") and not args.offline:
        for src in sources:
            fetched: List[VerifiedAsset] = []
            if src == "pexels":
                fetched = fetch_pexels_videos(query=query, limit=per_source, orientation=orientation)
            elif src == "pixabay":
                fetched = fetch_pixabay_videos(query=query, limit=per_source)
            elif src == "wikimedia":
                fetched = fetch_wikimedia_commons_videos(query=query, limit=per_source)
            elif src in ("archive", "internet_archive"):
                fetched = fetch_internet_archive_videos(query=query, limit=per_source)
            else:
                print(f"[WARN] Unknown source '{src}' ignored (supported: pexels, pixabay, wikimedia, archive).")

            for a in fetched:
                if a.verification_status == "approved":
                    approved_videos.append(a)
                else:
                    rejected.append(a)

    # 4. Optional Open-License Audio (Openverse / Freesound CC0/CC-BY)
    music_mode = (args.music or "procedural").strip().lower()
    if music_mode in ("openverse", "freesound") and not args.offline and not approved_audio:
        music_query = f"{args.style} ambient instrumental"
        aud_fetched = (
            fetch_openverse_audio(query=music_query, limit=3)
            if music_mode == "openverse"
            else fetch_freesound_audio(query=music_query, limit=3)
        )
        for a in aud_fetched:
            if a.verification_status == "approved":
                approved_audio.append(a)
            else:
                rejected.append(a)

    return approved_videos[: max(1, args.max_clips)], approved_audio[:1], rejected


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m licensed_media.cli",
        description="Optional Licensed-Media Downloader & Transformative FFmpeg Editor Add-on for Raptar",
    )
    p.add_argument(
        "--mode",
        choices=["open", "manifest", "own_ig", "hybrid"],
        default="open",
        help="Ingestion mode: open (open-license APIs), manifest (creator permission JSON), own_ig (own IG Graph API), or hybrid.",
    )
    p.add_argument("--query", default="", help="Search query for open-license APIs.")
    p.add_argument("--topic", default="", help="Storytelling topic for narration & SEO (defaults to --query).")
    p.add_argument(
        "--sources",
        default="pexels,pixabay,wikimedia,archive",
        help="Comma-separated open-license video sources (pexels,pixabay,wikimedia,archive).",
    )
    p.add_argument("--manifest", default="", help="Path to Permission Manifest JSON file (for manifest/hybrid modes).")
    p.add_argument(
        "--verify-youtube-api",
        action="store_true",
        help="Cross-verify YouTube manifest entries against YouTube Data API v3.",
    )
    p.add_argument("--max-clips", type=int, default=4, help="Maximum approved video clips to include (default: 4).")
    p.add_argument(
        "--format",
        dest="fmt",
        choices=["short", "story", "animated", "long"],
        default="short",
        help="Output video format preset (default: short).",
    )
    p.add_argument(
        "--aspect",
        choices=["9:16", "16:9", "1:1"],
        default="9:16",
        help="Output aspect ratio (default: 9:16).",
    )
    p.add_argument("--lang", default="en", help="Narration & subtitle language code (e.g. en, hi, ta, es).")
    p.add_argument("--style", default="story", help="Storytelling style / BGM mood (e.g. story, cinematic, documentary).")
    p.add_argument(
        "--music",
        choices=["procedural", "openverse", "freesound"],
        default="procedural",
        help="Background music source: copyright-free procedural synthesis (default), openverse, or freesound (CC0/CC-BY).",
    )
    p.add_argument(
        "--out-dir",
        default="",
        help="Output directory for rendered video, metadata, and evidence certificates (default: licensed_media_output).",
    )
    p.add_argument(
        "--ledger",
        default="",
        help="Optional path to licensed_media_ledger.json (default: Automated-video-creation/licensed_media_ledger.json).",
    )
    p.add_argument(
        "--publish",
        choices=["none", "youtube", "instagram", "both"],
        default="none",
        help="Opt-in handoff to existing unmodified uploaders. Default 'none' (dry-run).",
    )
    p.add_argument(
        "--verify-only",
        action="store_true",
        help="Run fail-closed license verification report only; do not download, render, or publish.",
    )
    p.add_argument(
        "--offline",
        action="store_true",
        help="Offline mode: skip remote API calls and use local manifest files + deterministic narration/procedural audio.",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    topic = (args.topic or args.query or "Verified Licensed Story").strip()

    print("============================================================")
    print(" Raptar Optional Licensed-Media Add-on (Fail-Closed Mode)")
    print(f" Mode: {args.mode} | Format: {args.fmt} ({args.aspect}) | Lang: {args.lang}")
    print(f" Audio Policy: 100% original source audio stripped (-an)")
    print(f" Publish Target: {args.publish} (opt-in only)")
    print("============================================================")

    approved_videos, approved_audio, rejected = collect_candidates(args)

    print(f"\n[LicenseGate Summary] Approved videos: {len(approved_videos)} | Approved audio: {len(approved_audio)} | Rejected: {len(rejected)}")
    for a in approved_videos:
        print(f"  [APPROVED VIDEO] {a.asset_id} ({a.source_provider}) | License: {a.license_code} | Creator: {a.creator}")
    for a in approved_audio:
        print(f"  [APPROVED AUDIO] {a.asset_id} ({a.source_provider}) | License: {a.license_code} | Creator: {a.creator}")
    for r in rejected:
        print(f"  [REJECTED]       {r.asset_id} ({r.source_provider}) | Reason: {r.verification_reason}")

    if args.verify_only:
        summary = {
            "mode": args.mode,
            "verify_only": True,
            "approved_videos": [a.to_dict() for a in approved_videos],
            "approved_audio": [a.to_dict() for a in approved_audio],
            "rejected": [r.to_dict() for r in rejected],
        }
        print("\n" + json.dumps(summary, indent=2, ensure_ascii=False))
        return 0 if approved_videos else 2

    if not approved_videos:
        print("\n[BLOCKED] Zero approved video assets passed LicenseGate. Aborting safely.")
        return 2

    out_dir = Path(args.out_dir) if args.out_dir else (Path(__file__).resolve().parent.parent / "licensed_media_output")
    stage_dir = out_dir / "verified_downloads"
    stage_dir.mkdir(parents=True, exist_ok=True)

    downloaded_videos: List[VerifiedAsset] = []
    for v in approved_videos:
        try:
            download_verified_asset(v, stage_dir)
            downloaded_videos.append(v)
        except Exception as exc:
            print(f"  [SKIP] Could not stage {v.asset_id}: {exc}")

    if not downloaded_videos:
        print("\n[ERROR] No approved video assets could be staged locally. Aborting safely.")
        return 3

    downloaded_music: Optional[VerifiedAsset] = None
    for aud in approved_audio:
        try:
            download_verified_asset(aud, stage_dir)
            downloaded_music = aud
            break
        except Exception as exc:
            print(f"  [WARN] Could not stage audio {aud.asset_id}, falling back to copyright-free procedural BGM: {exc}")

    ledger_path = Path(args.ledger) if args.ledger else None
    production = produce_transformative_video(
        topic=topic,
        verified_videos=downloaded_videos,
        verified_music=downloaded_music,
        fmt=args.fmt,
        aspect=args.aspect,
        language=args.lang,
        style=args.style,
        out_dir=out_dir,
        ledger_path=ledger_path,
        offline=bool(args.offline),
    )

    print("\n[SUCCESS] Transformative licensed video rendered!")
    print(f"  Record ID:   {production['record_id']}")
    print(f"  Video:       {production['video']}")
    print(f"  Metadata:    {production['metadata']}")
    print(f"  Certificate: {production['evidence_certificate']}")
    print(f"  Credits:     {production['credits_proof_txt']}")
    print(f"  Stage Dir:   {production['stage_dir']}")

    if args.publish != "none":
        pub_result = handoff_and_publish(
            production=production,
            publish_target=args.publish,
            ledger_path=ledger_path,
        )
        print(f"  Published:   {pub_result}")
    else:
        print("  Publish:     skipped (--publish none; dry-run safe mode)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
