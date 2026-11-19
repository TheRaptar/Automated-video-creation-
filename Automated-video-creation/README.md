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
