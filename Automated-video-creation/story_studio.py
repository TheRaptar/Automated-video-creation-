#!/usr/bin/env python3
"""
RAPTAR Open-Source Animated Story & Trend-to-Video Production Studio.

End-to-end, hardware-aware, checkpointable story studio that turns a simple idea
or live global trend into a complete multi-character animated video (5s to 10m+)
in 9:16, 16:9, or 1:1 using 100% free & open-source tools.

Key Capabilities:
  - 12+ animation & storytelling styles (photorealistic, 3d_realistic, 3d_cartoon,
    2d_cartoon, anime, animal_story, human_drama, fantasy, comedy, action,
    children, mixed).
  - Multi-duration planning: 5s, 10s, 15s, 30s, 60s, 2m, 5m, 10m+ assembled
    honestly from character-consistent shots with last-frame continuation.
  - Persistent CharacterBible with locked appearance/outfits & distinct neural
    voices per character (Hindi, Tamil, English, and 11+ languages).
  - Real audio-driven 2D puppet lip-sync on CPU + optional GPU lip-sync &
    ComfyUI / ZeroGPU Wan 2.2 / LTX-Video backends.
  - Copyright-free procedural Foley SFX + ducked BGM mixing.
  - Scene-level JSON checkpointing, automatic retries, and `--resume` support.
  - Measurable timing & hardware telemetry (`metrics.json`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import audio_studio
import hardware_manager
import motion_engine as me
import trend_discovery
import video_backends
from character_manager import CharacterBible

try:
    import make_video
except ImportError:
    make_video = None


STYLE_ART_DIRECTIONS: Dict[str, Tuple[str, str]] = {
    "photorealistic": (
        "Photorealistic 8K cinematic live-action film frame, natural global illumination, ultra-detailed fur/skin/fabric textures, shallow depth of field",
        "cinematic",
    ),
    "3d_realistic": (
        "Unreal Engine 5 photorealistic 3D CGI animated movie frame, volumetric raytraced lighting, physically accurate materials",
        "warm_glow",
    ),
    "3d_cartoon": (
        "Vibrant 3D Pixar-style cartoon feature film animation, expressive oversized eyes, glossy stylized textures, warm rim light",
        "vibrant",
    ),
    "2d_cartoon": (
        "Crisp modern 2D vector cartoon animation, bold clean outlines, rich flat-shaded colors, expressive smear-frame poses",
        "vibrant",
    ),
    "anime": (
        "High-budget Japanese anime feature film frame (Makoto Shinkai aesthetic), cel-shaded characters, glowing dramatic skyscapes, lens flare",
        "anime_neon",
    ),
    "animal_story": (
        "Expressive 3D stylized anthropomorphic animal characters in vivid cinematic environments, rich fur textures, warm dramatic lighting",
        "warm_glow",
    ),
    "human_drama": (
        "Cinematic emotional storytelling frame, expressive human acting, soft golden-hour key lighting, atmospheric film grade",
        "cinematic",
    ),
    "fantasy": (
        "Epic magical fantasy concept film frame, luminous floating particles, ancient temples and glowing skies, rich painterly detail",
        "warm_glow",
    ),
    "comedy": (
        "Playful energetic cartoon comedy film frame, exaggerated hilarious reactions, bright colorful sunlit locations",
        "vibrant",
    ),
    "action": (
        "High-octane dynamic cinematic action shot, dramatic low-angle perspective, motion streaks, crisp high-contrast lighting",
        "cinematic",
    ),
    "children": (
        "Whimsical storybook animated illustration, soft magical pastel glow, friendly charming characters, uplifting cozy wonder",
        "sparkles",
    ),
    "mixed": (
        "Creative mixed-media cinematic animation blending stylized 3D characters with vibrant 2D motion graphics overlays",
        "vibrant",
    ),
}

STYLE_TO_MOTION_PALETTE: Dict[str, str] = {
    "photorealistic": "legend",
    "3d_realistic": "animated_myth",
    "3d_cartoon": "animated_comedy",
    "2d_cartoon": "animated_comedy",
    "anime": "animated_anime",
    "animal_story": "animated_comedy",
    "human_drama": "animated_myth",
    "fantasy": "animated_myth",
    "comedy": "animated_comedy",
    "action": "scifi",
    "children": "fable",
    "mixed": "animated_comedy",
}


class ProjectCheckpoint:
    """Persists per-stage & per-scene completion state for crash recovery & `--resume`."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)
        self.path = self.project_dir / "checkpoint.json"
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"completed_scenes": [], "stages": {}, "updated_at": 0.0}

    def save(self) -> None:
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.data["updated_at"] = time.time()
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    def mark_stage(self, name: str, info: Any = True) -> None:
        self.data.setdefault("stages", {})[name] = info
        self.save()

    def is_scene_done(self, idx: int, expected_file: Path) -> bool:
        return idx in self.data.get("completed_scenes", []) and expected_file.exists() and expected_file.stat().st_size > 1000

    def mark_scene_done(self, idx: int) -> None:
        done = set(self.data.get("completed_scenes", []))
        done.add(idx)
        self.data["completed_scenes"] = sorted(done)
        self.save()


def _plan_offline_or_fallback_story(
    idea: str,
    style: str,
    target_seconds: int,
    lang: str,
    trend_item: Optional[trend_discovery.TrendItem] = None,
) -> Dict[str, Any]:
    """
    Deterministic multi-character story & shot planner that scales cleanly from 5s
    to 10+ minutes (600s) when offline or when LLM keys are not provided.
    """
    idea_clean = (idea or "The Golden Tower Challenge").strip()
    is_animal = style in ("animal_story", "comedy", "3d_cartoon") or any(
        w in idea_clean.lower() for w in ("lion", "squirrel", "animal", "cub", "tiger", "shera", "sheru")
    )

    if is_animal:
        characters = [
            {
                "name": "Leo",
                "archetype": "lion",
                "gender": "male",
                "age_group": "adult",
                "voice_role": "male_deep",
                "appearance_lock": "tall regal white lion with voluminous snow-white mane and cool gold-rimmed sunglasses",
                "outfit_lock": "tailored crisp white three-piece suit with gold chain",
                "color_palette": ["#f8fafc", "#e2e8f0", "#f59e0b"],
                "personality": "confident, generous, cool-headed",
            },
            {
                "name": "Milo",
                "archetype": "cub",
                "gender": "male",
                "age_group": "child",
                "voice_role": "child",
                "appearance_lock": "adorable small white lion cub with bright curious eyes and fluffy mane tuft",
                "outfit_lock": "mini black tuxedo with white sneakers",
                "color_palette": ["#f8fafc", "#111827", "#fbbf24"],
                "personality": "bold, playful, endlessly ambitious",
            },
            {
                "name": "Aria",
                "archetype": "human",
                "gender": "female",
                "age_group": "adult",
                "voice_role": "female",
                "appearance_lock": "poised young host with neat bun hairstyle and warm smile",
                "outfit_lock": "crisp white blazer and dark tailored skirt",
                "color_palette": ["#fde68a", "#334155", "#38bdf8"],
                "personality": "polite, observant, quickly amazed",
            },
        ]
    else:
        characters = [
            {
                "name": "Kira",
                "archetype": "anime_hero" if style == "anime" else "human",
                "gender": "female",
                "age_group": "young",
                "voice_role": "female",
                "appearance_lock": "determined young explorer with bright expressive eyes and wind-swept hair",
                "outfit_lock": "sleek indigo adventure jacket with glowing gold trim",
                "color_palette": ["#fde68a", "#312e81", "#fbbf24"],
                "personality": "curious, brave, sharp-witted",
            },
            {
                "name": "Orion",
                "archetype": "robot" if style in ("action", "mixed") else "elder",
                "gender": "male",
                "age_group": "adult",
                "voice_role": "male_deep",
                "appearance_lock": "wise companion with calm steady gaze and distinctive geometric crest",
                "outfit_lock": "dark slate cloak with luminous cyan accents",
                "color_palette": ["#e0f2fe", "#0f172a", "#38bdf8"],
                "personality": "calm, witty, protective",
            },
        ]

    # Scale scene count honestly to match requested duration (5s -> 1 scene, 60s -> ~6 scenes, 300s -> ~20 scenes, 600s -> ~36 scenes)
    avg_scene_sec = 5.0 if target_seconds <= 15 else (8.0 if target_seconds <= 60 else 15.0)
    n_scenes = max(1, min(40, int(round(target_seconds / avg_scene_sec))))

    envs = ["dubai_skyline", "royal_palace", "ocean_bridge", "ancient_forest"]
    motions = ["zoom_in", "pan_right", "dolly_pulse", "zoom_out", "pan_left", "pan_up"]
    sfx_cycle = [["whoosh"], ["footsteps", "door_open"], ["shock_hit"], ["impact_boom"], ["sparkle"]]

    scenes: List[Dict[str, Any]] = []
    c0, c1 = characters[0]["name"], characters[min(1, len(characters) - 1)]["name"]
    c2 = characters[-1]["name"]

    for i in range(n_scenes):
        if i == 0:
            heading = "The Impossible Dream"
            dialogue = [
                {"speaker": c1, "text": f"Look up there! Today we are taking on {idea_clean}.", "emotion": "happy"},
                {"speaker": c0, "text": "If you think that is impossible, just watch closely.", "emotion": "confident"},
            ] if n_scenes > 1 or target_seconds >= 8 else [
                {"speaker": c0, "text": f"Watch what happens when {idea_clean} comes alive!", "emotion": "confident"}
            ]
        elif i == n_scenes - 1:
            heading = "The Unforgettable Twist"
            dialogue = [
                {"speaker": c2, "text": "Nobody thought they could actually pull it off!", "emotion": "shocked"},
                {"speaker": c0, "text": "Never underestimate a bold dream. Follow for part two!", "emotion": "happy"},
            ]
        else:
            chapter_idx = i + 1
            heading = f"Chapter {chapter_idx}: Rising Stakes"
            dialogue = [
                {"speaker": c0, "text": f"Step {chapter_idx}: every obstacle opens a hidden path forward.", "emotion": "determined"},
                {"speaker": c1, "text": "Wait—did you hear that sound? Everything just changed!", "emotion": "shocked"},
            ]

        scenes.append({
            "heading": heading,
            "environment": envs[i % len(envs)],
            "characters": [c0, c1] if i < n_scenes - 1 else [c0, c2],
            "action": f"Dynamic animated storytelling moment {i + 1} for {idea_clean}",
            "camera_motion": motions[i % len(motions)],
            "camera_direction": "dramatic close-up reaction" if i % 2 == 1 else "wide cinematic establishing shot",
            "sfx": sfx_cycle[i % len(sfx_cycle)],
            "dialogue": dialogue,
        })

    return {
        "title": idea_clean[:70],
        "topic": idea_clean,
        "style": style,
        "language": lang,
        "target_seconds": target_seconds,
        "description": f"Original multi-character animated story inspired by {idea_clean}.",
        "hashtags": ["#AIAnimation", "#AnimatedStory", f"#{style}", f"#{lang}"],
        "characters": characters,
        "scenes": scenes,
        "trend_source": trend_item.to_dict() if trend_item else None,
    }


def plan_story_with_llm(
    idea: str,
    style: str,
    target_seconds: int,
    lang: str,
    trend_item: Optional[trend_discovery.TrendItem] = None,
    offline: bool = False,
) -> Dict[str, Any]:
    """Plans a structured multi-character story + storyboard JSON using free Gemini/Groq or deterministic fallback."""
    if offline or make_video is None or not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY")):
        return _plan_offline_or_fallback_story(idea, style, target_seconds, lang, trend_item=trend_item)

    avg_scene_sec = 5.5 if target_seconds <= 20 else (8.5 if target_seconds <= 75 else 14.0)
    n_scenes = max(2, min(28, int(round(target_seconds / avg_scene_sec))))
    trend_ctx = f"\nTrend inspiration (make 100% ORIGINAL characters/story, no real-person impersonation): {trend_item.original_story_angle}" if trend_item else ""

    prompt = f"""You are an award-winning Animated Film Director and Screenwriter.
Create an original, gripping multi-character animated story script in language code '{lang}'.
Core idea: {idea}
Animation style: {style}
Target total duration: ~{target_seconds} seconds across {n_scenes} scenes.{trend_ctx}

Return ONLY valid JSON:
{{
  "title": "High-curiosity original title in language '{lang}' (max 65 chars)",
  "description": "2-sentence engaging description in '{lang}'",
  "hashtags": ["#AIAnimation", "#AnimatedStory", "#Storytime"],
  "characters": [
    {{
      "name": "Short memorable character name",
      "archetype": "lion|cub|tiger|squirrel|robot|human|child|elder|anime_hero",
      "gender": "male|female",
      "age_group": "child|young|adult|elder",
      "voice_role": "male_deep|male_young|female|female_dramatic|child|elder|narrator",
      "appearance_lock": "Exact immutable physical appearance in ENGLISH (face, hair/fur, build, proportions)",
      "outfit_lock": "Exact immutable outfit and accessories in ENGLISH",
      "color_palette": ["#hex_skin_or_fur", "#hex_outfit", "#hex_accent"],
      "personality": "3-word personality"
    }}
  ],
  "scenes": [
    {{
      "heading": "Short scene/chapter title",
      "environment": "dubai_skyline|royal_palace|ocean_bridge|ancient_forest",
      "characters": ["CharacterName1", "CharacterName2"],
      "action": "Vivid visual description in ENGLISH for video/image generation",
      "camera_motion": "zoom_in|zoom_out|pan_left|pan_right|pan_up|dolly_pulse",
      "camera_direction": "wide establishing|medium two-shot|dramatic close-up",
      "sfx": ["whoosh|impact_boom|shock_hit|footsteps|laughter_chime|sparkle|thunder|door_open|engine_rev|suspense_riser"],
      "dialogue": [
        {{"speaker": "CharacterName1", "text": "Spoken dialogue line in language '{lang}'", "emotion": "happy|shocked|angry|sad|confident|determined|neutral"}}
      ]
    }}
  ]
}}
Rules:
- 2 to 3 distinct, visually locked original characters.
- Opening scene MUST hook viewers in the first 2 seconds with action or a bold line.
- Every scene must have 1 to 3 crisp dialogue turns totaling enough speech to fit ~{avg_scene_sec:.0f}s per scene.
- NEVER copy copyrighted characters or impersonate living people."""

    valid = lambda d: (
        isinstance(d, dict)
        and isinstance(d.get("characters"), list) and len(d["characters"]) >= 1
        and isinstance(d.get("scenes"), list) and len(d["scenes"]) >= 1
    )
    res = make_video.llm_json(prompt, rounds=2, valid=valid)
    if not res:
        return _plan_offline_or_fallback_story(idea, style, target_seconds, lang, trend_item=trend_item)

    res.setdefault("topic", idea)
    res["style"] = style
    res["language"] = lang
    res["target_seconds"] = target_seconds
    res["trend_source"] = trend_item.to_dict() if trend_item else None
    return res


def _write_dialogue_ass(
    ass_path: Path,
    turns: Sequence[audio_studio.DialogueTurn],
    width: int,
    height: int,
    font_name: str,
    heading: Optional[str] = None,
    accent_bgr: str = "&H0000E5FF",
) -> Path:
    """Generates styled ASS subtitles showing speaker-synced dialogue lines cleanly."""
    fontsize = 66 if width <= height else 56
    margin_v = int(height * 0.14) if width > height else int(height * 0.22)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 1
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{fontsize},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,55,55,{margin_v},1
Style: Highlight,{font_name},{fontsize},{accent_bgr},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,55,55,{margin_v},1
Style: Heading,{font_name},46,&H00FFFFFF,&H000000FF,&H00000000,&HC0000000,-1,0,0,0,100,100,0,0,3,14,0,7,65,65,55,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def _fmt(sec: float) -> str:
        sec = max(0.0, sec)
        return f"{int(sec // 3600)}:{int((sec % 3600) // 60):02d}:{sec % 60:05.2f}"

    events: List[str] = []
    for idx_t, tr in enumerate(turns):
        words = tr.text.split()
        span = max(0.3, tr.end_sec - tr.start_sec)
        chunks = [" ".join(words[k : k + 5]) for k in range(0, len(words), 5)] or [tr.text]
        total_chars = sum(len(c) for c in chunks) or 1
        cur = tr.start_sec
        st_name = "Highlight" if idx_t % 2 == 1 else "Default"
        for ch in chunks:
            seg = span * len(ch) / total_chars
            safe = ch.replace("{", "(").replace("}", ")").replace("\n", " ")
            pop = r"{\fscx93\fscy93\t(0,65,\fscx100\fscy100)}"
            events.append(f"Dialogue: 0,{_fmt(cur)},{_fmt(cur + seg)},{st_name},,0,0,0,,{pop}{safe}")
            cur += seg

    if heading:
        safe_h = heading.replace("{", "(").replace("}", ")").replace("\n", " ")
        events.append(f"Dialogue: 1,0:00:00.00,0:00:02.80,Heading,,0,0,0,,{safe_h}")

    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return ass_path


def _ff_esc(p: Path) -> str:
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def produce_story_project(
    idea: str = "",
    style: str = "3d_cartoon",
    target_seconds: int = 30,
    aspect: str = "9:16",
    quality: str = "high",
    lang: str = "en",
    backend: str = "auto",
    from_trend: bool = False,
    region: str = "ALL",
    category: str = "",
    cadence: str = "daily",
    project_dir: Optional[Path] = None,
    offline: bool = False,
    enable_bgm: bool = True,
    enable_particles: bool = True,
    enable_transitions: bool = True,
) -> Dict[str, Any]:
    """
    Executes the full checkpointed animated story pipeline and returns a
    comprehensive production report (video path, metadata, metrics, hardware).
    """
    t_start = time.time()
    hw = hardware_manager.detect_hardware()
    width, height = video_backends.resolve_dimensions(aspect=aspect, quality=quality)
    fps = 30

    # Resolve or create project directory (supports --resume cleanly!)
    if project_dir is None:
        slug = re.sub(r"[^a-z0-9]+", "_", (idea or category or "story").lower()).strip("_")[:28] or "story"
        proj_id = f"{slug}_{hashlib.md5(f'{idea}:{style}:{target_seconds}:{aspect}'.encode()).hexdigest()[:6]}"
        project_dir = Path("projects") / proj_id
    project_dir = Path(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    scenes_dir = project_dir / "scenes"
    scenes_dir.mkdir(exist_ok=True)
    work_dir = project_dir / "work"
    work_dir.mkdir(exist_ok=True)

    ckpt = ProjectCheckpoint(project_dir)
    stage_timings: Dict[str, float] = {}

    # Stage 1: Trend Discovery (if requested and no plan checkpoint exists yet)
    plan_path = project_dir / "story_plan.json"
    trend_item: Optional[trend_discovery.TrendItem] = None
    if plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        print(f"[Studio] Resuming existing story plan: {plan.get('title')}")
    else:
        t0 = time.time()
        if from_trend:
            td = trend_discovery.TrendDiscoveryEngine(cache_path=project_dir / "trend_cache.json", cadence=cadence)
            trends_found = td.discover(region=region, lang=lang, category=category, limit=5, offline=offline)
            if trends_found:
                trend_item = trends_found[0]
                idea = idea or trend_item.title
                if target_seconds <= 0:
                    target_seconds = trend_item.recommended_seconds
                print(f"[Studio] Selected trend: {trend_item.title} (score={trend_item.combined_score}, cat={trend_item.category})")
        if target_seconds <= 0:
            target_seconds = 30
        plan = plan_story_with_llm(idea or "The Impossible Quest", style, target_seconds, lang, trend_item=trend_item, offline=offline)
        plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
        ckpt.mark_stage("story_plan", {"title": plan["title"], "scenes": len(plan["scenes"])})
        stage_timings["story_plan_sec"] = round(time.time() - t0, 2)

    # Stage 2: Character Bible (persisted & reused across runs/resumes)
    chars_path = project_dir / "characters.json"
    if chars_path.exists():
        bible = CharacterBible.load(chars_path)
    else:
        bible = CharacterBible(project_dir=project_dir, lang=lang)
        for c in plan.get("characters", []):
            pal = c.get("color_palette")
            pal_tuple = (pal[0], pal[1], pal[2]) if isinstance(pal, list) and len(pal) >= 3 else None
            bible.register(
                name=c.get("name", "Hero"),
                archetype=c.get("archetype", "human"),
                gender=c.get("gender", "male"),
                age_group=c.get("age_group", "adult"),
                voice_role=c.get("voice_role", ""),
                appearance_lock=c.get("appearance_lock", ""),
                outfit_lock=c.get("outfit_lock", ""),
                color_palette=pal_tuple,
                personality=c.get("personality", ""),
            )
        bible.save(chars_path)
        ckpt.mark_stage("characters", len(bible.characters))

    art_style, fx_preset = STYLE_ART_DIRECTIONS.get(style, STYLE_ART_DIRECTIONS["3d_cartoon"])
    motion_style = STYLE_TO_MOTION_PALETTE.get(style, "animated_comedy")
    font_path = make_video.find_font(lang) if make_video else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    font_name = Path(font_path).stem.split("-")[0]

    comfy = video_backends.ComfyUIBackend()
    rendered_scenes: List[Path] = []
    chapters: List[Tuple[float, str]] = []
    elapsed = 0.0
    prev_last_frame: Optional[Path] = None
    backend_usage: Dict[str, int] = {}

    # Stage 3: Per-scene checkpointed rendering with retry & last-frame continuation
    t_scenes = time.time()
    for idx, sc in enumerate(plan.get("scenes", [])):
        scene_out = scenes_dir / f"scene_{idx:03d}.mp4"
        if ckpt.is_scene_done(idx, scene_out):
            dur_existing = me._probe_duration(scene_out)
            if sc.get("heading"):
                chapters.append((elapsed, sc["heading"]))
            elapsed += dur_existing
            rendered_scenes.append(scene_out)
            # Keep continuation frame fresh for subsequent unrendered scenes
            lf = work_dir / f"last_frame_{idx:03d}.png"
            if video_backends.extract_last_frame(scene_out, lf):
                prev_last_frame = lf
            print(f"[Studio] Scene {idx + 1}/{len(plan['scenes'])} resumed from checkpoint ({dur_existing:.1f}s)")
            continue

        # 3a. Multi-character dialogue TTS + SFX + BGM mixing
        scene_audio = work_dir / f"scene_{idx:03d}_audio.mp3"
        dialogue_lines = sc.get("dialogue") or [{"speaker": "Narrator", "text": sc.get("action", "The adventure continues.")}]
        dur, turns = audio_studio.build_scene_dialogue_and_mix(
            dialogue_lines=dialogue_lines,
            bible=bible,
            work_dir=work_dir,
            scene_idx=idx,
            out_audio=scene_audio,
            lang=lang,
            style=motion_style,
            sfx_cues=sc.get("sfx"),
            enable_bgm=enable_bgm,
            offline=offline,
        )

        # 3b. Visual generation (interchangeable backends + multi-shot continuation)
        vis_raw = work_dir / f"scene_{idx:03d}_vis.mp4"
        char_names = sc.get("characters") or list(bible.characters.keys())[:2]
        shot_prompt, shot_seed = bible.build_consistent_shot_prompt(
            art_style=art_style,
            scene_action=sc.get("action", ""),
            character_names=char_names,
            environment=sc.get("environment", ""),
            camera_direction=sc.get("camera_direction", "medium shot"),
            aspect_ratio=aspect,
        )
        used_backend = "puppet_2d"
        visual_ok = False

        # Try ComfyUI first when explicitly configured and online
        if backend in ("auto", "comfyui") and not offline and comfy.is_available():
            if comfy.run_workflow(shot_prompt, vis_raw, width, height, seed=shot_seed, input_image=prev_last_frame):
                used_backend = "comfyui"
                visual_ok = True

        # Try CPU-native 2D articulated talking puppet with real audio-amplitude lip-sync
        if not visual_ok and backend in ("auto", "puppet_2d"):
            visual_ok = video_backends.render_talking_puppet_scene(
                out_path=vis_raw,
                audio_path=scene_audio,
                turns=turns,
                bible=bible,
                character_names=char_names,
                width=width,
                height=height,
                duration=dur + 0.2,
                fps=fps,
                style=motion_style,
                environment=sc.get("environment", "ancient_forest"),
                motion=sc.get("camera_motion", "zoom_in"),
                fx=fx_preset,
                idx=idx,
                enable_particles=enable_particles,
            )
            if visual_ok:
                used_backend = "puppet_2d_lipsync"

        # Fallback to Theatre.js / SVG.js multi-layer motion graphics
        if not visual_ok:
            visual_ok = me.render_animated_svg_scene(
                out_path=vis_raw,
                width=width,
                height=height,
                duration=dur + 0.2,
                fps=fps,
                style=motion_style,
                idx=idx,
                motion=sc.get("camera_motion", "zoom_in"),
                fx=fx_preset,
                enable_particles=enable_particles,
            )
            used_backend = "svg_motion"

        if not visual_ok:
            raise RuntimeError(f"All visual backends failed for scene {idx}")

        # Optional local GPU lip-sync refinement hook (MuseTalk / LatentSync if installed)
        lipsync_tmp = work_dir / f"scene_{idx:03d}_lipsync.mp4"
        if not offline and video_backends.apply_gpu_lipsync_hook(vis_raw, scene_audio, lipsync_tmp):
            lipsync_tmp.replace(vis_raw)
            used_backend += "+gpu_lipsync"

        # Extract final frame to support true shot-to-shot continuation
        lf = work_dir / f"last_frame_{idx:03d}.png"
        if video_backends.extract_last_frame(vis_raw, lf):
            prev_last_frame = lf

        # 3c. Burn speaker-synced ASS subtitles + mux mastered audio -> CFR 30fps scene MP4
        ass_path = _write_dialogue_ass(
            work_dir / f"scene_{idx:03d}.ass",
            turns=turns,
            width=width,
            height=height,
            font_name=font_name,
            heading=sc.get("heading") if (aspect == "16:9" or idx == 0) else None,
        )
        fonts_dir = _ff_esc(Path(font_path).parent)
        total_sc = dur + 0.18
        subprocess.run([
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(vis_raw), "-i", str(scene_audio),
            "-t", f"{total_sc:.3f}",
            "-vf", f"ass='{_ff_esc(ass_path)}':fontsdir='{fonts_dir}'",
            "-af", f"apad,atrim=0:{total_sc:.3f}",
            "-map", "0:v:0", "-map", "1:a:0",
            "-r", str(fps), "-vsync", "cfr", "-video_track_timescale", "90000",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            str(scene_out),
        ], check=True, capture_output=True, text=True, timeout=180)

        if sc.get("heading"):
            chapters.append((elapsed, sc["heading"]))
        elapsed += total_sc
        rendered_scenes.append(scene_out)
        backend_usage[used_backend] = backend_usage.get(used_backend, 0) + 1
        ckpt.mark_scene_done(idx)
        print(f"[Studio] Rendered scene {idx + 1}/{len(plan['scenes'])} via {used_backend} ({total_sc:.1f}s)")

    stage_timings["scenes_render_sec"] = round(time.time() - t_scenes, 2)

    # Stage 4: Final Assembly (xfade for Shorts/medium, lossless concat for long stories)
    t_join = time.time()
    final_mp4 = project_dir / "final_story.mp4"
    used_transitions = False
    if enable_transitions and 2 <= len(rendered_scenes) <= 16 and target_seconds <= 120:
        used_transitions = me.join_scenes_with_transitions(
            rendered_scenes, final_mp4, style=motion_style, fps=fps, transition_dur=0.28
        )
    if not used_transitions:
        lst = work_dir / "final_concat.txt"
        lst.write_text("".join(f"file '{p.resolve()}'\n" for p in rendered_scenes), encoding="utf-8")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
            "-c", "copy", "-movflags", "+faststart", str(final_mp4),
        ], check=True, capture_output=True, text=True, timeout=180)
    stage_timings["final_assembly_sec"] = round(time.time() - t_join, 2)

    # Generate thumbnail frame cleanly
    thumb_path = project_dir / "thumbnail.jpg"
    actual_dur = me._probe_duration(final_mp4)
    subprocess.run([
        "ffmpeg", "-y", "-ss", f"{min(1.0, actual_dur * 0.25):.2f}", "-i", str(final_mp4),
        "-frames:v", "1", "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720",
        "-q:v", "3", str(thumb_path),
    ], capture_output=True, text=True, timeout=30)

    metadata = {
        "title": plan["title"],
        "topic": plan.get("topic", idea),
        "style": style,
        "language": lang,
        "aspect_ratio": aspect,
        "resolution": f"{width}x{height}",
        "target_seconds": target_seconds,
        "actual_seconds": round(actual_dur, 2),
        "scenes_count": len(rendered_scenes),
        "characters": [c.name for c in bible.characters.values()],
        "chapters": [{"time_sec": round(t, 2), "heading": h} for t, h in chapters],
        "description": plan.get("description", ""),
        "hashtags": plan.get("hashtags", []),
        "transitions_applied": used_transitions,
        "backends_used": backend_usage,
        "trend_source": plan.get("trend_source"),
    }
    (project_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    metrics = {
        "total_runtime_sec": round(time.time() - t_start, 2),
        "stage_timings": stage_timings,
        "hardware_tier": hw.tier,
        "hardware_profile": hw.to_dict(),
        "output_size_mb": round(final_mp4.stat().st_size / (1024 * 1024), 2) if final_mp4.exists() else 0.0,
        "actual_video_sec": round(actual_dur, 2),
        "backends_used": backend_usage,
    }
    (project_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    ckpt.mark_stage("final_mp4", str(final_mp4))
    return {"video": str(final_mp4), "thumbnail": str(thumb_path), "metadata": metadata, "metrics": metrics}


def main() -> None:
    ap = argparse.ArgumentParser(description="RAPTAR Free Open-Source AI Animated Story Studio")
    ap.add_argument("--idea", default="", help="Story concept or prompt")
    ap.add_argument("--from-trend", action="store_true", help="Automatically discover a fresh trend and turn it into an original story")
    ap.add_argument("--region", default="ALL", help="Trend region code (ALL, US, IN, GB, JP, etc.)")
    ap.add_argument("--category", default="", help="Trend category (funny_animals, anime, comedy, technology, etc.)")
    ap.add_argument("--cadence", choices=["hourly", "daily", "weekly"], default="daily")
    ap.add_argument("--style", choices=sorted(STYLE_ART_DIRECTIONS.keys()), default="3d_cartoon")
    ap.add_argument("--duration", type=int, default=30, help="Target story duration in seconds (5 to 600+)")
    ap.add_argument("--aspect", choices=["9:16", "16:9", "1:1"], default="9:16")
    ap.add_argument("--quality", choices=["high", "draft"], default="high")
    ap.add_argument("--lang", default="en", help="Dialogue language (en, hi, ta, es, fr, ja, ko, ar, etc.)")
    ap.add_argument("--backend", choices=["auto", "puppet_2d", "svg_motion", "comfyui"], default="auto")
    ap.add_argument("--resume", default="", help="Path to an existing project directory to resume cleanly")
    ap.add_argument("--offline", action="store_true", help="Run completely offline without external network calls")
    args = ap.parse_args()

    offline = args.offline or (os.environ.get("OFFLINE_TEST") == "1")
    res = produce_story_project(
        idea=args.idea,
        style=args.style,
        target_seconds=args.duration,
        aspect=args.aspect,
        quality=args.quality,
        lang=args.lang,
        backend=args.backend,
        from_trend=args.from_trend,
        region=args.region,
        category=args.category,
        cadence=args.cadence,
        project_dir=Path(args.resume) if args.resume else None,
        offline=offline,
    )
    print(json.dumps({
        "video": res["video"],
        "actual_seconds": res["metadata"]["actual_seconds"],
        "resolution": res["metadata"]["resolution"],
        "characters": res["metadata"]["characters"],
        "total_runtime_sec": res["metrics"]["total_runtime_sec"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
