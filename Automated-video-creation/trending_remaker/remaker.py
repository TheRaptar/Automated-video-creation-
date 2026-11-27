"""
Dual-Engine Original Remake Producer & Zero-Modification Uploader Bridge.

Engines:
  - `ai`: Invokes existing, unmodified `make_video.py` with the original remake topic.
  - `open_media`: Fetches verified open-license B-roll (Pexels, Pixabay, Wikimedia, Archive)
    via `licensed_media.sources`, strips 100% of original clip audio (-an), and renders
    a 100% original narrated video via `licensed_media.editor.produce_transformative_video`.
  - `auto`: Uses `open_media` if verified open clips are found, otherwise falls back to `ai`.

Publishing:
  - Default `--publish none` (safe dry-run).
  - Opt-in `--publish youtube|instagram|both` hands off directly to unmodified
    `upload_youtube.py` and/or `upload_instagram.py` (preserving existing daily caps).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
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
    fetch_internet_archive_videos,
    fetch_openverse_audio,
    fetch_pexels_videos,
    fetch_pixabay_videos,
    fetch_wikimedia_commons_videos,
)

from .blueprint import RemakeBlueprint


def record_remake_history(
    blueprint: RemakeBlueprint,
    engine_used: str,
    output_video: str,
    publish_result: Dict[str, Any],
    history_path: Optional[Path] = None,
) -> Dict[str, Any]:
    hpath = history_path or (PARENT_DIR / "trending_remaker_history.json")
    data: Dict[str, Any] = {"schema_version": "1.0", "entries": []}
    if hpath.exists():
        try:
            loaded = json.loads(hpath.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("entries"), list):
                data = loaded
        except Exception:
            pass

    entry = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_signal_id": blueprint.source_signal_id,
        "source_title": blueprint.source_title,
        "source_provider": blueprint.source_provider,
        "source_url": blueprint.source_url,
        "source_viral_score": blueprint.source_viral_score,
        "hook_archetype": blueprint.hook_archetype,
        "remake_topic": blueprint.original_topic,
        "remake_title": blueprint.original_title,
        "engine": engine_used,
        "output_video": output_video,
        "publish": publish_result,
    }
    data["entries"].append(entry)
    hpath.parent.mkdir(parents=True, exist_ok=True)
    hpath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return entry


def _fetch_open_clips_for_blueprint(
    blueprint: RemakeBlueprint,
    sources: List[str],
    max_clips: int = 4,
    music_mode: str = "procedural",
    http_get: Optional[Callable[..., Any]] = None,
) -> tuple[List[VerifiedAsset], Optional[VerifiedAsset]]:
    query = " ".join(blueprint.visual_keywords[:3]) or blueprint.original_topic
    orientation = "portrait" if blueprint.recommended_aspect == "9:16" else (
        "landscape" if blueprint.recommended_aspect == "16:9" else "square"
    )
    per_src = max(2, (max_clips + max(len(sources), 1) - 1) // max(len(sources), 1))
    approved: List[VerifiedAsset] = []

    for src in sources:
        s = src.strip().lower()
        fetched: List[VerifiedAsset] = []
        if s == "pexels":
            fetched = fetch_pexels_videos(query=query, limit=per_src, orientation=orientation, http_get=http_get)
        elif s == "pixabay":
            fetched = fetch_pixabay_videos(query=query, limit=per_src, http_get=http_get)
        elif s == "wikimedia":
            fetched = fetch_wikimedia_commons_videos(query=query, limit=per_src, http_get=http_get)
        elif s in ("archive", "internet_archive"):
            fetched = fetch_internet_archive_videos(query=query, limit=per_src, http_get=http_get)
        approved.extend(a for a in fetched if a.verification_status == "approved")

    music: Optional[VerifiedAsset] = None
    if music_mode in ("openverse", "freesound"):
        m_query = f"{blueprint.style} instrumental ambient"
        m_list = (
            fetch_openverse_audio(m_query, limit=2, http_get=http_get)
            if music_mode == "openverse"
            else fetch_freesound_audio(m_query, limit=2, http_get=http_get)
        )
        for m in m_list:
            if m.verification_status == "approved":
                music = m
                break

    return approved[: max(1, max_clips)], music


def _publish_existing_output(publish_target: str) -> Dict[str, Any]:
    target = (publish_target or "none").strip().lower()
    if target not in ("youtube", "instagram", "both"):
        return {"published": [], "mode": "dry_run"}
    published: List[str] = []
    if target in ("youtube", "both"):
        res = subprocess.run([sys.executable, "upload_youtube.py"], cwd=str(PARENT_DIR), check=False)
        if res.returncode == 0:
            published.append("youtube")
    if target in ("instagram", "both"):
        res = subprocess.run([sys.executable, "upload_instagram.py"], cwd=str(PARENT_DIR), check=False)
        if res.returncode == 0:
            published.append("instagram")
    return {"published": published, "mode": target}


def run_remake(
    blueprint: RemakeBlueprint,
    engine: str = "ai",
    sources: Optional[List[str]] = None,
    max_clips: int = 4,
    language: str = "en",
    music_mode: str = "procedural",
    out_dir: Optional[Path] = None,
    ledger_path: Optional[Path] = None,
    history_path: Optional[Path] = None,
    publish_target: str = "none",
    offline: bool = False,
    preverified_videos: Optional[List[VerifiedAsset]] = None,
    http_get: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    """
    Executes a 100% original remake from a `RemakeBlueprint` using either the
    unmodified Raptar AI pipeline (`make_video.py`) or verified open-license media.
    """
    eff_engine = (engine or "ai").strip().lower()
    out_root = out_dir or (PARENT_DIR / "trending_remaker_output")
    out_root.mkdir(parents=True, exist_ok=True)

    # Save the blueprint artifact alongside outputs for transparency
    bp_path = out_root / "remake_blueprint.json"
    bp_path.write_text(json.dumps(blueprint.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    # Path A: Open-license transformative FFmpeg engine
    if eff_engine in ("open_media", "auto"):
        videos: List[VerifiedAsset] = list(preverified_videos or [])
        music_asset: Optional[VerifiedAsset] = None

        if not videos and not offline:
            videos, music_asset = _fetch_open_clips_for_blueprint(
                blueprint=blueprint,
                sources=sources or ["pexels", "pixabay", "wikimedia", "archive"],
                max_clips=max_clips,
                music_mode=music_mode,
                http_get=http_get,
            )

        if videos:
            stage_dl = out_root / "verified_downloads"
            staged_videos: List[VerifiedAsset] = []
            for v in videos:
                try:
                    download_verified_asset(v, stage_dl, http_get=http_get)
                    staged_videos.append(v)
                except Exception as exc:
                    print(f"  [remaker] skipped clip {v.asset_id}: {exc}")

            if staged_videos:
                staged_music: Optional[VerifiedAsset] = None
                if music_asset is not None:
                    try:
                        download_verified_asset(music_asset, stage_dl, http_get=http_get)
                        staged_music = music_asset
                    except Exception:
                        staged_music = None

                prod = produce_transformative_video(
                    topic=blueprint.original_topic,
                    verified_videos=staged_videos,
                    verified_music=staged_music,
                    fmt=blueprint.recommended_format,
                    aspect=blueprint.recommended_aspect,
                    language=language,
                    style=blueprint.style,
                    out_dir=out_root,
                    ledger_path=ledger_path,
                    offline=offline,
                )
                pub_res = (
                    handoff_and_publish(prod, publish_target=publish_target, ledger_path=ledger_path)
                    if publish_target != "none"
                    else {"published": [], "mode": "dry_run"}
                )
                hist = record_remake_history(blueprint, "open_media", prod["video"], pub_res, history_path=history_path)
                return {
                    "engine": "open_media",
                    "blueprint": str(bp_path),
                    "production": prod,
                    "publish": pub_res,
                    "history_entry": hist,
                }
        if eff_engine == "open_media":
            raise RuntimeError("No verified open-license clips could be staged for open_media remake.")

    # Path B: Existing unmodified Raptar AI pipeline (`make_video.py`)
    env = os.environ.copy()
    env["VIDEO_FORMAT"] = blueprint.recommended_format
    env["TARGET_LANGUAGE"] = language
    if offline:
        env["OFFLINE_TEST"] = "1"
    cmd = [
        sys.executable,
        "make_video.py",
        blueprint.original_topic,
        "--format", blueprint.recommended_format,
        "--lang", language,
        "--aspect", blueprint.recommended_aspect,
    ]
    res = subprocess.run(cmd, cwd=str(PARENT_DIR), env=env, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"Unmodified make_video.py exited with status {res.returncode}")

    out_video = str(PARENT_DIR / "output" / "video.mp4")
    pub_res = _publish_existing_output(publish_target)
    hist = record_remake_history(blueprint, "ai", out_video, pub_res, history_path=history_path)
    return {
        "engine": "ai",
        "blueprint": str(bp_path),
        "video": out_video,
        "metadata": str(PARENT_DIR / "output" / "metadata.json"),
        "publish": pub_res,
        "history_entry": hist,
    }
