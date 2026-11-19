#!/usr/bin/env python3
"""
Pluggable Open-Source Video Generation, Continuation & Lip-Sync Backends.

Supports:
  - Multiple Export Aspect Ratios & Resolutions: 9:16, 16:9, 1:1 (full & draft).
  - Real Local / Colab / Kaggle ComfyUI API Client (/upload/image, /prompt,
    /history/{id}, /view) for Wan 2.2, LTX-2, FramePack, VACE, FLUX+PuLID.
  - True Last-Frame Extraction & Multi-Shot Scene Continuation so stories scale
    cleanly from 5s/15s/30s/60s to 2-minute, 5-minute, and 10-minute narratives.
  - CPU-Native 2D Rigged Multi-Character Talking Puppet Engine with real
    audio-amplitude RMS lip-sync, emotion expressions, blinking, gestures,
    environment backdrops, and Effekseer particle VFX.
  - Optional Local GPU Lip-Sync Hook (MuseTalk / LatentSync CLI when configured).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

import motion_engine as me
from audio_studio import DialogueTurn, extract_rms_lip_envelope
from character_manager import CharacterBible, CharacterProfile


ASPECT_PRESETS: Dict[str, Dict[str, Tuple[int, int]]] = {
    "9:16": {"high": (1080, 1920), "draft": (720, 1280)},
    "16:9": {"high": (1920, 1080), "draft": (1280, 720)},
    "1:1": {"high": (1080, 1080), "draft": (720, 720)},
}


def resolve_dimensions(aspect: str = "9:16", quality: str = "high") -> Tuple[int, int]:
    a = aspect if aspect in ASPECT_PRESETS else "9:16"
    q = "draft" if quality == "draft" else "high"
    return ASPECT_PRESETS[a][q]


# ============================================================================
# 1. Last-Frame / First-Frame Extraction for True Scene Continuation
# ============================================================================

def extract_last_frame(video_path: Path, out_png: Path) -> bool:
    """Extracts the final frame of a rendered shot to seed Shot N+1 I2V continuation."""
    video_path, out_png = Path(video_path), Path(out_png)
    if not video_path.exists():
        return False
    out_png.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["ffmpeg", "-y", "-sseof", "-0.12", "-i", str(video_path), "-update", "1", "-frames:v", "1", str(out_png)],
        capture_output=True, text=True, timeout=30,
    )
    return r.returncode == 0 and out_png.exists() and out_png.stat().st_size > 1000


def extract_first_frame(video_path: Path, out_png: Path) -> bool:
    """Extracts the first frame of a video clip for reference consistency checks."""
    video_path, out_png = Path(video_path), Path(out_png)
    if not video_path.exists():
        return False
    out_png.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-frames:v", "1", str(out_png)],
        capture_output=True, text=True, timeout=30,
    )
    return r.returncode == 0 and out_png.exists() and out_png.stat().st_size > 1000


# ============================================================================
# 2. Real Local / Colab / Kaggle ComfyUI Backend (Wan 2.2 / LTX-2 / FramePack)
# ============================================================================

class ComfyUIBackend:
    """
    Production client for a self-hosted ComfyUI API server (`Comfy-Org/ComfyUI`).
    Supports custom workflow JSON templates via `LOCAL_COMFY_WORKFLOW` containing
    placeholders `{{PROMPT}}`, `{{NEGATIVE_PROMPT}}`, `{{SEED}}`, `{{INPUT_IMAGE}}`,
    `{{WIDTH}}`, `{{HEIGHT}}`.
    """

    def __init__(self, base_url: Optional[str] = None, workflow_path: Optional[str] = None) -> None:
        self.base_url = (base_url or os.environ.get("LOCAL_COMFY_URL", "")).strip().rstrip("/")
        self.workflow_path = (workflow_path or os.environ.get("LOCAL_COMFY_WORKFLOW", "")).strip()

    def is_available(self) -> bool:
        if not self.base_url:
            return False
        try:
            r = requests.get(f"{self.base_url}/system_stats", timeout=4)
            return r.ok
        except Exception:
            return False

    def upload_image(self, img_path: Path) -> Optional[str]:
        if not (self.base_url and img_path.exists()):
            return None
        try:
            with open(img_path, "rb") as fh:
                r = requests.post(
                    f"{self.base_url}/upload/image",
                    files={"image": (img_path.name, fh, "image/png")},
                    data={"overwrite": "true"},
                    timeout=30,
                )
            if r.ok:
                return r.json().get("name")
        except Exception as e:
            print(f"  [ComfyUI] Upload failed: {type(e).__name__}: {e}")
        return None

    def run_workflow(
        self,
        prompt_text: str,
        out_path: Path,
        width: int,
        height: int,
        seed: int = 42,
        input_image: Optional[Path] = None,
        timeout: int = 240,
    ) -> bool:
        """Executes a user-provided ComfyUI API workflow JSON and downloads the resulting video/image."""
        if not (self.is_available() and self.workflow_path and Path(self.workflow_path).exists()):
            return False
        uploaded_name = self.upload_image(input_image) if (input_image and input_image.exists()) else ""
        try:
            raw_wf = Path(self.workflow_path).read_text(encoding="utf-8")
            raw_wf = (
                raw_wf.replace("{{PROMPT}}", json.dumps(prompt_text)[1:-1])
                .replace("{{NEGATIVE_PROMPT}}", "blurry, deformed, watermark, text, low quality")
                .replace("{{SEED}}", str(seed))
                .replace("{{INPUT_IMAGE}}", uploaded_name)
                .replace("{{WIDTH}}", str(width))
                .replace("{{HEIGHT}}", str(height))
            )
            wf_json = json.loads(raw_wf)
            sub = requests.post(f"{self.base_url}/prompt", json={"prompt": wf_json}, timeout=30)
            if not sub.ok:
                return False
            prompt_id = sub.json().get("prompt_id")
            if not prompt_id:
                return False

            deadline = time.time() + timeout
            while time.time() < deadline:
                h = requests.get(f"{self.base_url}/history/{prompt_id}", timeout=15)
                if h.ok:
                    data = h.json().get(prompt_id)
                    if data and data.get("outputs"):
                        for node_out in data["outputs"].values():
                            for key in ("gifs", "videos", "images"):
                                items = node_out.get(key) or []
                                if items:
                                    finfo = items[0]
                                    params = {
                                        "filename": finfo["filename"],
                                        "subfolder": finfo.get("subfolder", ""),
                                        "type": finfo.get("type", "output"),
                                    }
                                    dl = requests.get(f"{self.base_url}/view", params=params, stream=True, timeout=60)
                                    if dl.ok:
                                        with open(out_path, "wb") as out_fh:
                                            for chunk in dl.iter_content(1 << 16):
                                                out_fh.write(chunk)
                                        return out_path.exists() and out_path.stat().st_size > 1000
                time.sleep(2.0)
        except Exception as e:
            print(f"  [ComfyUI] Workflow error: {type(e).__name__}: {e}")
        return False


# ============================================================================
# 3. Optional Local GPU Lip-Sync Hook (MuseTalk / LatentSync CLI Bridge)
# ============================================================================

def apply_gpu_lipsync_hook(video_in: Path, audio_in: Path, video_out: Path) -> bool:
    """
    Invokes an externally installed open-source GPU lip-sync command if configured:
      - LIPSYNC_CMD='python /path/to/MuseTalk/inference.py --video {video} --audio {audio} --out {out}'
    Honest behavior: returns False immediately if no local GPU lip-sync engine is configured.
    """
    cmd_tpl = os.environ.get("LIPSYNC_CMD", "").strip()
    if not cmd_tpl:
        return False
    try:
        import shlex
        cmd_str = cmd_tpl.format(video=str(video_in), audio=str(audio_in), out=str(video_out))
        r = subprocess.run(shlex.split(cmd_str), capture_output=True, text=True, timeout=300)
        return r.returncode == 0 and video_out.exists() and video_out.stat().st_size > 1000
    except Exception as e:
        print(f"  [LipSyncHook] Skipped: {type(e).__name__}: {e}")
        return False


# ============================================================================
# 4. 2D Articulated Character Puppet + Real Audio-Amplitude Lip-Sync Engine
# ============================================================================

def _render_environment_svg(env_name: str, w: int, h: int, pal: Dict[str, str], t_sec: float, p_far: float, p_mid: float) -> str:
    """Draws rich layered vector story backdrops (skyline, forest, palace, bridge, cyber city)."""
    env = (env_name or "ancient_forest").lower()
    if any(k in env for k in ("dubai", "city", "tower", "skyscraper", "office", "street")):
        # Skyline with central tall spire + glass windows
        spire_x = w * 0.50 + p_far * 0.4
        return (
            f'<g transform="translate({p_far:.1f}, 0)" opacity="0.88">'
            f'<rect x="{w * 0.08:.1f}" y="{h * 0.44:.1f}" width="{w * 0.16:.1f}" height="{h * 0.56:.1f}" fill="{pal["far_hill"]}"/>'
            f'<rect x="{w * 0.74:.1f}" y="{h * 0.40:.1f}" width="{w * 0.19:.1f}" height="{h * 0.60:.1f}" fill="{pal["far_hill"]}"/>'
            f'<polygon points="{spire_x:.1f},{h * 0.12:.1f} {spire_x - w * 0.07:.1f},{h * 0.76:.1f} {spire_x + w * 0.07:.1f},{h * 0.76:.1f}" fill="{pal["mid_hill"]}" stroke="{pal["accent"]}" stroke-width="2"/>'
            f'<line x1="{spire_x:.1f}" y1="{h * 0.12:.1f}" x2="{spire_x:.1f}" y2="{h * 0.76:.1f}" stroke="{pal["orb"]}" stroke-width="2" opacity="0.5"/>'
            f'</g>'
            f'<rect x="-60" y="{h * 0.74:.1f}" width="{w + 120}" height="{h * 0.30:.1f}" fill="{pal["near_hill"]}"/>'
            f'<line x1="0" y1="{h * 0.74:.1f}" x2="{w}" y2="{h * 0.74:.1f}" stroke="{pal["accent"]}" stroke-width="3" opacity="0.6"/>'
        )
    if any(k in env for k in ("palace", "lobby", "room", "hall", "temple")):
        # Grand arched columns & marble floor
        return (
            f'<g opacity="0.82">'
            f'<rect x="{w * 0.06:.1f}" y="{h * 0.18:.1f}" width="{w * 0.08:.1f}" height="{h * 0.58:.1f}" fill="{pal["mid_hill"]}" stroke="{pal["accent"]}" stroke-width="2"/>'
            f'<rect x="{w * 0.86:.1f}" y="{h * 0.18:.1f}" width="{w * 0.08:.1f}" height="{h * 0.58:.1f}" fill="{pal["mid_hill"]}" stroke="{pal["accent"]}" stroke-width="2"/>'
            f'<path d="M {w * 0.14:.1f} {h * 0.30:.1f} Q {w * 0.50:.1f} {h * 0.08:.1f} {w * 0.86:.1f} {h * 0.30:.1f}" fill="none" stroke="{pal["accent"]}" stroke-width="4" opacity="0.65"/>'
            f'</g>'
            f'<rect x="-40" y="{h * 0.74:.1f}" width="{w + 80}" height="{h * 0.30:.1f}" fill="{pal["near_hill"]}"/>'
        )
    if any(k in env for k in ("ocean", "bridge", "beach", "sea", "water")):
        wave_dx = math.sin(t_sec * 2.1) * 18.0
        return (
            f'<rect x="-40" y="{h * 0.64:.1f}" width="{w + 80}" height="{h * 0.40:.1f}" fill="{pal["mid_hill"]}" opacity="0.92"/>'
            f'<path d="M {-60 + wave_dx:.1f} {h * 0.70:.1f} Q {w * 0.25 + wave_dx:.1f} {h * 0.67:.1f} {w * 0.50 + wave_dx:.1f} {h * 0.70:.1f} T {w + 60 + wave_dx:.1f} {h * 0.70:.1f}" fill="none" stroke="{pal["orb"]}" stroke-width="3" opacity="0.45"/>'
            f'<path d="M -40 {h * 0.78:.1f} Q {w * 0.50:.1f} {h * 0.72:.1f} {w + 40} {h * 0.79:.1f} L {w + 40} {h + 40} L -40 {h + 40} Z" fill="{pal["near_hill"]}"/>'
        )
    # Default: layered hills / forest silhouettes
    return (
        f'<g transform="translate({p_far:.1f}, 0)">'
        f'<path d="M -120 {h * 0.66:.1f} Q {w * 0.30:.1f} {h * 0.55:.1f} {w * 0.60:.1f} {h * 0.64:.1f} T {w + 140} {h * 0.60:.1f} L {w + 140} {h + 80} L -120 {h + 80} Z" fill="{pal["far_hill"]}" opacity="0.90"/>'
        f'</g>'
        f'<g transform="translate({p_mid:.1f}, 0)">'
        f'<path d="M -140 {h * 0.75:.1f} Q {w * 0.42:.1f} {h * 0.67:.1f} {w + 160} {h * 0.76:.1f} L {w + 160} {h + 80} L -140 {h + 80} Z" fill="{pal["near_hill"]}" opacity="0.96"/>'
        f'</g>'
    )


def _render_puppet_svg(
    char: CharacterProfile,
    cx: float,
    cy: float,
    scale: float,
    t_sec: float,
    mouth_open: float,
    is_speaking: bool,
    emotion: str = "neutral",
    facing: int = 1,
) -> str:
    """
    Renders an articulated 2D vector character rig with:
      - Audio-synced mouth openness (`mouth_open` in [0.0..1.0])
      - Emotion-driven eyebrows & eye shape
      - Periodic eye blinking + breathing bob + talking hand gesture
      - Species/archetype traits (lion mane, tiger stripes, squirrel ears/tail, robot visor, human hair)
    """
    c_skin, c_outfit, c_accent = char.color_palette
    r = 68.0 * scale
    bob = math.sin(t_sec * (7.2 if is_speaking else 2.6)) * (5.5 if is_speaking else 2.8) * scale
    head_tilt = math.sin(t_sec * (4.5 if is_speaking else 1.5)) * (3.5 if is_speaking else 1.2)
    arm_angle = (22.0 + 18.0 * math.sin(t_sec * 8.0)) if is_speaking else (4.0 * math.sin(t_sec * 2.0))

    # Periodic natural blink
    blink_cycle = (t_sec * 0.9 + (char.seed % 11) * 0.3) % 3.4
    eye_h_scale = 0.14 if blink_cycle > 3.22 else 1.0

    # Eyebrow angle by emotion
    eb_l, eb_r = 0.0, 0.0
    if emotion in ("angry", "determined"):
        eb_l, eb_r = 14.0, -14.0
    elif emotion in ("sad", "worried"):
        eb_l, eb_r = -14.0, 14.0
    elif emotion in ("shocked", "surprised"):
        eb_l, eb_r = -8.0, 8.0

    arch = (char.archetype or "human").lower()
    extras_back = ""
    extras_front = ""

    if arch in ("lion", "cub"):
        mane_r = r * (1.36 if arch == "lion" else 1.18)
        spikes = []
        for k in range(16):
            ang = k * (math.tau / 16.0)
            r_pt = mane_r if k % 2 == 0 else mane_r * 0.84
            spikes.append(f"{math.cos(ang) * r_pt:.1f},{math.sin(ang) * r_pt:.1f}")
        extras_back += f'<polygon points="{" ".join(spikes)}" fill="{c_skin}" stroke="{c_accent}" stroke-width="2.5" opacity="0.96"/>'
        if arch == "lion":
            # Signature cool sunglasses for adult lion boss vibe
            extras_front += (
                f'<rect x="{-r * 0.56:.1f}" y="{-r * 0.25:.1f}" width="{r * 0.46:.1f}" height="{r * 0.26:.1f}" rx="6" fill="#0f172a" stroke="{c_accent}" stroke-width="2" opacity="0.88"/>'
                f'<rect x="{r * 0.10:.1f}" y="{-r * 0.25:.1f}" width="{r * 0.46:.1f}" height="{r * 0.26:.1f}" rx="6" fill="#0f172a" stroke="{c_accent}" stroke-width="2" opacity="0.88"/>'
                f'<line x1="{-r * 0.10:.1f}" y1="{-r * 0.14:.1f}" x2="{r * 0.10:.1f}" y2="{-r * 0.14:.1f}" stroke="{c_accent}" stroke-width="3"/>'
            )
    elif arch == "tiger":
        extras_back += (
            f'<circle cx="{-r * 0.72:.1f}" cy="{-r * 0.72:.1f}" r="{r * 0.28:.1f}" fill="{c_skin}" stroke="#111827" stroke-width="2.5"/>'
            f'<circle cx="{r * 0.72:.1f}" cy="{-r * 0.72:.1f}" r="{r * 0.28:.1f}" fill="{c_skin}" stroke="#111827" stroke-width="2.5"/>'
        )
        extras_front += (
            f'<path d="M {-r * 0.25:.1f} {-r * 0.85:.1f} L {-r * 0.15:.1f} {-r * 0.55:.1f} M 0 {-r * 0.90:.1f} L 0 {-r * 0.55:.1f} M {r * 0.25:.1f} {-r * 0.85:.1f} L {r * 0.15:.1f} {-r * 0.55:.1f}" stroke="#111827" stroke-width="4"/>'
        )
    elif arch == "squirrel":
        extras_back += (
            f'<path d="M {r * 0.6:.1f} {r * 1.4:.1f} Q {r * 1.9:.1f} {r * 0.2:.1f} {r * 1.2:.1f} {-r * 0.7:.1f} Q {r * 0.9:.1f} {r * 0.4:.1f} {r * 0.5:.1f} {r * 1.1:.1f} Z" fill="{c_skin}" stroke="{c_accent}" stroke-width="2.5"/>'
            f'<ellipse cx="{-r * 0.58:.1f}" cy="{-r * 0.86:.1f}" rx="{r * 0.22:.1f}" ry="{r * 0.36:.1f}" fill="{c_skin}"/>'
            f'<ellipse cx="{r * 0.58:.1f}" cy="{-r * 0.86:.1f}" rx="{r * 0.22:.1f}" ry="{r * 0.36:.1f}" fill="{c_skin}"/>'
        )
    elif arch == "robot":
        extras_back += f'<line x1="0" y1="{-r:.1f}" x2="0" y2="{-r * 1.42:.1f}" stroke="{c_accent}" stroke-width="4"/><circle cx="0" cy="{-r * 1.46:.1f}" r="{r * 0.14:.1f}" fill="{c_accent}"/>'
    else:
        # Human / anime hair silhouette
        extras_back += f'<path d="M {-r * 0.95:.1f} {-r * 0.10:.1f} Q {-r * 0.80:.1f} {-r * 1.25:.1f} 0 {-r * 1.12:.1f} Q {r * 0.85:.1f} {-r * 1.22:.1f} {r * 0.95:.1f} {-r * 0.10:.1f} Z" fill="{c_outfit}" stroke="{c_accent}" stroke-width="2"/>'

    # Lip-sync mouth geometry driven by real audio RMS [0.0..1.0]
    m_y = r * 0.36
    if is_speaking and mouth_open > 0.08:
        m_rx = r * (0.18 + 0.16 * mouth_open)
        m_ry = r * (0.06 + 0.24 * mouth_open)
        mouth_svg = (
            f'<ellipse cx="0" cy="{m_y:.1f}" rx="{m_rx:.1f}" ry="{m_ry:.1f}" fill="#3b0a18" stroke="#111827" stroke-width="2.5"/>'
            f'<ellipse cx="0" cy="{m_y + m_ry * 0.45:.1f}" rx="{m_rx * 0.55:.1f}" ry="{m_ry * 0.30:.1f}" fill="#ef4444" opacity="0.85"/>'
        )
    elif emotion in ("happy", "confident"):
        mouth_svg = f'<path d="M {-r * 0.28:.1f} {m_y - 3:.1f} Q 0 {m_y + r * 0.22:.1f} {r * 0.28:.1f} {m_y - 3:.1f}" fill="none" stroke="#111827" stroke-width="4" stroke-linecap="round"/>'
    elif emotion in ("shocked", "surprised"):
        mouth_svg = f'<circle cx="0" cy="{m_y:.1f}" r="{r * 0.18:.1f}" fill="#3b0a18" stroke="#111827" stroke-width="2.5"/>'
    elif emotion in ("sad", "worried"):
        mouth_svg = f'<path d="M {-r * 0.24:.1f} {m_y + 8:.1f} Q 0 {m_y - r * 0.14:.1f} {r * 0.24:.1f} {m_y + 8:.1f}" fill="none" stroke="#111827" stroke-width="3.5" stroke-linecap="round"/>'
    else:
        mouth_svg = f'<line x1="{-r * 0.22:.1f}" y1="{m_y:.1f}" x2="{r * 0.22:.1f}" y2="{m_y:.1f}" stroke="#111827" stroke-width="3.5" stroke-linecap="round"/>'

    # Body + animated arms + head group
    speak_glow = f'<circle cx="0" cy="{r * 0.35:.1f}" r="{r * 1.95:.1f}" fill="{c_accent}" opacity="0.14"/>' if is_speaking else ""
    return (
        f'<g transform="translate({cx:.1f}, {cy + bob:.1f}) scale({facing}, 1)">'
        f'{speak_glow}'
        f'<ellipse cx="0" cy="{r * 2.55:.1f}" rx="{r * 1.15:.1f}" ry="{r * 0.24:.1f}" fill="#000000" opacity="0.30"/>'
        # Torso / suit
        f'<path d="M {-r * 0.88:.1f} {r * 2.40:.1f} L {-r * 0.72:.1f} {r * 0.88:.1f} Q 0 {r * 0.65:.1f} {r * 0.72:.1f} {r * 0.88:.1f} L {r * 0.88:.1f} {r * 2.40:.1f} Z" fill="{c_outfit}" stroke="{c_accent}" stroke-width="3"/>'
        # Lapel / collar accent
        f'<polygon points="0,{r * 0.90:.1f} {-r * 0.24:.1f},{r * 1.48:.1f} {r * 0.24:.1f},{r * 1.48:.1f}" fill="{c_accent}" opacity="0.88"/>'
        # Animated gesturing right arm
        f'<g transform="translate({r * 0.72:.1f}, {r * 1.05:.1f}) rotate({-arm_angle:.1f})">'
        f'<rect x="-10" y="0" width="{r * 0.30:.1f}" height="{r * 0.98:.1f}" rx="12" fill="{c_outfit}" stroke="{c_accent}" stroke-width="2.5"/>'
        f'<circle cx="{r * 0.08:.1f}" cy="{r * 1.02:.1f}" r="{r * 0.18:.1f}" fill="{c_skin}"/>'
        f'</g>'
        # Left arm
        f'<g transform="translate({-r * 0.72:.1f}, {r * 1.05:.1f}) rotate({arm_angle * 0.35:.1f})">'
        f'<rect x="{-r * 0.20:.1f}" y="0" width="{r * 0.30:.1f}" height="{r * 0.98:.1f}" rx="12" fill="{c_outfit}" stroke="{c_accent}" stroke-width="2.5"/>'
        f'<circle cx="{-r * 0.05:.1f}" cy="{r * 1.02:.1f}" r="{r * 0.18:.1f}" fill="{c_skin}"/>'
        f'</g>'
        # Head group with gentle head tilt
        f'<g transform="rotate({head_tilt:.1f})">'
        f'{extras_back}'
        f'<circle cx="0" cy="0" r="{r:.1f}" fill="{c_skin}" stroke="{c_accent}" stroke-width="2.5"/>'
        # Eyes
        f'<ellipse cx="{-r * 0.32:.1f}" cy="{-r * 0.12:.1f}" rx="{r * 0.13:.1f}" ry="{r * 0.15 * eye_h_scale:.1f}" fill="#0f172a"/>'
        f'<ellipse cx="{r * 0.32:.1f}" cy="{-r * 0.12:.1f}" rx="{r * 0.13:.1f}" ry="{r * 0.15 * eye_h_scale:.1f}" fill="#0f172a"/>'
        f'<circle cx="{-r * 0.28:.1f}" cy="{-r * 0.16:.1f}" r="{r * 0.045 * eye_h_scale:.1f}" fill="#ffffff"/>'
        f'<circle cx="{r * 0.36:.1f}" cy="{-r * 0.16:.1f}" r="{r * 0.045 * eye_h_scale:.1f}" fill="#ffffff"/>'
        # Eyebrows
        f'<line x1="{-r * 0.48:.1f}" y1="{-r * 0.34:.1f}" x2="{-r * 0.16:.1f}" y2="{-r * 0.34:.1f}" stroke="#111827" stroke-width="4" stroke-linecap="round" transform="rotate({eb_l:.1f} {-r * 0.32:.1f} {-r * 0.34:.1f})"/>'
        f'<line x1="{r * 0.16:.1f}" y1="{-r * 0.34:.1f}" x2="{r * 0.48:.1f}" y2="{-r * 0.34:.1f}" stroke="#111827" stroke-width="4" stroke-linecap="round" transform="rotate({eb_r:.1f} {r * 0.32:.1f} {-r * 0.34:.1f})"/>'
        f'{extras_front}'
        f'{mouth_svg}'
        f'</g>'
        f'</g>'
    )


def render_talking_puppet_scene(
    out_path: Path,
    audio_path: Path,
    turns: Sequence[DialogueTurn],
    bible: CharacterBible,
    character_names: Sequence[str],
    width: int,
    height: int,
    duration: float,
    fps: int = 30,
    style: str = "animated_comedy",
    environment: str = "dubai_skyline",
    motion: str = "zoom_in",
    fx: str = "vibrant",
    idx: int = 0,
    enable_particles: bool = True,
    svg_fps: int = 15,
) -> bool:
    """
    Renders a multi-character 2D articulated animated story scene with genuine
    audio-driven lip-sync extracted from the scene's mixed dialogue audio.
    """
    duration = max(0.5, float(duration))
    rw = max(256, int(round(width * 0.5 / 2.0)) * 2)
    rh = max(256, int(round(height * 0.5 / 2.0)) * 2)
    n_frames = max(2, int(math.ceil(duration * svg_fps)))

    rms = extract_rms_lip_envelope(audio_path, fps=svg_fps, duration=duration)
    sheet = me.build_scene_motion_sheet(duration, motion=motion)
    pal = me.STYLE_PALETTES.get(style, me.STYLE_PALETTES["animated_comedy"])
    preset = me.pick_particle_preset(style, fx)
    seed = int(hashlib.md5(f"puppet:{style}:{idx}".encode("utf-8")).hexdigest()[:8], 16)
    emitter = me.ParticleEmitter(preset, rw, rh, seed=seed, count=22) if enable_particles else None

    # Resolve 1 or 2 on-stage characters from CharacterBible
    cast: List[CharacterProfile] = []
    for cname in character_names:
        prof = bible.get(cname)
        if prof and prof not in cast:
            cast.append(prof)
    if not cast and bible.characters:
        cast = list(bible.characters.values())[:2]
    if not cast:
        cast = [bible.register("Hero", archetype="human")]
    cast = cast[:2]

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"raptar_puppet_{idx}_"))
    try:
        for f_idx in range(n_frames):
            t_sec = f_idx / float(svg_fps)
            norm_t = min(1.0, t_sec / max(1e-6, duration))
            vals = sheet.sample(norm_t)
            mouth_amp = rms[f_idx] if f_idx < len(rms) else 0.0

            # Determine active speaker & emotion at timestamp t_sec
            active_speaker = ""
            active_emotion = "neutral"
            for tr in turns:
                if tr.start_sec <= t_sec <= tr.end_sec + 0.05:
                    active_speaker = tr.speaker.lower()
                    active_emotion = tr.emotion or "neutral"
                    break

            cam_s = float(vals.get("cam_scale", 1.0))
            cam_x = float(vals.get("cam_x", 0.0)) * 0.6
            cam_y = float(vals.get("cam_y", 0.0)) * 0.6
            p_far = float(vals.get("parallax_far", 0.0))
            p_mid = float(vals.get("parallax_mid", 0.0))
            half_w, half_h = rw * 0.5, rh * 0.5
            cam_tf = (
                f"translate({half_w + cam_x:.1f} {half_h + cam_y:.1f}) "
                f"scale({cam_s:.4f}) "
                f"translate({-half_w:.1f} {-half_h:.1f})"
            )

            env_svg = _render_environment_svg(environment, rw, rh, pal, t_sec, p_far, p_mid)
            puppets_svg = []
            base_scale = min(rw, rh) / 560.0
            if len(cast) == 1:
                ch = cast[0]
                sp = (not active_speaker) or (ch.name.lower() == active_speaker) or (ch.character_id == active_speaker)
                sc_ch = base_scale * (0.82 if ch.age_group == "child" else 1.05)
                puppets_svg.append(_render_puppet_svg(
                    ch, rw * 0.50, rh * 0.55, sc_ch, t_sec, mouth_amp if sp else 0.0, sp, active_emotion, facing=1
                ))
            else:
                positions = [(rw * 0.31, rh * 0.55, 1), (rw * 0.69, rh * 0.57, -1)]
                for ch, (px, py, face_dir) in zip(cast, positions):
                    sp = (ch.name.lower() == active_speaker) or (ch.character_id == active_speaker)
                    sc_ch = base_scale * (0.76 if ch.age_group == "child" else 0.98)
                    py_adj = py + (rh * 0.04 if ch.age_group == "child" else 0.0)
                    puppets_svg.append(_render_puppet_svg(
                        ch, px, py_adj, sc_ch, t_sec, mouth_amp if sp else 0.0, sp,
                        active_emotion if sp else "neutral", facing=face_dir,
                    ))

            particles_svg = emitter.render_svg_group(t_sec) if emitter else ""
            svg_frame = (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{rw}" height="{rh}" viewBox="0 0 {rw} {rh}">'
                f'<defs>'
                f'<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
                f'<stop offset="0%" stop-color="{pal["sky_top"]}"/>'
                f'<stop offset="55%" stop-color="{pal["sky_mid"]}"/>'
                f'<stop offset="100%" stop-color="{pal["sky_bot"]}"/>'
                f'</linearGradient>'
                f'</defs>'
                f'<g transform="{cam_tf}">'
                f'<rect x="-80" y="-80" width="{rw + 160}" height="{rh + 160}" fill="url(#sky)"/>'
                f'<circle cx="{rw * 0.72:.1f}" cy="{rh * 0.24:.1f}" r="{min(rw, rh) * 0.13:.1f}" fill="{pal["orb"]}" opacity="0.82"/>'
                f'{env_svg}'
                f'{"".join(puppets_svg)}'
                f'</g>'
                f'{particles_svg}'
                f'</svg>'
            )
            (tmp_dir / f"pf_{f_idx:04d}.svg").write_text(svg_frame, encoding="utf-8")

        graph = (
            me.CompositorGraph()
            .add("scale_crop", w=width, h=height, flags="bicubic")
            .add("grade", fx=fx, style=style)
            .add("fps", fps=fps)
            .add("sar")
        )
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(svg_fps),
            "-i", str(tmp_dir / "pf_%04d.svg"),
            "-t", f"{duration:.3f}",
            "-vf", graph.compile(),
            "-an",
            "-r", str(fps), "-vsync", "cfr", "-video_track_timescale", "90000",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            str(out_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 1000
    except Exception as e:
        print(f"  [VideoBackends] Talking puppet render error: {type(e).__name__}: {e}")
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
