"""
Transformative Commentary Producer for Ranked Licensed & CC-BY Media.

Takes top-ranked, LicenseGate-approved clips (+ optional verified YouTube CC-BY
commentary subject references), strips 100% of original clip audio (`-an`), renders
an original narrated commentary video with safe-zone captions & copyright-free/licensed
music via `licensed_media.editor.produce_transformative_video`, automatically appends
all required CC-BY attributions to YouTube & Instagram metadata, and optionally hands
off to unmodified `upload_youtube.py` / `upload_instagram.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PARENT_DIR = Path(__file__).resolve().parent.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from licensed_media.editor import handoff_and_publish, produce_transformative_video
from licensed_media.license_gate import VerifiedAsset
from licensed_media.sources import (
    download_verified_asset,
    fetch_freesound_audio,
    fetch_openverse_audio,
)

from .discover import RankedCCReference, RankedLicensedClip


def build_commentary_topic(query: str, yt_cc_refs: List[RankedCCReference]) -> str:
    if yt_cc_refs:
        top = yt_cc_refs[0]
        return f"Breakdown & Commentary: {top.title[:75]}"
    return f"Curated Licensed Breakdown: {query.strip() or 'Top Creative Commons Discoveries'}"


def produce_cc_commentary_video(
    query: str,
    ranked_clips: List[RankedLicensedClip],
    yt_cc_refs: Optional[List[RankedCCReference]] = None,
    max_clips: int = 4,
    fmt: str = "short",
    aspect: str = "9:16",
    language: str = "en",
    style: str = "commentary",
    music_mode: str = "procedural",
    out_dir: Optional[Path] = None,
    ledger_path: Optional[Path] = None,
    publish_target: str = "none",
    offline: bool = False,
    http_get: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    """Stages top-ranked verified clips, produces transformative commentary video & credits."""
    refs = list(yt_cc_refs or [])
    out_root = out_dir or (PARENT_DIR / "cc_discovery_output")
    stage_dl = out_root / "verified_downloads"
    stage_dl.mkdir(parents=True, exist_ok=True)

    staged_videos: List[VerifiedAsset] = []
    for item in ranked_clips[: max(1, max_clips * 2)]:
        if len(staged_videos) >= max(1, max_clips):
            break
        try:
            download_verified_asset(item.asset, stage_dl, http_get=http_get)
            staged_videos.append(item.asset)
        except Exception as exc:
            print(f"  [cc_commentary] skipped clip {item.asset.asset_id}: {exc}")

    if not staged_videos:
        raise RuntimeError("No verified licensed clips could be staged for CC-BY commentary production.")

    staged_music: Optional[VerifiedAsset] = None
    if music_mode in ("openverse", "freesound") and not offline:
        m_list = (
            fetch_openverse_audio(f"{style} ambient instrumental", limit=2, http_get=http_get)
            if music_mode == "openverse"
            else fetch_freesound_audio(f"{style} ambient instrumental", limit=2, http_get=http_get)
        )
        for m in m_list:
            if m.verification_status == "approved":
                try:
                    download_verified_asset(m, stage_dl, http_get=http_get)
                    staged_music = m
                    break
                except Exception:
                    continue

    topic = build_commentary_topic(query, refs)
    prod = produce_transformative_video(
        topic=topic,
        verified_videos=staged_videos,
        verified_music=staged_music,
        fmt=fmt,
        aspect=aspect,
        language=language,
        style=style,
        out_dir=out_root,
        ledger_path=ledger_path,
        offline=offline,
    )

    # Append any verified YouTube CC-BY commentary reference attributions into metadata.json
    if refs:
        meta_path = Path(prod["metadata"])
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        ref_lines = [r.attribution_line for r in refs[:3]]
        ref_block_full = "Featured Creative Commons (CC-BY) Commentary References:\n" + "\n".join(f"- {ln}" for ln in ref_lines)
        ref_block_compact = "CC-BY Ref: " + " | ".join(ref_lines[:2])

        yt_seo = meta.get("youtube_seo") or {}
        if ref_lines[0] not in str(yt_seo.get("description") or ""):
            yt_seo["description"] = (str(yt_seo.get("description") or "") + "\n\n" + ref_block_full)[:4900]
            meta["youtube_seo"] = yt_seo
            meta["description"] = yt_seo["description"]

        ig_seo = meta.get("instagram_seo") or {}
        if ref_lines[0] not in str(ig_seo.get("caption") or ""):
            ig_seo["caption"] = (str(ig_seo.get("caption") or "") + "\n\n" + ref_block_compact)[:2200]
            meta["instagram_seo"] = ig_seo

        meta["cc_by_references"] = [r.to_dict() for r in refs[:3]]
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        prod["meta"] = meta

    pub_res = (
        handoff_and_publish(prod, publish_target=publish_target, ledger_path=ledger_path)
        if publish_target != "none"
        else {"published": [], "mode": "dry_run"}
    )
    return {
        "topic": topic,
        "production": prod,
        "cc_by_references": [r.to_dict() for r in refs[:5]],
        "publish": pub_res,
    }
