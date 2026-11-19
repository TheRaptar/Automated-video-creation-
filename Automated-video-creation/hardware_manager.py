#!/usr/bin/env python3
"""
Hardware-Aware Detection & Open-Source Model Recommendation Engine.

Automatically inspects local CPU, RAM, disk space, NVIDIA/AMD/MPS GPUs,
Colab/Kaggle cloud runtimes, and locally available open-source binaries
(FFmpeg, Blender, Synfig, Piper, ComfyUI) to select realistic generation
backends without blindly downloading multi-gigabyte weights.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class HardwareProfile:
    os_name: str
    arch: str
    cpu_cores: int
    ram_gb: float
    disk_free_gb: float
    gpu_vendor: str = "none"          # nvidia | amd | apple | none
    gpu_name: str = ""
    vram_gb: float = 0.0
    runtime_env: str = "local"        # local | github_actions | colab | kaggle
    tier: str = "cpu_light"           # cpu_ci | cpu_local | gpu_low_vram | gpu_mid_vram | gpu_high_vram
    tools: Dict[str, bool] = field(default_factory=dict)
    comfyui_online: bool = False
    recommendations: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _detect_ram_gb() -> float:
    try:
        if Path("/proc/meminfo").exists():
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    kb = float(line.split()[1])
                    return round(kb / (1024.0 * 1024.0), 2)
    except Exception:
        pass
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        if pages > 0 and page_size > 0:
            return round((pages * page_size) / (1024.0 ** 3), 2)
    except Exception:
        pass
    return 4.0


def _detect_disk_free_gb(path: str = ".") -> float:
    try:
        usage = shutil.disk_usage(path)
        return round(usage.free / (1024.0 ** 3), 2)
    except Exception:
        return 10.0


def _detect_gpu() -> tuple[str, str, float]:
    """Detects NVIDIA (nvidia-smi), AMD ROCm (rocm-smi), or Apple Silicon MPS."""
    if shutil.which("nvidia-smi"):
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=6,
            )
            if r.returncode == 0 and r.stdout.strip():
                line = r.stdout.strip().splitlines()[0]
                parts = [p.strip() for p in line.split(",")]
                name = parts[0] if parts else "NVIDIA GPU"
                vram_mb = float(parts[1]) if len(parts) > 1 else 0.0
                return "nvidia", name, round(vram_mb / 1024.0, 2)
        except Exception:
            pass

    if shutil.which("rocm-smi"):
        try:
            r = subprocess.run(["rocm-smi", "--showmeminfo", "vram"], capture_output=True, text=True, timeout=6)
            if r.returncode == 0 and r.stdout:
                for ln in r.stdout.splitlines():
                    if "Total Memory" in ln:
                        nums = [int(tok) for tok in ln.split() if tok.isdigit()]
                        if nums:
                            return "amd", "AMD ROCm GPU", round(nums[0] / (1024.0 ** 3), 2)
                return "amd", "AMD ROCm GPU", 8.0
        except Exception:
            pass

    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return "apple", "Apple Silicon Unified GPU", round(_detect_ram_gb() * 0.6, 2)

    return "none", "", 0.0


def _detect_runtime_env() -> str:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return "github_actions"
    if os.environ.get("COLAB_RELEASE_TAG") or Path("/content").exists():
        return "colab"
    if os.environ.get("KAGGLE_KERNEL_RUN_TYPE") or Path("/kaggle").exists():
        return "kaggle"
    return "local"


def _probe_comfyui(url: str) -> bool:
    url = (url or "").strip().rstrip("/")
    if not url:
        return False
    try:
        req = urllib.request.Request(f"{url}/system_stats", headers={"User-Agent": "raptar-hw-probe"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _recommend_models(tier: str, comfyui_online: bool, tools: Dict[str, bool]) -> Dict[str, Any]:
    """Produces verified open-source model recommendations tailored to hardware."""
    if tier == "gpu_high_vram":
        return {
            "video": {
                "primary": "Lightricks/LTX-2 (Audio+Video) or Wan-Video/Wan2.2-14B (Apache-2.0)",
                "continuation": "lllyasviel/FramePack or ali-vilab/VACE (Apache-2.0)",
                "quantization": "bf16 / fp8",
                "max_resolution": "1080p",
                "recommended_backend": "comfyui" if comfyui_online else "zerogpu_or_local",
            },
            "image_consistency": "ComfyUI + FLUX.1-dev/schnell + PuLID / IP-Adapter",
            "voice": "resemble-ai/chatterbox (MIT) or QwenAudio/CosyVoice (Apache-2.0) or edge-tts",
            "lipsync": "MeiGen-AI/InfiniteTalk (Apache-2.0) or TMElyralab/MuseTalk (MIT)",
            "animation_3d": "blender" if tools.get("blender") else "svg_puppet_2d",
        }
    if tier == "gpu_mid_vram":
        return {
            "video": {
                "primary": "Wan-Video/Wan2.2-TI2V-5B or Wan2.2-14B GGUF Q4_K_M via ComfyUI-GGUF",
                "continuation": "lllyasviel/FramePack (6-12GB VRAM) or Lightricks/LTX-Video distilled",
                "quantization": "fp8 / gguf_q4_k_m + cpu_offload",
                "max_resolution": "720p_upscaled_to_1080p",
                "recommended_backend": "comfyui" if comfyui_online else "zerogpu_i2v",
            },
            "image_consistency": "ComfyUI + FLUX.1-schnell (GGUF) + IP-Adapter / PuLID",
            "voice": "OHF-Voice/piper1-gpl (GPL-3.0) or hexgrad/kokoro (Apache-2.0) or edge-tts",
            "lipsync": "TMElyralab/MuseTalk (MIT) or bytedance/LatentSync (Apache-2.0)",
            "animation_3d": "blender" if tools.get("blender") else "svg_puppet_2d",
        }
    if tier == "gpu_low_vram":
        return {
            "video": {
                "primary": "lllyasviel/FramePack (6GB VRAM) or Lightricks/LTX-Video distilled GGUF",
                "continuation": "Last-frame I2V chaining via ZeroGPU or FramePack",
                "quantization": "gguf_q4 + sequential_cpu_offload",
                "max_resolution": "540p_upscaled_to_1080p",
                "recommended_backend": "comfyui" if comfyui_online else "zerogpu_i2v",
            },
            "image_consistency": "Pollinations Flux + Character Bible Lock (or local SDXL/FLUX GGUF)",
            "voice": "edge-tts (free cloud) or OHF-Voice/piper1-gpl (local CPU)",
            "lipsync": "TMElyralab/MuseTalk (MIT, ~4-6GB VRAM) or 2D audio-amplitude lip-sync",
            "animation_3d": "svg_puppet_2d",
        }
    # CPU-only (GitHub Actions or local CPU laptop)
    return {
        "video": {
            "primary": "Free ZeroGPU Spaces (Wan 2.2 Lightning I2V -> LTX-Video -> LTX-2.3) + 2D Rigged SVG Puppet Motion Engine",
            "continuation": "Last-frame I2V chaining + multi-shot Ken Burns / parallax SVG scenes",
            "quantization": "remote_zerogpu_and_cpu_vector",
            "max_resolution": "1080p (rendered at 50% SVG scale -> bicubic 1080p CFR)",
            "recommended_backend": "comfyui" if comfyui_online else "hybrid_cloud_and_svg",
        },
        "image_consistency": "Character Bible Prompt Locking + Pollinations Flux + Gemini SVG Auto-Rig",
        "voice": "edge-tts (11+ languages, multi-character pitch/rate) + optional OHF-Voice/piper1-gpl CLI",
        "lipsync": "Audio-amplitude 2D SVG puppet lip-sync (CPU native; MuseTalk/LatentSync requires GPU)",
        "animation_3d": "svg_puppet_2d",
    }


def detect_hardware(comfy_url: Optional[str] = None) -> HardwareProfile:
    """Inspects the active machine and returns a complete HardwareProfile."""
    cores = os.cpu_count() or 2
    ram = _detect_ram_gb()
    disk = _detect_disk_free_gb()
    gpu_vendor, gpu_name, vram = _detect_gpu()
    runtime = _detect_runtime_env()

    tools = {
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "blender": bool(shutil.which("blender")),
        "synfig": bool(shutil.which("synfig")),
        "piper": bool(shutil.which("piper")),
        "espeak": bool(shutil.which("espeak") or shutil.which("espeak-ng")),
        "godot": bool(shutil.which("godot") or shutil.which("godot4")),
    }
    comfy_online = _probe_comfyui(comfy_url or os.environ.get("LOCAL_COMFY_URL", ""))

    if gpu_vendor != "none" and vram >= 20.0:
        tier = "gpu_high_vram"
    elif gpu_vendor != "none" and vram >= 10.5:
        tier = "gpu_mid_vram"
    elif gpu_vendor != "none" and vram >= 4.0:
        tier = "gpu_low_vram"
    elif runtime == "github_actions":
        tier = "cpu_ci"
    else:
        tier = "cpu_local"

    return HardwareProfile(
        os_name=platform.system(),
        arch=platform.machine(),
        cpu_cores=cores,
        ram_gb=ram,
        disk_free_gb=disk,
        gpu_vendor=gpu_vendor,
        gpu_name=gpu_name,
        vram_gb=vram,
        runtime_env=runtime,
        tier=tier,
        tools=tools,
        comfyui_online=comfy_online,
        recommendations=_recommend_models(tier, comfy_online, tools),
    )


if __name__ == "__main__":
    print(json.dumps(detect_hardware().to_dict(), indent=2))
