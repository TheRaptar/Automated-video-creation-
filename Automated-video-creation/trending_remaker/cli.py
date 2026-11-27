"""
Standalone CLI for the Optional Trending-Topic Auto-Remaker (Option 1).

Examples:
  # 1. Scan & rank viral topics only (dry-run report, generates nothing)
  python -m trending_remaker.cli --regions IN,US --niche science --scan-only

  # 2. Remake #1 viral topic using existing unmodified AI pipeline (dry-run, no upload)
  python -m trending_remaker.cli --regions IN,US --engine ai --format animated --publish none

  # 3. Remake top niche trend using verified open-license footage + opt-in YouTube upload
  python -m trending_remaker.cli --query "deep ocean discoveries" --engine open_media --publish youtube
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from .blueprint import build_remake_blueprint
from .remaker import run_remake
from .scanner import discover_viral_signals


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m trending_remaker.cli",
        description="Optional Trending-Topic Auto-Remaker for Raptar (100% Original Videos)",
    )
    p.add_argument("--regions", default="IN,US", help="Comma-separated YouTube/Trends region codes (default: IN,US).")
    p.add_argument("--niche", default="", help="Optional YouTube category niche (e.g. science, tech, education, entertainment, comedy).")
    p.add_argument("--query", default="", help="Optional search query for recent high-velocity niche videos.")
    p.add_argument("--days", type=int, default=7, help="Recency window in days for niche search (default: 7).")
    p.add_argument("--top", type=int, default=10, help="Number of ranked viral signals to inspect (default: 10).")
    p.add_argument("--pick", type=int, default=1, help="1-based rank index of viral signal to remake (default: 1).")
    p.add_argument(
        "--engine",
        choices=["ai", "open_media", "auto"],
        default="ai",
        help="Original video engine: 'ai' (unmodified make_video.py), 'open_media' (verified open-license clips), or 'auto'.",
    )
    p.add_argument(
        "--sources",
        default="pexels,pixabay,wikimedia,archive",
        help="Open-license sources when --engine is open_media/auto.",
    )
    p.add_argument("--max-clips", type=int, default=4, help="Max open-license clips for open_media mode.")
    p.add_argument(
        "--format",
        dest="fmt",
        choices=["auto", "short", "story", "animated", "long"],
        default="auto",
        help="Output video format (default: auto based on viral signal duration).",
    )
    p.add_argument(
        "--aspect",
        choices=["auto", "9:16", "16:9", "1:1"],
        default="auto",
        help="Output aspect ratio (default: auto).",
    )
    p.add_argument("--lang", default="en", help="Primary narration & subtitle language code (default: en).")
    p.add_argument("--style", default="story", help="Storytelling tone / BGM mood (default: story).")
    p.add_argument(
        "--music",
        choices=["procedural", "openverse", "freesound"],
        default="procedural",
        help="Background music source for open_media mode (default: procedural).",
    )
    p.add_argument("--out-dir", default="", help="Output directory for remake blueprint and open_media renders.")
    p.add_argument("--ledger", default="", help="Optional provenance ledger path for open_media mode.")
    p.add_argument("--history", default="", help="Optional path to trending_remaker_history.json.")
    p.add_argument(
        "--publish",
        choices=["none", "youtube", "instagram", "both"],
        default="none",
        help="Opt-in publish via unmodified upload_youtube.py / upload_instagram.py (default: none).",
    )
    p.add_argument("--scan-only", action="store_true", help="Print ranked viral signals & blueprint only; do not render or publish.")
    p.add_argument("--offline", action="store_true", help="Offline deterministic mode (no remote API calls).")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    regions = [r.strip().upper() for r in args.regions.split(",") if r.strip()]
    history_path = Path(args.history) if args.history else None

    print("============================================================")
    print(" Raptar Optional Trending-Topic Auto-Remaker (100% Original)")
    print(f" Regions: {','.join(regions)} | Niche: {args.niche or 'all'} | Engine: {args.engine}")
    print(f" Publish Target: {args.publish} (opt-in only)")
    print("============================================================")

    signals = discover_viral_signals(
        regions=regions,
        niche=args.niche,
        query=args.query,
        days=args.days,
        top_k=args.top,
        offline=bool(args.offline),
        remaker_history_path=history_path,
    )
    if not signals:
        print("[WARN] No new deduplicated viral signals discovered.")
        return 2

    pick_idx = min(max(args.pick - 1, 0), len(signals) - 1)
    chosen = signals[pick_idx]
    blueprint = build_remake_blueprint(
        signal=chosen,
        fmt=args.fmt,
        aspect=args.aspect,
        language=args.lang,
        style=args.style,
        offline=bool(args.offline),
    )

    print(f"\n[Top Viral Signals Discovered: {len(signals)}]")
    for i, s in enumerate(signals[:5], 1):
        marker = " <-- PICKED" if (i - 1) == pick_idx else ""
        print(f"  #{i} [{s.source}] score={s.viral_score} | {s.view_count:,} views ({s.views_per_hour:,.0f}/hr) | {s.title[:70]}{marker}")

    print("\n[Original Remake Blueprint]")
    print(f"  Archetype:      {blueprint.hook_archetype}")
    print(f"  Original Topic: {blueprint.original_topic}")
    print(f"  Original Title: {blueprint.original_title}")
    print(f"  Hook Line:      {blueprint.opening_hook_line}")
    print(f"  Format/Aspect:  {blueprint.recommended_format} ({blueprint.recommended_aspect})")

    if args.scan_only:
        report = {
            "scan_only": True,
            "signals": [s.to_dict() for s in signals],
            "selected_blueprint": blueprint.to_dict(),
        }
        print("\n" + json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    out_dir = Path(args.out_dir) if args.out_dir else None
    ledger_path = Path(args.ledger) if args.ledger else None
    result = run_remake(
        blueprint=blueprint,
        engine=args.engine,
        sources=[s.strip() for s in args.sources.split(",") if s.strip()],
        max_clips=args.max_clips,
        language=args.lang,
        music_mode=args.music,
        out_dir=out_dir,
        ledger_path=ledger_path,
        history_path=history_path,
        publish_target=args.publish,
        offline=bool(args.offline),
    )
    print(f"\n[SUCCESS] Original trending remake complete via '{result['engine']}' engine.")
    print(f"  Blueprint: {result['blueprint']}")
    print(f"  Publish:   {result['publish']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
