#!/usr/bin/env python3
"""
Transformative FFmpeg Storytelling Engine & Zero-Modification Uploader Bridge.

Converts verified open-license and creator-approved video clips into original
edited stories that minimize copyright & reused-content risk:
- Strips ALL original source audio (`-an`) by default to prevent Content ID bleed.
- Generates original multi-scene narrative commentary (LLM or offline fallback).
- Synthesizes multilingual neural voiceover (reusing existing audio_studio / Edge-TTS).
- Cuts 3-8 rhythmic scenes with color grading, zoom/pan motion & safe-zone power-word
  kinetic ASS captions + 1.8s top Hook Banner (reusing growth_optimizer).
- Mixes narration + verified CC0/CC-BY music (Openverse/Freesound) or procedural
  copyright-free BGM bed + opening hook SFX.
- Embeds clean required attribution credits into YouTube & Instagram SEO metadata,
  records cryptographic proof in ProvenanceLedger, and optionally invokes the
  existing unmodified upload_youtube.py / upload_instagram.py only when --publish is set.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .ledger import ProvenanceLedger
from .license_gate import VerifiedAsset, format_attribution_block

PARENT_DIR = Path(__file__).resolve().parent.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

try:
    import audio_studio
except Exception:
    audio_studio = None

try:
    import growth_optimizer
except Exception:
    growth_optimizer = None

try:
    import make_video as mv_helpers
except Exception:
    mv_helpers = None


ASPECT_MAP: Dict[str, Tuple[int, int]] = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
}


def _probe_duration(path: Path) -> float:
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1", str(path),
            ],
            text=True,
            timeout=20,
        ).strip()
        return max(0.0, float(out))
    except Exception:
        return 0.0


def _ff_escape(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _find_font(lang: str = "en") -> str:
    if mv_helpers is not None:
        try:
            return mv_helpers.find_font(lang)
        except Exception:
            pass
    for cand in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    ):
        if Path(cand).exists():
            return cand
    return "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


# ---------------------------------------------------------------------------
# 1. Original Transformative Storytelling Script Generator
# ---------------------------------------------------------------------------
def build_transformative_script(
    topic: str,
    clip_count: int,
    language: str = "en",
    style: str = "story",
    offline: bool = False,
) -> Dict[str, Any]:
    """
    Produces an original multi-beat storytelling / commentary script so curated
    clips become genuine transformative content rather than raw re-uploads.
    Uses Gemini/Groq when configured and online, with deterministic fallback.
    """
    n_scenes = max(3, min(8, int(clip_count)))
    lang = (language or "en").strip().lower()
    cta = (
        growth_optimizer.localized_engagement_cta(lang, topic)
        if growth_optimizer is not None
        else "What stood out to you most? Share your thoughts in the comments!"
    )

    if not offline and mv_helpers is not None and (os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY")):
        prompt = f"""You are a senior documentary & short-form video storyteller.
Write an ORIGINAL, transformative {n_scenes}-scene narration commentary about "{topic}" in language '{lang}'.
Return ONLY JSON:
{{
  "topic": "{topic}",
  "title": "High-CTR curiosity title under 58 chars in {lang}",
  "description": "2-sentence search-friendly summary in {lang}",
  "hashtags": ["#TopicTag1", "#TopicTag2", "#Storytelling"],
  "engagement_cta": "Short debate question in {lang}",
  "scenes": [
    {{"text": "Punchy original narration sentence (10-18 words) in {lang}"}}
  ]
}}
Rules:
- Exactly {n_scenes} scenes.
- Scene 1 is an instant 1.5-second curiosity hook under 10 words.
- Final scene bridges smoothly back to Scene 1 for seamless replay."""
        try:
            data = mv_helpers.llm_json(
                prompt,
                rounds=1,
                valid=lambda d: isinstance(d, dict) and isinstance(d.get("scenes"), list) and len(d["scenes"]) >= 3,
            )
            if data and len(data["scenes"]) >= 3:
                return {
                    "topic": str(data.get("topic") or topic),
                    "title": str(data.get("title") or topic),
                    "description": str(data.get("description") or f"An original edited story exploring {topic}."),
                    "hashtags": [str(h) for h in (data.get("hashtags") or []) if str(h).strip()],
                    "language": lang,
                    "style": style,
                    "category": f"Curated {style.title()} Stories",
                    "engagement_cta": str(data.get("engagement_cta") or cta),
                    "scenes": [{"text": str(s.get("text") or "").strip()} for s in data["scenes"][:n_scenes] if str(s.get("text") or "").strip()],
                }
        except Exception:
            pass

    # Deterministic, original narrative commentary fallback (never raw re-upload!)
    templates = [
        f"Most people scroll right past the real story behind {topic}.",
        f"Look closely at every small movement unfolding in this moment.",
        f"When ordinary details connect in sequence, a hidden human story appears.",
        f"Notice how rhythm, light, and timing transform a simple scene into emotion.",
        f"Every frame captures a choice that quietly shifts what happens next.",
        f"Step back for a second and you realize why moments like {topic} stay with us.",
        f"What starts small builds into something unforgettable before the final beat.",
        f"And that is why most people miss the real story behind {topic}.",
    ]
    chosen = templates[: max(2, n_scenes - 1)] + [templates[-1]]
    return {
        "topic": topic,
        "title": f"The Hidden Story Behind {topic}"[:58],
        "description": f"An original narrated visual story exploring {topic} through curated licensed footage.",
        "hashtags": [f"#{re.sub(r'[^A-Za-z0-9]', '', topic.title())[:20] or 'RealStories'}", "#VisualStorytelling", "#HumanMoments"],
        "language": lang,
        "style": style,
        "category": f"Curated {style.title()} Stories",
        "engagement_cta": cta,
        "scenes": [{"text": line} for line in chosen[:n_scenes]],
    }


# ---------------------------------------------------------------------------
# 2. Safe-Zone Kinetic ASS Subtitles & Audio-Stripped Clip Normalization
# ---------------------------------------------------------------------------
def _fmt_ass_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _write_scene_ass(
    idx: int,
    text: str,
    dur: float,
    width: int,
    height: int,
    font_path: str,
    lang: str,
    work_dir: Path,
    hook_banner: str = "",
) -> Path:
    sz = (
        growth_optimizer.get_safe_zone_margins(width, height)
        if growth_optimizer is not None
        else {"margin_l": 64, "margin_r": 140 if height > width else 64, "margin_v": int(height * 0.27), "banner_v": int(height * 0.14)}
    )
    fontsize = 72 if height >= 1080 else 48
    hl_bgr = "&H0000E5FF"
    font_name = Path(font_path).stem.split("-")[0]

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 1
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{fontsize},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,{sz['margin_l']},{sz['margin_r']},{sz['margin_v']},1
Style: Highlight,{font_name},{fontsize},{hl_bgr},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,{sz['margin_l']},{sz['margin_r']},{sz['margin_v']},1
Style: HookBanner,{font_name},56,&H0000E6FF,&H000000FF,&H00000000,&HB0000000,-1,0,0,0,100,100,0,0,3,12,0,8,{sz['margin_l']},{sz['margin_l']},{sz['banner_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    words = text.split()
    chunks = [" ".join(words[i:i + 3]) for i in range(0, len(words), 3)] or [text]
    total_chars = sum(len(c) for c in chunks) or 1
    t = 0.0
    events: List[str] = []
    for n, ch in enumerate(chunks):
        span = dur * len(ch) / total_chars
        if growth_optimizer is not None:
            disp = growth_optimizer.format_power_word_ass(ch, hl_bgr, lang=lang)
            st = "Default" if r"{\c" in disp else ("Highlight" if n % 3 == 1 else "Default")
        else:
            disp = ch.upper().replace("{", "(").replace("}", ")")
            st = "Highlight" if n % 2 == 1 else "Default"
        pop = r"{\fscx92\fscy92\t(0,70,\fscx100\fscy100)}"
        events.append(f"Dialogue: 0,{_fmt_ass_time(t)},{_fmt_ass_time(t + span)},{st},,0,0,0,,{pop}{disp}")
        t += span

    if hook_banner and idx == 0:
        safe_ban = hook_banner.replace("{", "(").replace("}", ")").strip()
        if safe_ban:
            events.append(f"Dialogue: 2,0:00:00.00,{_fmt_ass_time(min(dur, 1.85))},HookBanner,,0,0,0,,{safe_ban}")

    ass_path = work_dir / f"lic_sub_{idx}.ass"
    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return ass_path


def _normalize_clip_strip_audio(
    src_video: Path,
    dst_video: Path,
    target_dur: float,
    width: int,
    height: int,
    scene_idx: int,
    fps: int = 24,
) -> Path:
    """
    Normalizes a verified source clip to exact resolution/FPS, applies light cinematic
    color grading, and EXPLICITLY STRIPS ALL ORIGINAL AUDIO (`-an`) to eliminate
    Content ID risk from background music or classic-film restoration scores.
    """
    src_dur = _probe_duration(src_video)
    # Pick a dynamic mid-clip offset when source is long (avoids dark intro slates!)
    start_sec = 0.0
    if src_dur > target_dur + 3.0:
        frac = 0.15 + ((scene_idx * 0.19) % 0.55)
        start_sec = round(min(src_dur - target_dur - 0.5, src_dur * frac), 2)

    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        "eq=contrast=1.06:saturation=1.12,"
        f"fps={fps},format=yuv420p"
    )
    cmd = ["ffmpeg", "-y"]
    if src_dur < target_dur:
        cmd += ["-stream_loop", "-1"]
    if start_sec > 0:
        cmd += ["-ss", f"{start_sec:.2f}"]
    cmd += [
        "-i", str(src_video),
        "-t", f"{target_dur:.3f}",
        "-an",  # CRITICAL: strip 100% of original source audio!
        "-vf", vf,
        "-r", str(fps), "-vsync", "cfr",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
        str(dst_video),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=120)
    return dst_video


def _synthesize_narration(text: str, out_audio: Path, lang: str = "en", offline: bool = False) -> float:
    """Synthesizes original narration using existing audio_studio (Edge-TTS / Piper / offline)."""
    if audio_studio is not None:
        voice_map = {
            "en": "en-US-GuyNeural", "ta": "ta-IN-ValluvarNeural", "hi": "hi-IN-MadhurNeural",
            "es": "es-MX-JorgeNeural", "fr": "fr-FR-HenriNeural", "pt": "pt-BR-AntonioNeural",
            "ja": "ja-JP-KeitaNeural",
        }
        return audio_studio.synthesize_voice_line(
            text=text,
            out_path=out_audio,
            voice=voice_map.get(lang, "en-US-GuyNeural"),
            offline=offline,
        )
    # Minimal FFmpeg fallback if audio_studio unavailable
    dur = max(2.2, min(7.0, len(text.split()) * 0.38))
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"sine=frequency=210:duration={dur:.2f},volume=0.08",
            "-ar", "44100", "-ac", "2", str(out_audio),
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=30,
    )
    return dur


# ---------------------------------------------------------------------------
# 3. End-to-End Transformative Production Pipeline
# ---------------------------------------------------------------------------
def produce_transformative_video(
    topic: str,
    verified_videos: List[VerifiedAsset],
    verified_music: Optional[VerifiedAsset] = None,
    fmt: str = "short",
    aspect: str = "9:16",
    language: str = "en",
    style: str = "story",
    out_dir: Optional[Path] = None,
    ledger_path: Optional[Path] = None,
    offline: bool = False,
) -> Dict[str, Any]:
    """
    Assembles verified clips into an original, transformative edited video:
    - Refuses to process any clip whose verification_status != 'approved'.
    - Replaces 100% of original audio with original narration + verified CC0/CC-BY or
      procedural copyright-free music + opening hook SFX.
    - Generates uploader-compatible output/video.mp4, output/metadata.json,
      output/thumbnail.jpg (for long-form), and ProvenanceLedger evidence certificates.
    """
    approved_vids = [v for v in verified_videos if v.verification_status == "approved" and v.local_path and Path(v.local_path).exists()]
    if not approved_vids:
        raise ValueError("No verified local video assets available for transformative editing.")

    if verified_music is not None and verified_music.verification_status != "approved":
        raise PermissionError(f"Music asset '{verified_music.asset_id}' is not license-approved.")

    width, height = ASPECT_MAP.get(aspect, (1080, 1920))
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stage_dir = Path(out_dir) if out_dir else (PARENT_DIR / "licensed_media_output" / f"run_{run_stamp}")
    work_dir = stage_dir / "work"
    stage_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1. Build original transformative script
    clip_slots = max(3, min(8, len(approved_vids)))
    script = build_transformative_script(topic=topic, clip_count=clip_slots, language=language, style=style, offline=offline)
    scenes_spec = script["scenes"]
    font_path = _find_font(language)
    hook_banner = (
        growth_optimizer.extract_thumbnail_hook_words(script["title"], scenes_spec[0]["text"])
        if (growth_optimizer is not None and fmt != "long" and scenes_spec)
        else ""
    )

    # 2. Build each scene: strip original audio -> burn safe-zone kinetic captions -> attach narration
    rendered_scenes: List[Path] = []
    used_video_assets: List[VerifiedAsset] = []
    for idx, sc in enumerate(scenes_spec):
        src_asset = approved_vids[idx % len(approved_vids)]
        if src_asset not in used_video_assets:
            used_video_assets.append(src_asset)

        voice_wav = work_dir / f"narr_{idx}.wav"
        narr_dur = _synthesize_narration(sc["text"], voice_wav, lang=language, offline=offline)
        scene_dur = max(2.4, narr_dur + 0.30)

        clean_clip = work_dir / f"clean_{idx}.mp4"
        _normalize_clip_strip_audio(
            src_video=Path(src_asset.local_path),
            dst_video=clean_clip,
            target_dur=scene_dur,
            width=width,
            height=height,
            scene_idx=idx,
        )

        ass_file = _write_scene_ass(
            idx=idx,
            text=sc["text"],
            dur=narr_dur,
            width=width,
            height=height,
            font_path=font_path,
            lang=language,
            work_dir=work_dir,
            hook_banner=hook_banner if idx == 0 else "",
        )
        fonts_dir = _ff_escape(Path(font_path).parent)
        scene_out = work_dir / f"scene_{idx}.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(clean_clip),
                "-i", str(voice_wav),
                "-t", f"{scene_dur:.3f}",
                "-vf", f"ass='{_ff_escape(ass_file)}':fontsdir='{fonts_dir}'",
                "-af", f"apad,atrim=0:{scene_dur:.3f}",
                "-map", "0:v:0", "-map", "1:a:0",
                "-r", "24", "-vsync", "cfr",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                str(scene_out),
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=120,
        )
        rendered_scenes.append(scene_out)

    # 3. Join scenes smoothly
    joined_mp4 = work_dir / "joined.mp4"
    list_txt = work_dir / "concat.txt"
    list_txt.write_text("".join(f"file '{p.resolve()}'\n" for p in rendered_scenes), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_txt), "-c", "copy", "-movflags", "+faststart", str(joined_mp4)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=120,
    )

    total_dur = _probe_duration(joined_mp4)
    final_mp4 = stage_dir / "video.mp4"

    # 4. Layer verified CC0/CC-BY music OR copyright-free procedural BGM bed + opening hook SFX
    audio_assets_used: List[VerifiedAsset] = []
    bgm_file: Optional[Path] = None
    if verified_music is not None and verified_music.local_path and Path(verified_music.local_path).exists():
        bgm_file = Path(verified_music.local_path)
        audio_assets_used.append(verified_music)
    elif audio_studio is not None:
        bgm_wav = work_dir / "procedural_bgm.wav"
        mood = audio_studio.map_style_to_bgm_mood(style)
        if audio_studio.synthesize_bgm_bed(mood, max(3.0, total_dur), bgm_wav):
            bgm_file = bgm_wav
            proc_asset = VerifiedAsset(
                asset_id="procedural_bgm_dsp",
                media_type="audio",
                source_provider="procedural_dsp",
                external_id=mood,
                title=f"Procedural Copyright-Free BGM ({mood})",
                creator="Raptar Audio Studio DSP",
                source_url="local://procedural_dsp",
                local_path=str(bgm_wav),
                license_code="CC0-1.0",
                verification_status="approved",
                verification_reason="Locally synthesized procedural audio (100% copyright-free).",
                verified_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            audio_assets_used.append(proc_asset)

    sfx_file: Optional[Path] = None
    if audio_studio is not None:
        sfx_wav = work_dir / "hook_sfx.wav"
        if audio_studio.synthesize_sfx("whoosh", sfx_wav):
            sfx_file = sfx_wav

    if bgm_file is not None:
        inputs = ["-i", str(joined_mp4), "-stream_loop", "-1", "-i", str(bgm_file)]
        if sfx_file is not None:
            inputs += ["-i", str(sfx_file)]
            fc = (
                "[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[voice];"
                "[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
                f"atrim=0:{total_dur:.3f},volume=0.11,afade=t=in:st=0:d=0.6,"
                f"afade=t=out:st={max(0.2, total_dur - 1.0):.2f}:d=1.0[bgm];"
                "[2:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=0.22[sfx];"
                "[voice][bgm][sfx]amix=inputs=3:duration=first:dropout_transition=0:normalize=0,"
                "alimiter=limit=0.95[aout]"
            )
        else:
            fc = (
                "[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[voice];"
                "[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
                f"atrim=0:{total_dur:.3f},volume=0.11,afade=t=in:st=0:d=0.6,"
                f"afade=t=out:st={max(0.2, total_dur - 1.0):.2f}:d=1.0[bgm];"
                "[voice][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
                "alimiter=limit=0.95[aout]"
            )
        subprocess.run(
            [
                "ffmpeg", "-y", *inputs,
                "-filter_complex", fc,
                "-map", "0:v:0", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                str(final_mp4),
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=120,
        )
    else:
        shutil.copy2(joined_mp4, final_mp4)

    # 5. Peak-frame cover selection + Platform-native SEO + Embedded Attribution Credits
    all_assets = used_video_assets + audio_assets_used
    full_credits = format_attribution_block(all_assets, compact=False)
    compact_credits = format_attribution_block(all_assets, compact=True)
    attr_lines = [a.attribution_text for a in all_assets if a.attribution_required or a.attribution_text]

    peak = (
        growth_optimizer.select_peak_cover_frame(final_mp4, work_dir)
        if growth_optimizer is not None
        else {"timestamp_sec": 1.5, "thumb_offset_ms": 1500, "score": 0.5}
    )
    seo_pkg = (
        growth_optimizer.build_platform_seo(
            script,
            fmt=fmt,
            thumb_offset_ms=int(peak.get("thumb_offset_ms") or 1500),
            hook_type="secret_reveal",
        )
        if growth_optimizer is not None
        else {
            "series_name": "Licensed Stories",
            "youtube_seo": {"title": script["title"], "description": script["description"], "tags": [], "category_id": "24"},
            "instagram_seo": {"caption": script["description"], "hashtags": script["hashtags"][:5], "thumb_offset_ms": 1500},
        }
    )

    yt_seo = dict(seo_pkg["youtube_seo"])
    ig_seo = dict(seo_pkg["instagram_seo"])
    if full_credits:
        yt_seo["description"] = (yt_seo["description"] + "\n\n" + full_credits)[:4900]
    if compact_credits:
        ig_seo["caption"] = (ig_seo["caption"] + "\n\n" + compact_credits)[:2200]

    thumb_path = stage_dir / "thumbnail.jpg"
    if fmt == "long" and growth_optimizer is not None:
        growth_optimizer.render_ctr_thumbnail(
            video_path=final_mp4,
            hook_text=seo_pkg.get("thumbnail_hook") or script["title"],
            font_path=font_path,
            out_path=thumb_path,
            work_dir=work_dir,
            peak_info=peak,
        )

    actual_dur = round(_probe_duration(final_mp4), 2)
    meta = {
        "format": fmt,
        "language": language,
        "topic": script["topic"],
        "title": script["title"],
        "description": yt_seo["description"],
        "hashtags": ig_seo.get("hashtags", []),
        "category": script.get("category"),
        "style": style,
        "hook_type": "secret_reveal",
        "series_name": seo_pkg.get("series_name"),
        "duration_sec": actual_dur,
        "duration_bucket": growth_optimizer.duration_bucket_for(actual_dur) if growth_optimizer else "short_28_45",
        "thumb_offset_ms": int(peak.get("thumb_offset_ms") or 0),
        "youtube_seo": yt_seo,
        "instagram_seo": ig_seo,
        "licensed_media_addon": True,
        "original_audio_stripped": True,
        "source": "licensed_media",
    }
    meta_path = stage_dir / "metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    # 6. Record immutable proof in ProvenanceLedger + per-video certificate
    ledger = ProvenanceLedger(ledger_path=ledger_path)
    proof_entry = ledger.record_production(
        output_video=final_mp4,
        topic=script["topic"],
        language=language,
        fmt=fmt,
        video_assets=used_video_assets,
        audio_assets=audio_assets_used,
        transformative_summary={
            "clips_combined": len(rendered_scenes),
            "unique_sources": len(used_video_assets),
            "original_audio_stripped": True,
            "original_narration_added": True,
            "kinetic_subtitles_burned": True,
            "music_source": audio_assets_used[0].source_provider if audio_assets_used else "none",
            "aspect_ratio": aspect,
            "duration_sec": actual_dur,
        },
        attributions_embedded=attr_lines,
        certificate_dir=stage_dir,
    )

    return {
        "stage_dir": str(stage_dir),
        "video": str(final_mp4),
        "metadata": str(meta_path),
        "thumbnail": str(thumb_path) if thumb_path.exists() else "",
        "evidence_certificate": str(stage_dir / "evidence_certificate.json"),
        "credits_proof_txt": str(stage_dir / "CREDITS_AND_PROOF.txt"),
        "record_id": proof_entry["record_id"],
        "meta": meta,
        "proof_entry": proof_entry,
    }


# ---------------------------------------------------------------------------
# 4. Zero-Modification Opt-In Uploader Bridge
#    Invokes your existing, unmodified upload_youtube.py and upload_instagram.py
#    ONLY when explicitly requested via `--publish youtube|instagram|both`.
# ---------------------------------------------------------------------------
def handoff_and_publish(
    production: Dict[str, Any],
    publish_target: str = "none",
    ledger_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Stages the verified production into Automated-video-creation/output/ and runs
    the existing, unmodified upload_youtube.py and/or upload_instagram.py scripts.
    Existing daily safety caps (MAX_UPLOADS_PER_DAY / MAX_IG_POSTS_PER_DAY) remain
    100% enforced by those unmodified scripts.
    """
    target = (publish_target or "none").strip().lower()
    if target not in ("youtube", "instagram", "both"):
        return {"published": [], "mode": "dry_run"}

    video_src = Path(production["video"])
    meta_src = Path(production["metadata"])
    if not (video_src.exists() and meta_src.exists()):
        raise FileNotFoundError("Rendered video.mp4 or metadata.json missing for publisher handoff.")

    out_dir = PARENT_DIR / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Clear stale extra lang_* folders so only this verified video publishes
    for old_lang in out_dir.glob("lang_*"):
        shutil.rmtree(old_lang, ignore_errors=True)
    (out_dir / "thumbnail.jpg").unlink(missing_ok=True)

    shutil.copy2(video_src, out_dir / "video.mp4")
    shutil.copy2(meta_src, out_dir / "metadata.json")
    if production.get("thumbnail") and Path(production["thumbnail"]).exists():
        shutil.copy2(Path(production["thumbnail"]), out_dir / "thumbnail.jpg")

    ledger = ProvenanceLedger(ledger_path=ledger_path)
    published: List[str] = []

    if target in ("youtube", "both"):
        res = subprocess.run([sys.executable, "upload_youtube.py"], cwd=str(PARENT_DIR), check=False)
        if res.returncode == 0:
            published.append("youtube")
            ledger.mark_published(production["record_id"], "youtube", "Uploaded via unmodified upload_youtube.py")

    if target in ("instagram", "both"):
        res = subprocess.run([sys.executable, "upload_instagram.py"], cwd=str(PARENT_DIR), check=False)
        if res.returncode == 0:
            published.append("instagram")
            ledger.mark_published(production["record_id"], "instagram", "Published via unmodified upload_instagram.py")

    return {"published": published, "mode": target}
