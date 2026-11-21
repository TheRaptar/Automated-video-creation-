# Automated Video Creation (RAPTAR Engine)

Generates AI-animated Reels, YouTube Shorts, and Long-Form videos automatically on GitHub Actions (`ubuntu-24.04`) with zero paid animation software or API credits required.

## Open-Source Animation Engine (`motion_engine.py`)

Evaluated and integrated headless-compatible patterns from the 10 open-source GitHub animation repositories:

| Repository | Role / Technique Integrated | Status in Cloud Pipeline |
|---|---|---|
| `theatre-js/theatre` | Declarative `MotionSheet` keyframe tracks + cubic-bezier & spring easing solver | **Integrated** in `motion_engine.py` |
| `svgdotjs/svg.js` | Programmatic multi-layer SVG scene graph, animated per-frame vector rendering & Gemini SVG auto-rigging | **Integrated** in `motion_engine.py` |
| `effekseer/Effekseer` | Deterministic particle VFX emitters (embers/sparks, sakura petals, magic stars, cyber motes) with alpha-over-life compositing | **Integrated** in `motion_engine.py` |
| `NatronGitHub/Natron` | Node-graph `CompositorGraph` (color grading, bloom/unsharp, vignette), smooth `xfade` + `acrossfade` scene transitions & broadcast audio mastering | **Integrated** in `motion_engine.py` |
| `synfig/synfig` | Native `.sif` XML keyframe canvas exporter (`EXPORT_SYNFIG_PROJECT=1`) + optional headless `synfig` CLI render backend (`FREE_VIDEO_PROVIDER=synfig`) | **Integrated** in `motion_engine.py` |
| `AcademySoftwareFoundation/openvdb` | Procedural layered volumetric mist/smoke atmosphere preset (`volumetric_mist`) emulated without heavy C++/GPU OpenVDB builds | **Emulated (CPU-safe)** |
| `friction2d/friction` | Eased vector/raster motion graphics choreography (`cubic_bezier`, `spring`, parallax layers) | **Pattern adapted** |
| `opentoonz/opentoonz` | Desktop Qt/OpenGL 2D studio suite — unsuitable for headless Linux CI runners | Not bundled (desktop GUI) |
| `pencil2d/pencil` | Interactive hand-drawn cartoon desktop app — unsuitable for automated script-to-video CI | Not bundled (desktop GUI) |
| `freemocap/freemocap` | Multi-camera 3D human motion capture — requires real camera feeds | Not bundled (live mocap) |

## Optional Motion Engine Environment Flags

- `ENABLE_MOTION_GRAPHICS="1"` — Enables multi-frame animated SVG vector scenes & Gemini SVG auto-rigging on fallback/offline runs.
- `ENABLE_PARTICLE_VFX="1"` — Composites subtle genre-matched Effekseer-style particle VFX overlays on Shorts/Reels/Animated clips (skipped for `long` format to keep 5–7 min renders fast).
- `ENABLE_TRANSITIONS="1"` — Applies Natron-style FFmpeg `xfade` + `acrossfade` transitions between Short/Animated/Story scenes (preserves lossless `concat` on `long` format for exact chapter timestamps).
- `ENABLE_AUDIO_MASTER="1"` — Applies voice highpass + gentle dynamics compression (`acompressor`) on narration.
- `EXPORT_SYNFIG_PROJECT="0"` — Set to `"1"` to also write `output/scene_0.sif` editable in Synfig Studio.

---

## Free Open-Source Story Studio & Global Trend Engine (`story_studio.py`)

Modular, hardware-aware, checkpointable multi-character story production pipeline (`5s` to `10m+`, `9:16` / `16:9` / `1:1`):

- **`hardware_manager.py`**: Detects CPU, RAM, NVIDIA/AMD/Apple GPU, VRAM, Colab/Kaggle, and local tools (`ffmpeg`, `blender`, `synfig`, `piper`, `comfyui`) and recommends optimal quantized open-weight models.
- **`character_manager.py`**: Persists `CharacterBible` profiles with locked appearances/outfits, deterministic seeds, and distinct multi-character neural voices across English, Hindi, Tamil, and 11+ languages.
- **`audio_studio.py`**: Multi-character dialogue synthesis (`edge-tts` + optional local `OHF-Voice/piper1-gpl`), 100% copyright-free procedural Foley SFX & ducked BGM beds, and RMS audio lip-sync envelope extraction.
- **`video_backends.py`**: Aspect-ratio presets (`9:16`, `16:9`, `1:1`), real ComfyUI API workflow client (`LOCAL_COMFY_URL` + `LOCAL_COMFY_WORKFLOW`), last-frame shot continuation, CPU-native 2D articulated talking puppets with real audio RMS lip-sync, and optional GPU lip-sync CLI hook (`LIPSYNC_CMD` for MuseTalk/LatentSync).
- **`trend_discovery.py`**: Global multi-source public trend discovery (Google Trends RSS across all regions, Google News RSS, multi-language Wikipedia Pageviews, Hacker News, optional YouTube Data API v3) with 15 categories, freshness/growth scoring, caching (`hourly`/`daily`/`weekly`), deduplication, and originality/safety filters.
- **`story_studio.py`**: Checkpointable multi-scene story orchestrator with automatic retries, `--resume` recovery, and `metrics.json` telemetry.

### Quick CLI Examples

```bash
cd Automated-video-creation

# 1. Inspect local hardware & open-source model recommendations
python3 hardware_manager.py

# 2. Discover live global trends across all regions
python3 trend_discovery.py

# 3. Generate a 60s 9:16 multi-character animated story in Hindi
python3 story_studio.py --idea "A proud white lion and his cub visit a golden tower" \
  --style animal_story --duration 60 --aspect 9:16 --lang hi

# 4. Auto-discover a live trend and convert it into an original 2-minute 16:9 story
python3 story_studio.py --from-trend --region ALL --category fantasy_adventure \
  --style fantasy --duration 120 --aspect 16:9 --lang en

# 5. Resume an interrupted long-form project without re-rendering completed scenes
python3 story_studio.py --resume projects/<project_id>
```

See [`OPEN_SOURCE_RESEARCH_REPORT.md`](./OPEN_SOURCE_RESEARCH_REPORT.md) for the full verified GitHub repository matrix, licenses, VRAM requirements, and known limitations.

## Growth, Retention, SEO & Dual-Platform Analytics (`growth_optimizer.py` & `analytics_optimizer.py`)
- **Timezone-Aligned 7-Slot Routing**: Preserves all 7 daily slots and all 7 languages (`en`, `ta`, `hi`, `es`, `fr`, `pt`, `ja`), routing each UTC slot to its audience's native peak window and matching regional Google Trends / News feeds (`IN` for Hindi/Tamil, `IN,US,GB` for English, etc.).
- **Retention Packaging**: 0-1.5s scroll-stop hook archetypes (75/25 bandit), tighter 3-4.5s visual pacing, seamless replay loop bridges, vertical safe-zone power-word ASS captions + 1.8s top Hook Banner, and subtle ducked copyright-free BGM + opening hook SFX.
- **Peak-Frame Cover & Platform-Native SEO**: Scores frames to pick the sharpest cover for YouTube CTR thumbnails and Instagram `thumb_offset`, removes bot footers and `#viral`/`#reels` spam, sets dynamic YouTube categories, and formats 4-5 focused niche Instagram hashtags + localized comment/save CTAs.
- **Closed-Loop Dual-Platform Analytics**: Syncs YouTube OAuth video statistics (`views`, `likes`, `comments`) and Instagram Graph Reels Insights (`views`, `likes`, `comments`, `shares`, `saved`, `ig_reels_avg_watch_time`) to auto-tune multi-dimensional bandit weights (`category`, `style`, `hook_type`, `duration_bucket`), plus scope-safe YouTube playlist assignment and first-comment prompts.
