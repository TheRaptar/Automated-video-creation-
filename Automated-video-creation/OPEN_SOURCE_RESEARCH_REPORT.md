# Open-Source AI Video, Animation, Voice, Lip-Sync & Trend Research Report

*All GitHub repositories, licenses, releases, and update dates below were verified directly via the GitHub API.*

---

## 1. Existing System Audit (`Automated-video-creation/`)

### Retained & Working Modules
- **`make_video.py`**: Free Hugging Face ZeroGPU I2V/T2V (Wan 2.2 Lightning, LTX-Video, LTX-2.3), Pollinations Flux keyframes, Edge-TTS, multilingual `libass` subtitles, 30fps CFR assembly, multi-language dubbing.
- **`motion_engine.py`**: Theatre.js keyframe sheets, SVG.js multi-layer parallax & Gemini SVG auto-rigging, Effekseer particle presets, Natron color grading + `xfade`/`acrossfade` transitions, Synfig `.sif` export.
- **`raptar_agent.py`**: Gemini/Groq multi-language persona planner, translation, auditing, and weighted feedback memory.
- **`trends.py`**, **`upload_youtube.py`**, **`upload_instagram.py`**, **`.github/workflows/daily.yml`**: Working daily trend signals, YouTube/Instagram publishing, and daily safety caps.

### Gaps Identified & Addressed in This Upgrade
1. **Single-narrator audio only** -> Added `character_manager.py` + `audio_studio.py` for multi-character voice casting (male deep, female, child, elder across Hindi, Tamil, English, 11+ languages), copyright-free procedural Foley SFX, and ducked BGM.
2. **No character consistency bible or shot-to-shot continuation** -> Added `CharacterBible` prompt/seed locking and `video_backends.extract_last_frame()` chaining.
3. **ComfyUI backend was a stub (`return False`)** -> Replaced with real `ComfyUIBackend` (`/upload/image`, `/prompt`, `/history/{id}`, `/view`).
4. **No hardware detection, checkpointing, or `--resume` for long stories** -> Added `hardware_manager.py` + `story_studio.py` (`ProjectCheckpoint`, `metrics.json`, 5s–600s+ multi-scene planning, `9:16` / `16:9` / `1:1` export).
5. **No lip-sync** -> Added genuine CPU-native **audio-amplitude RMS lip-sync** on 2D articulated character puppets (`video_backends.render_talking_puppet_scene`) plus an honest local GPU hook (`LIPSYNC_CMD`) for MuseTalk / LatentSync.
6. **Limited trend sources & no freshness decay** -> Added `trend_discovery.py` with Google Trends RSS (all regions), Google News RSS, multi-language Wikipedia Top Pageviews, Hacker News Firebase API, optional YouTube Data API v3, 15 categories, freshness decay scoring, caching (`hourly`/`daily`/`weekly`), and originality/safety filters.

---

## 2. Verified Open-Source Repositories Matrix

### A. AI Video Generation (Open-Weight Models)
| Repository | Website | License | Last Push | VRAM / Hardware | Best Use Case & Notes |
|---|---|---|---|---|---|
| [`Lightricks/LTX-2`](https://github.com/Lightricks/LTX-2) | [ltx.io](https://ltx.io) | Apache-2.0 | 2026-11-19 | 16–24 GB+ (FP8/GGUF lower) | **Audio-video generative model** (official Python inference + LoRA trainer) |
| [`Wan-Video/Wan2.2`](https://github.com/Wan-Video/Wan2.2) | [wan.video](https://wan.video) | Apache-2.0 | 2026-09-21 | 12–24 GB (6–12 GB GGUF Q4) | SOTA open-weight T2V, I2V, TI2V MoE architecture; already tapped on ZeroGPU |
| [`Lightricks/LTX-Video`](https://github.com/Lightricks/LTX-Video) | [ltx.io/model](https://ltx.io/model) | Apache-2.0 | 2026-11-02 | 8–16 GB | Fast distilled I2V/T2V; ideal for rapid 5s shot generation |
| [`lllyasviel/FramePack`](https://github.com/lllyasviel/FramePack) | GitHub | Apache-2.0 | 2025-10-16 | **6 GB VRAM** | Progressive long-duration video extension (up to 60s on consumer GPUs) |
| [`ali-vilab/VACE`](https://github.com/ali-vilab/VACE) | [VACE Page](https://ali-vilab.github.io/VACE-Page/) | Apache-2.0 | 2025-10-17 | 16–24 GB | Reference-to-video, first/last-frame interpolation, video continuation |
| [`SkyworkAI/SkyReels-V2`](https://github.com/SkyworkAI/SkyReels-V2) | [platform.skyreels.ai](https://platform.skyreels.ai) | Custom (verify terms) | 2026-01-29 | 24 GB+ | Auto-regressive diffusion forcing for multi-shot long-duration films |
| [`Tencent-Hunyuan/HunyuanVideo-1.5`](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5) | [hunyuan.tencent.com](https://hunyuan.tencent.com/video/zh?tabIndex=0) | Custom Tencent License* | 2026-04-10 | 12–24 GB | Lightweight high-quality video (*review Tencent Community License territorial/MAU restrictions) |
| [`zai-org/CogVideo`](https://github.com/zai-org/CogVideo) | GitHub | Apache-2.0 | 2025-11-04 | 12–24 GB | CogVideoX T2V/I2V (v1.0) |
| [`genmoai/mochi`](https://github.com/genmoai/mochi) | GitHub | Apache-2.0 | 2026-10-22 | 24 GB+ | Smooth motion fidelity T2V |

### B. Image Generation, Workflow & Character Consistency
| Repository | License | Latest / Push | Notes |
|---|---|---|---|
| [`Comfy-Org/ComfyUI`](https://github.com/Comfy-Org/ComfyUI) | GPL-3.0 | `v0.46.0` (2026-11-19) | Universal modular node-graph backend for FLUX, Wan 2.2, LTX-2, FramePack, PuLID, MuseTalk |
| [`city96/ComfyUI-GGUF`](https://github.com/city96/ComfyUI-GGUF) | Apache-2.0 | 2026-01-12 | Runs 14B/12B video & FLUX models in 6–12 GB VRAM via GGUF quantization |
| [`kijai/ComfyUI-WanVideoWrapper`](https://github.com/kijai/ComfyUI-WanVideoWrapper) | Apache-2.0 | 2026-11-13 | Native ComfyUI wrapper for Wan 2.1/2.2, VACE, InfiniteTalk |
| [`black-forest-labs/flux`](https://github.com/black-forest-labs/flux) | Apache-2.0 (`schnell`) / Non-Commercial (`dev`)* | 2025-07-31 | Top open-weight image keyframe generator (*use `FLUX.1-schnell` for commercial Apache-2.0) |
| [`ToTheBeginning/PuLID`](https://github.com/ToTheBeginning/PuLID) | Apache-2.0 | 2025-07-31 | High-fidelity zero-shot face/character identity lock for FLUX & SDXL |
| [`instantX-research/InstantID`](https://github.com/instantX-research/InstantID) | Apache-2.0 | 2024-07-18 | Zero-shot identity preservation (SDXL) |
| [`tencent-ailab/IP-Adapter`](https://github.com/tencent-ailab/IP-Adapter) | Apache-2.0 | 2024-06-28 | Reference image & outfit style transfer across scenes |

### C. Free AI Voice & Multi-Character Dialogue
| Repository | License | Latest / Push | Languages & Maintenance Notes |
|---|---|---|---|
| [`rany2/edge-tts`](https://github.com/rany2/edge-tts) | LGPL-3.0 (wrapper) | `7.3.1` (2026-11-18) | **Active**. Zero-GPU neural voices for Hindi, Tamil, English, 100+ locales (uses Microsoft Edge online endpoint) |
| [`OHF-Voice/piper1-gpl`](https://github.com/OHF-Voice/piper1-gpl) | GPL-3.0 | `v1.8.0` (2026-11-19) | **Active** official successor to archived `rhasspy/piper`; fast local CPU neural TTS |
| [`resemble-ai/chatterbox`](https://github.com/resemble-ai/chatterbox) | MIT | `v0.1.2` (2026-11-04) | **Active**. Expressive emotional TTS + zero-shot voice cloning (GPU recommended) |
| [`QwenAudio/CosyVoice`](https://github.com/QwenAudio/CosyVoice) | Apache-2.0 | 2026-05-25 | **Active**. Multilingual expressive speech & voice cloning |
| [`hexgrad/kokoro`](https://github.com/hexgrad/kokoro) | Apache-2.0 | 2025-08-06 | Ultra-fast 82M parameter TTS (runs cleanly on CPU & GPU; best in EN/JA/ZH/ES/HI) |
| [`idiap/coqui-ai-TTS`](https://github.com/idiap/coqui-ai-TTS) | MPL-2.0 | `v0.28.0` (2026-11-16) | **Active** community/Idiap successor to archived Coqui TTS (`XTTS-v2` weights have Coqui CPML commercial restrictions*) |
| [`SWivid/F5-TTS`](https://github.com/SWivid/F5-TTS) | MIT | `1.1.22` (2026-11-03) | Flow-matching zero-shot TTS (CC-BY-NC training data caveat — verify commercial use) |

### D. Open-Source Lip Synchronization
| Repository | License | Last Push | Hardware & Notes |
|---|---|---|---|
| [`TMElyralab/MuseTalk`](https://github.com/TMElyralab/MuseTalk) | MIT | 2026-11-19 | **Active**. Real-time (~30fps) high-quality latent-space lip-sync (~4–6 GB VRAM) |
| [`MeiGen-AI/InfiniteTalk`](https://github.com/MeiGen-AI/InfiniteTalk) | Apache-2.0 | 2026-05-22 | **Active**. Unlimited-length audio-driven talking video generation (I2V & V2V; 12–24 GB VRAM) |
| [`bytedance/LatentSync`](https://github.com/bytedance/LatentSync) | Apache-2.0 | 2025-06-20 | Temporal-consistent diffusion lip-sync (~8–12 GB VRAM) |
| [`antgroup/echomimic_v2`](https://github.com/antgroup/echomimic_v2) | Apache-2.0 | 2026-11-17 | **Active**. Audio-driven semi-body gesture + facial animation |
| [`KlingAIResearch/LivePortrait`](https://github.com/KlingAIResearch/LivePortrait) | MIT (verify weights) | 2026-06-01 | Portrait expression & head pose animation (works on humans & stylized animals!) |
| [`Rudrabha/Wav2Lip`](https://github.com/Rudrabha/Wav2Lip) | **Non-Commercial / Research Only*** | 2025-06-22 | Legacy baseline; **avoid for commercial channels** due to LRS2 dataset/license restrictions |

### E. Animation, Rendering & Audio/Subtitle Tooling
| Repository | License | Latest / Push | Role |
|---|---|---|---|
| [`blender/blender`](https://github.com/blender/blender) | GPL-3.0 | 2026-11-19 | Headless Python (`bpy`) 3D animation & Eevee/Cycles rendering on local/GPU machines |
| [`godotengine/godot`](https://github.com/godotengine/godot) | MIT | `4.7.2-stable` (2026-11-19) | Real-time 2D/3D skeletal animation & Movie Maker CLI |
| [`ManimCommunity/manim`](https://github.com/ManimCommunity/manim) | MIT | `v0.22.1` (2026-11-17) | Programmatic educational/explainer vector animations in Python |
| [`svgdotjs/svg.js`](https://github.com/svgdotjs/svg.js) / [`theatre-js/theatre`](https://github.com/theatre-js/theatre) / [`synfig/synfig`](https://github.com/synfig/synfig) | MIT / Apache-2.0 / GPL-3.0 | Active | Core patterns integrated into `motion_engine.py` |
| [`SYSTRAN/faster-whisper`](https://github.com/SYSTRAN/faster-whisper) / [`m-bain/whisperX`](https://github.com/m-bain/whisperX) | MIT / BSD-2-Clause | `v1.2.1` / 2026-11-12 | Word-level forced-alignment subtitle timestamps |
| [`facebookresearch/audiocraft`](https://github.com/facebookresearch/audiocraft) / [`Stability-AI/stable-audio-tools`](https://github.com/Stability-AI/stable-audio-tools) | MIT code / **NC or Community weights*** | 2026-03 / 2026-11 | Local GPU MusicGen/AudioGen (*check weight licenses before commercial monetization; `audio_studio.py` ships 100% copyright-free FFmpeg DSP SFX/BGM as default) |

---

## 3. Known Technical Limitations (Honest Assessment)
1. **CPU-only GitHub Actions runners (`ubuntu-24.04`)** cannot locally run 14B diffusion video weights or MuseTalk GPU inference — on CPU, the studio uses **2D articulated lip-synced puppets**, **Theatre.js/SVG.js motion graphics**, **FFmpeg DSP SFX/BGM**, and **free remote ZeroGPU Spaces**.
2. **Photorealistic multi-character acting with 3D lip-sync** (like commercial Veo 3 Reels) requires connecting a **local NVIDIA GPU / free Colab / Kaggle T4-P100** running **ComfyUI** (`LOCAL_COMFY_URL` + `LOCAL_COMFY_WORKFLOW` using Wan 2.2 GGUF / LTX-2 / PuLID) + `LIPSYNC_CMD` (`MuseTalk` or `InfiniteTalk`).
3. **Long-form duration (2–10+ min)** is achieved honestly via **scene/shot decomposition + last-frame continuation + checkpointed assembly**, not single-pass 10-minute diffusion.
4. **Trend API limits**: X (Twitter), Instagram Reels, and TikTok do not provide free unrestricted trend APIs; `trend_discovery.py` relies on verified, legal, zero-cost feeds (Google Trends RSS, Google News RSS, Wikipedia Pageviews, Hacker News, and optional YouTube Data API v3).
