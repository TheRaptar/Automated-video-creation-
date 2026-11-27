"""
Standalone CLI for Optional Licensed Creator / CC-BY Discovery (Option 3).

Examples:
  # 1. Discover & rank top CC-BY YouTube videos + open-license clips (report + manifest export only)
  python -m cc_discovery.cli --query "space exploration" --discover-only --export-manifest cc_manifest.json

  # 2. Produce a transformative commentary video from top-ranked licensed clips (dry-run)
  python -m cc_discovery.cli --query "deep sea wildlife" --sources youtube_cc,archive,wikimedia,pexels --publish none

  # 3. Combine creator-approved manifest + ranked CC-BY discovery and publish to YouTube
  python -m cc_discovery.cli --query "wildlife documentary" --manifest my_creators.json --publish youtube
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from .commentary import produce_cc_commentary_video
from .discover import discover_ranked_licensed_media, export_cc_by_manifest_template


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m cc_discovery.cli",
        description="Optional Most-Viewed CC-BY & Licensed Creator Discovery Add-on for Raptar",
    )
    p.add_argument("--query", default="nature documentary", help="Topic or niche query to discover top licensed / CC-BY media.")
    p.add_argument(
        "--sources",
        default="youtube_cc,archive,wikimedia,pexels,pixabay",
        help="Comma-separated licensed sources (youtube_cc,archive,wikimedia,pexels,pixabay).",
    )
    p.add_argument("--manifest", default="", help="Optional Permission Manifest JSON with creator-approved / owned videos.")
    p.add_argument("--verify-youtube-api", action="store_true", help="Cross-check manifest YouTube entries via YouTube Data API v3.")
    p.add_argument("--days", type=int, default=30, help="Recency window in days for YouTube CC-BY discovery (default: 30).")
    p.add_argument("--limit", type=int, default=6, help="Max ranked candidates per source (default: 6).")
    p.add_argument("--max-clips", type=int, default=4, help="Max verified clips to include in rendered video (default: 4).")
    p.add_argument("--format", dest="fmt", choices=["short", "story", "animated", "long"], default="short")
    p.add_argument("--aspect", choices=["9:16", "16:9", "1:1"], default="9:16")
    p.add_argument("--lang", default="en", help="Narration & subtitle language code (default: en).")
    p.add_argument("--style", default="commentary", help="Commentary tone / BGM mood (default: commentary).")
    p.add_argument("--music", choices=["procedural", "openverse", "freesound"], default="procedural")
    p.add_argument("--out-dir", default="", help="Output directory for commentary renders & discovery reports.")
    p.add_argument("--ledger", default="", help="Optional provenance ledger path.")
    p.add_argument("--export-manifest", default="", help="Optional file path to export discovered YouTube CC-BY manifest template.")
    p.add_argument("--publish", choices=["none", "youtube", "instagram", "both"], default="none")
    p.add_argument("--discover-only", action="store_true", help="Rank & report licensed discoveries only; do not download or render.")
    p.add_argument("--offline", action="store_true", help="Offline deterministic mode (local manifest clips only).")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
    manifest_path = Path(args.manifest) if args.manifest else None
    out_dir = Path(args.out_dir) if args.out_dir else (Path(__file__).resolve().parent.parent / "cc_discovery_output")

    print("============================================================")
    print(" Raptar Optional Licensed Creator / CC-BY Discovery (Option 3)")
    print(f" Query: {args.query} | Sources: {','.join(sources)}")
    print(f" Audio Policy: 100% original clip audio stripped (-an)")
    print(f" Publish Target: {args.publish} (opt-in only)")
    print("============================================================")

    ranked_clips, yt_cc_refs, rejected = discover_ranked_licensed_media(
        query=args.query,
        sources=sources,
        manifest_path=manifest_path,
        verify_youtube_api=bool(args.verify_youtube_api),
        days=args.days,
        limit=args.limit,
        aspect=args.aspect,
        yt_api_key=os.environ.get("YT_API_KEY", ""),
        offline=bool(args.offline),
    )

    print(f"\n[Discovery Summary] Ranked verified clips: {len(ranked_clips)} | Verified YT CC-BY refs: {len(yt_cc_refs)} | Rejected: {len(rejected)}")
    for idx, rc in enumerate(ranked_clips[:6], 1):
        print(f"  #{idx} [{rc.asset.source_provider}] score={rc.popularity_score} | {rc.asset.license_code} | {rc.asset.title[:60]}")
    for idx, ref in enumerate(yt_cc_refs[:5], 1):
        print(f"  [YT CC-BY #{idx}] {ref.view_count:,} views | {ref.channel_title} | {ref.title[:60]}")

    exported_manifest = ""
    if args.export_manifest and yt_cc_refs:
        exp_path = export_cc_by_manifest_template(yt_cc_refs, Path(args.export_manifest))
        exported_manifest = str(exp_path)
        print(f"  [Exported CC-BY Manifest Template] {exported_manifest}")

    if args.discover_only:
        report = {
            "discover_only": True,
            "query": args.query,
            "ranked_clips": [c.to_dict() for c in ranked_clips],
            "youtube_cc_by_references": [r.to_dict() for r in yt_cc_refs],
            "rejected": [r.to_dict() for r in rejected],
            "exported_manifest": exported_manifest,
        }
        print("\n" + json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if (ranked_clips or yt_cc_refs) else 2

    if not ranked_clips:
        print("\n[BLOCKED] Zero verified downloadable/local clips available for rendering. Provide --manifest or open-license sources.")
        return 2

    ledger_path = Path(args.ledger) if args.ledger else None
    result = produce_cc_commentary_video(
        query=args.query,
        ranked_clips=ranked_clips,
        yt_cc_refs=yt_cc_refs,
        max_clips=args.max_clips,
        fmt=args.fmt,
        aspect=args.aspect,
        language=args.lang,
        style=args.style,
        music_mode=args.music,
        out_dir=out_dir,
        ledger_path=ledger_path,
        publish_target=args.publish,
        offline=bool(args.offline),
    )
    prod = result["production"]
    print("\n[SUCCESS] Transformative CC-BY / licensed commentary video rendered!")
    print(f"  Topic:       {result['topic']}")
    print(f"  Video:       {prod['video']}")
    print(f"  Certificate: {prod['evidence_certificate']}")
    print(f"  Credits:     {prod['credits_proof_txt']}")
    print(f"  Publish:     {result['publish']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
