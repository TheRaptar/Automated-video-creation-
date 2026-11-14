#!/usr/bin/env python3
"""
RAPTAR Organic Growth, SEO, Thumbnail, QC & Analytics Learning Engine
=====================================================================
Provides:
1. Copyright-free procedural BGM synthesis & sidechain narration ducking (FFmpeg)
2. 3-Concept high-contrast 1280x720 Thumbnail generation & automated CTR selection
3. Truthful YouTube SEO metadata optimizer (5 title variants, opening hook, tags, categoryId)
4. Pre-publish 10-factor AI Quality Control (1-10 rubric + ffprobe stream validation)
5. YouTube Analytics API v2 sync (views, impressions, CTR, AVD, retention, subs, traffic, returning)
6. Closed-loop Channel Learning Engine updating `state["learnings"]`
"""
import json
import os
import re
import shutil
import subprocess
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import requests

YT_ANALYTICS_URL = os.environ.get(
    "YT_ANALYTICS_URL", "https://youtubeanalytics.googleapis.com/v2/reports"
)

BANNED_OPENINGS = (
    "hello everyone",
    "welcome back",
    "hey guys",
    "hi everyone",
    "in today's video",
    "what's up guys",
)


def _ff_escape(path) -> str:
    return str(path).replace("\\", "/").replace(":", r"\:")


def _run_cmd(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180)


def probe_media(path: Path) -> dict:
    """Extracts video/audio stream telemetry using ffprobe."""
    if not path.exists():
        return {"exists": False}
    try:
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,bit_rate,size:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=25,
        )
        if r.returncode != 0:
            return {"exists": True, "valid": False}
        data = json.loads(r.stdout or "{}")
        fmt = data.get("format", {})
        streams = data.get("streams", [])
        v_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        a_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
        return {
            "exists": True,
            "valid": bool(v_stream and a_stream),
            "duration": float(fmt.get("duration") or 0.0),
            "bitrate": int(fmt.get("bit_rate") or 0),
            "size_bytes": int(fmt.get("size") or path.stat().st_size),
            "width": int(v_stream.get("width") or 0),
            "height": int(v_stream.get("height") or 0),
            "video_codec": v_stream.get("codec_name", ""),
            "audio_codec": a_stream.get("codec_name", ""),
            "sample_rate": int(a_stream.get("sample_rate") or 0),
        }
    except Exception:
        return {"exists": path.exists(), "valid": False}


# ------------------------------------------------------------
# 1. Copyright-Free Procedural BGM & Narration Audio Ducking
# ------------------------------------------------------------
def synthesize_bgm(style: str, duration: float, dest: Path) -> Optional[Path]:
    """
    Generates a clean, royalty-free ambient musical underscore using FFmpeg math synthesis.
    No external downloaded audio -> zero copyright claims guaranteed.
    """
    dur = max(2.0, float(duration))
    s = (style or "").lower()
    if s in ("horror", "thriller", "mystery"):
        # Minor ominous warm drone + subtle low pulse
        expr = (
            "0.22*sin(2*PI*73.42*t)+0.16*sin(2*PI*110*t)+0.12*sin(2*PI*130.81*t)*(0.5+0.5*sin(2*PI*0.25*t))"
        )
        af = f"lowpass=f=480,aecho=0.6:0.7:120:0.25,afade=t=in:st=0:d=1.0,afade=t=out:st={max(0.5, dur - 1.5):.2f}:d=1.5"
    elif s in ("animated_comedy", "fitness_glamour", "fable", "charm"):
        # Bright major progression with subtle uplifting pulse
        expr = (
            "0.18*sin(2*PI*261.63*t)+0.15*sin(2*PI*329.63*t)+0.14*sin(2*PI*392.00*t)*(0.65+0.35*sin(2*PI*1.6*t))"
        )
        af = f"lowpass=f=900,aecho=0.5:0.5:80:0.18,afade=t=in:st=0:d=0.6,afade=t=out:st={max(0.5, dur - 1.2):.2f}:d=1.2"
    else:
        # Cinematic storytelling & myth ambient pad (warm 5th + octave pad)
        expr = (
            "0.20*sin(2*PI*146.83*t)+0.17*sin(2*PI*220.00*t)+0.13*sin(2*PI*293.66*t)*(0.7+0.3*sin(2*PI*0.35*t))"
        )
        af = f"lowpass=f=750,aecho=0.6:0.65:110:0.22,afade=t=in:st=0:d=0.8,afade=t=out:st={max(0.5, dur - 1.5):.2f}:d=1.5"

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"aevalsrc={expr}:s=44100:d={dur:.2f}",
        "-af",
        af,
        "-ac",
        "2",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "128k",
        str(dest),
    ]
    res = _run_cmd(cmd)
    if res.returncode == 0 and dest.exists() and dest.stat().st_size > 500:
        return dest
    return None


def mix_narration_and_bgm(
    video_in: Path,
    bgm_path: Path,
    video_out: Path,
    bgm_volume: Optional[float] = None,
) -> bool:
    """
    Mixes narration video track with procedural BGM using sidechain ducking so the speaker
    always cuts cleanly through the music bed, then normalizes loudness cleanly.
    """
    if not video_in.exists() or not bgm_path or not bgm_path.exists():
        return False
    vol = bgm_volume if bgm_volume is not None else float(os.environ.get("BGM_VOLUME", "0.14"))
    vol = max(0.03, min(0.35, vol))

    dur = max(1.0, probe_media(video_in).get("duration") or 10.0)
    filter_complex = (
        "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,asplit=2[vo_main][vo_sc];"
        f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={vol:.3f}[bgm_raw];"
        "[bgm_raw][vo_sc]sidechaincompress=threshold=0.025:ratio=6:attack=25:release=260[bgm_ducked];"
        "[vo_main][bgm_ducked]amix=inputs=2:duration=first:normalize=0,"
        "alimiter=limit=0.95[aout]"
    )
    tmp_out = video_out.with_name(f"{video_out.stem}_bgm_tmp.mp4")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_in),
        "-stream_loop",
        "-1",
        "-i",
        str(bgm_path),
        "-t",
        f"{dur:.3f}",
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v:0",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        "44100",
        "-movflags",
        "+faststart",
        str(tmp_out),
    ]
    res = _run_cmd(cmd)
    if res.returncode == 0 and tmp_out.exists() and tmp_out.stat().st_size > 1000:
        shutil.move(str(tmp_out), str(video_out))
        return True
    tmp_out.unlink(missing_ok=True)
    return False


# ------------------------------------------------------------
# 2. YouTube SEO & 5-Title Optimization Engine
# ------------------------------------------------------------
def infer_youtube_category(style: str, category: str = "") -> str:
    """Maps internal style/category accurately to a clean YouTube VideoCategory ID."""
    s = (style or "").lower()
    c = (category or "").lower()
    if s in ("animated_myth", "animated_comedy", "animated_anime", "fable", "story"):
        return "1"  # Film & Animation
    if s in ("scifi", "fact") or any(k in c for k in ("space", "science", "tech", "ai", "quantum")):
        return "28"  # Science & Technology
    if s in ("how",) or any(k in c for k in ("history", "education", "mythology", "culture")):
        return "27"  # Education
    return "24"  # Entertainment (horror, thriller, mystery, legend, fitness_glamour)


def optimize_youtube_seo(
    script: dict,
    learnings: Optional[dict] = None,
    llm_json_fn: Optional[Callable] = None,
    offline: bool = False,
) -> dict:
    """
    Produces complete non-clickbait SEO metadata:
      - 5 distinct title variations ranked for truthful curiosity & CTR
      - selected_title (clean best pick)
      - engaging above-the-fold opening_description (<=160 chars)
      - search_keywords, non-spammy hashtags (no hardcoded #viral), clean tags, category_id
    """
    base_title = str(script.get("title") or script.get("topic") or "Untold Story").strip()
    topic = str(script.get("topic") or base_title).strip()
    desc = str(script.get("description") or "").strip()
    style = str(script.get("style") or "story").strip()
    category = str(script.get("category") or "").strip()
    lang = str(script.get("language") or "en").strip()
    fmt = str(script.get("format") or "short").strip()
    first_scene = (script.get("scenes") or [{}])[0].get("text", "")

    cat_id = infer_youtube_category(style, category)

    if llm_json_fn and not offline:
        top_title_patterns = (learnings or {}).get("top_title_patterns") or []
        prompt = f"""You are a YouTube SEO & CTR Strategist.
Topic: {topic}
Original Title: {base_title}
Description: {desc}
Opening Hook: {first_scene[:200]}
Format: {fmt} | Language: {lang} | Style: {style} | Category: {category}
Proven Channel Title Patterns: {top_title_patterns}

Create high-CTR, accurate, NON-clickbait YouTube metadata in language '{lang}'.
Never use fake promises or spammy '#viral' tags.

Return ONLY JSON:
{{
  "title_variations": [
    "Curiosity-gap title under 65 chars",
    "Benefit/Story stake title under 65 chars",
    "Direct search-friendly title under 65 chars",
    "Contrarian/Unexpected angle title under 65 chars",
    "Concise emotional title under 60 chars"
  ],
  "selected_index": 0,
  "opening_description": "Compelling 1-2 sentence hook (<155 chars) encouraging viewers to watch till the end",
  "search_keywords": ["keyword 1", "keyword 2", "keyword 3", "keyword 4", "keyword 5"],
  "hashtags": ["#RelevantTag1", "#RelevantTag2", "#RelevantTag3", "#RelevantTag4"],
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8"]
}}"""

        valid = lambda d: (
            isinstance(d, dict)
            and isinstance(d.get("title_variations"), list)
            and len(d["title_variations"]) >= 3
            and bool(d.get("opening_description"))
        )
        res = llm_json_fn(prompt, rounds=1, valid=valid)
        if res:
            vars_clean = [str(t).strip()[:92] for t in res["title_variations"] if str(t).strip()][:5]
            while len(vars_clean) < 5:
                vars_clean.append(base_title[:92])
            idx = int(res.get("selected_index") or 0)
            idx = max(0, min(len(vars_clean) - 1, idx))
            clean_hashtags = []
            for h in res.get("hashtags", []):
                hs = str(h).strip()
                if not hs or "viral" in hs.lower():
                    continue
                clean_hashtags.append(hs if hs.startswith("#") else f"#{hs}")
            if not clean_hashtags:
                clean_hashtags = [f"#{style}", "#Storytelling"]
            return {
                "title_variations": vars_clean,
                "selected_title": vars_clean[idx],
                "opening_description": str(res["opening_description"]).strip()[:220],
                "search_keywords": [str(k).strip() for k in res.get("search_keywords", []) if str(k).strip()][:8],
                "hashtags": clean_hashtags[:5],
                "tags": [str(t).strip() for t in res.get("tags", []) if str(t).strip() and "viral" not in str(t).lower()][:15],
                "category_id": cat_id,
            }

    # Deterministic smart fallback
    clean_topic = re.sub(r"[^\w\s!?:'\-\u0080-\uffff]", "", topic).strip() or "Untold Mystery"
    variations = [
        base_title[:90],
        f"Why {clean_topic[:46]} Changed Everything",
        f"The Untold Truth Behind {clean_topic[:42]}",
        f"What Really Happened in {clean_topic[:42]}",
        f"{clean_topic[:55]} Explained",
    ]
    # Deduplicate while preserving 5 entries
    variations = list(dict.fromkeys(v.strip() for v in variations if v.strip()))
    while len(variations) < 5:
        variations.append(f"{clean_topic[:45]} — Full Story #{len(variations) + 1}")

    raw_tags = script.get("hashtags") or []
    clean_hashtags = [
        (h if h.startswith("#") else f"#{h}")
        for h in raw_tags
        if isinstance(h, str) and "viral" not in h.lower()
    ][:5]
    if not clean_hashtags:
        clean_hashtags = [f"#{style}", "#Storytelling", f"#{lang}"]

    keywords = [w for w in re.findall(r"[a-zA-Z0-9\u0080-\uffff]{4,}", topic.lower())][:6]
    if style:
        keywords.append(style.replace("_", " "))

    opening = desc[:155] if desc else (first_scene[:150] or f"Discover the full story of {clean_topic}.")
    tags = list(dict.fromkeys([h.lstrip("#") for h in clean_hashtags] + keywords + [fmt, style.replace("_", " ")]))

    return {
        "title_variations": variations[:5],
        "selected_title": variations[0],
        "opening_description": opening,
        "search_keywords": keywords[:6],
        "hashtags": clean_hashtags,
        "tags": [t for t in tags if t and "viral" not in t.lower()][:14],
        "category_id": cat_id,
    }


# ------------------------------------------------------------
# 3. 3-Concept Automated Thumbnail Generator (1280x720)
# ------------------------------------------------------------
def _pick_thumbnail_words(script: dict, seo: dict) -> str:
    """Extracts 2-4 crisp readable words highlighting the core curiosity hook (no clutter)."""
    raw = str(seo.get("selected_title") or script.get("title") or script.get("topic") or "THE TRUTH").strip()
    clean = re.sub(r"[^\w\s!?'\-\u0080-\uffff]", "", raw).strip()
    stop = {"the", "a", "an", "and", "of", "in", "on", "to", "for", "with", "about", "how", "why", "is", "are"}
    words = clean.split()
    if len(words) <= 4:
        return " ".join(words).upper() or "THE TRUTH"
    key = [w for w in words if w.lower() not in stop]
    chosen = (key[:3] if len(key) >= 2 else words[:3])
    return " ".join(chosen).upper()


def _measure_contrast_score(img_path: Path) -> float:
    """Computes visual sharpness + tonal range score via FFmpeg signalstats."""
    try:
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"movie={_ff_escape(img_path)},signalstats",
                "-show_entries",
                "frame_tags=lavfi.signalstats.YDIF,lavfi.signalstats.SATAVG,lavfi.signalstats.YMAX,lavfi.signalstats.YMIN",
                "-of",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode == 0:
            frames = json.loads(r.stdout or "{}").get("frames", [{}])
            tags = (frames[0] if frames else {}).get("tags", {})
            ymax = float(tags.get("lavfi.signalstats.YMAX", 220))
            ymin = float(tags.get("lavfi.signalstats.YMIN", 20))
            sat = float(tags.get("lavfi.signalstats.SATAVG", 65))
            contrast = min(10.0, max(3.5, ((ymax - ymin) / 24.0) + min(2.0, sat / 60.0)))
            return round(contrast, 2)
    except Exception:
        pass
    size_kb = img_path.stat().st_size / 1024 if img_path.exists() else 0
    return round(min(9.0, 5.5 + size_kb / 80.0), 2)


def generate_thumbnails(
    video: Path,
    script: dict,
    work_dir: Path,
    out_thumb: Path,
    font: str,
    seo: Optional[dict] = None,
    gen_image_fn: Optional[Callable] = None,
    llm_json_fn: Optional[Callable] = None,
    offline: bool = False,
) -> dict:
    """
    Generates 3 distinct 1280x720 thumbnail concepts:
      Concept A: High-contrast curiosity left-split dark gradient + gold headline
      Concept B: Dominant centered focal frame (AI art if online) + dramatic spotlight bar
      Concept C: Bold duotone contrast rim + minimal top-right punch text
    Evaluates all 3 candidates and writes the winning concept to `out_thumb`.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    out_thumb.parent.mkdir(parents=True, exist_ok=True)
    seo_data = seo or {}
    hook_words = _pick_thumbnail_words(script, seo_data)
    wrapped = "\n".join(textwrap.wrap(hook_words, width=12)[:2])
    txt_file = work_dir / "thumb_hook.txt"
    txt_file.write_text(wrapped, encoding="utf-8")

    vid_meta = probe_media(video)
    vid_dur = max(1.0, float(vid_meta.get("duration") or 3.0))

    # Extract 2 distinct source frames from video
    frame_a = work_dir / "thumb_src_a.png"
    frame_b = work_dir / "thumb_src_b.png"
    _run_cmd(["ffmpeg", "-y", "-ss", f"{min(vid_dur * 0.22, vid_dur - 0.3):.2f}", "-i", str(video), "-frames:v", "1", str(frame_a)])
    _run_cmd(["ffmpeg", "-y", "-ss", f"{min(vid_dur * 0.65, vid_dur - 0.3):.2f}", "-i", str(video), "-frames:v", "1", str(frame_b)])

    # Optional dedicated 16:9 AI focal subject for Concept B when online
    ai_focal = work_dir / "thumb_ai_focal.png"
    has_ai_focal = False
    if gen_image_fn and not offline:
        art_prompt = (
            f"YouTube thumbnail centerpiece illustration, dramatic studio rim lighting, high contrast, "
            f"single dominant expressive subject about: {script.get('topic', '')}, clean uncluttered composition, zero text"
        )
        try:
            has_ai_focal = bool(gen_image_fn(art_prompt, ai_focal, style=script.get("style", ""), idx=77))
        except Exception:
            has_ai_focal = False

    src_for_a = frame_a if frame_a.exists() else video
    src_for_b = ai_focal if has_ai_focal else (frame_b if frame_b.exists() else src_for_a)
    src_for_c = frame_b if frame_b.exists() else src_for_a

    concepts_spec = [
        {
            "id": "concept_a_high_contrast_hook",
            "label": "High-Contrast Curiosity Left Split",
            "src": src_for_a,
            "path": work_dir / "thumb_concept_a.jpg",
            "vf": (
                "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
                "eq=contrast=1.22:saturation=1.42:brightness=-0.04,"
                "drawbox=x=0:y=0:w=iw*0.56:h=ih:color=black@0.58:t=fill,"
                f"drawtext=fontfile='{_ff_escape(font)}':textfile='{_ff_escape(txt_file)}':expansion=none"
                ":fontsize=102:fontcolor=0xFFD60A:borderw=8:bordercolor=black:line_spacing=14:x=56:y=(h-th)/2"
            ),
            "clarity_bonus": 0.4,
        },
        {
            "id": "concept_b_dominant_focal",
            "label": "Dominant Subject + Lower Spotlight Banner",
            "src": src_for_b,
            "path": work_dir / "thumb_concept_b.jpg",
            "vf": (
                "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
                "eq=contrast=1.18:saturation=1.38,"
                "drawbox=x=0:y=ih*0.64:w=iw:h=ih*0.36:color=black@0.72:t=fill,"
                "drawbox=x=0:y=ih*0.64:w=iw:h=6:color=0x00E5FF@0.95:t=fill,"
                f"drawtext=fontfile='{_ff_escape(font)}':textfile='{_ff_escape(txt_file)}':expansion=none"
                ":fontsize=88:fontcolor=white:borderw=7:bordercolor=black:line_spacing=10:x=(w-tw)/2:y=h*0.69"
            ),
            "clarity_bonus": 0.7 if has_ai_focal else 0.5,
        },
        {
            "id": "concept_c_duotone_rim",
            "label": "Cinematic Frame + Bold Contrast Frame",
            "src": src_for_c,
            "path": work_dir / "thumb_concept_c.jpg",
            "vf": (
                "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
                "eq=contrast=1.28:saturation=1.48:brightness=-0.06,vignette=angle=PI/4,"
                "drawbox=x=18:y=18:w=iw-36:h=ih-36:color=0xFF4500@0.9:t=8,"
                f"drawtext=fontfile='{_ff_escape(font)}':textfile='{_ff_escape(txt_file)}':expansion=none"
                ":fontsize=96:fontcolor=white:borderw=9:bordercolor=0x111111:line_spacing=12:x=(w-tw)/2:y=h*0.14"
            ),
            "clarity_bonus": 0.35,
        },
    ]

    candidates = []
    for spec in concepts_spec:
        res = _run_cmd(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(spec["src"]),
                "-frames:v",
                "1",
                "-vf",
                spec["vf"],
                "-q:v",
                "2",
                str(spec["path"]),
            ]
        )
        if res.returncode == 0 and spec["path"].exists() and spec["path"].stat().st_size > 1500:
            visual_score = _measure_contrast_score(spec["path"])
            score = round(min(10.0, visual_score + spec["clarity_bonus"]), 2)
            candidates.append(
                {
                    "id": spec["id"],
                    "label": spec["label"],
                    "path": str(spec["path"]),
                    "score": score,
                    "hook_text": hook_words,
                }
            )

    if llm_json_fn and not offline and len(candidates) >= 2:
        try:
            pick_res = llm_json_fn(
                f"""Select the strongest YouTube CTR thumbnail concept for:
Title: {seo_data.get('selected_title') or script.get('title')}
Topic: {script.get('topic')}
Thumbnail Hook Text (<=4 words): {hook_words}
Candidates: {json.dumps([{k: c[k] for k in ('id', 'label', 'score')} for c in candidates])}

Return ONLY JSON: {{"winner_id": "concept_...", "bonus": 0.5, "reason": "short 1-sentence reason"}}""",
                rounds=1,
                valid=lambda d: isinstance(d, dict) and isinstance(d.get("winner_id"), str),
            )
            if pick_res:
                for c in candidates:
                    if c["id"] == pick_res["winner_id"]:
                        c["score"] = round(min(10.0, c["score"] + float(pick_res.get("bonus") or 0.4)), 2)
                        c["selection_reason"] = pick_res.get("reason", "Selected by CTR critique")
        except Exception:
            pass

    if candidates:
        candidates.sort(key=lambda c: -c["score"])
        winner = candidates[0]
        shutil.copy2(winner["path"], out_thumb)
        report = {
            "winner": winner["id"],
            "winner_score": winner["score"],
            "hook_text": hook_words,
            "candidates": candidates,
        }
    else:
        report = {"winner": None, "winner_score": 0.0, "hook_text": hook_words, "candidates": []}

    try:
        (out_thumb.parent / "thumbnail_candidates.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass
    return report


# ------------------------------------------------------------
# 4. 10-Factor Pre-Publish AI Quality Control Evaluator
# ------------------------------------------------------------
QC_FACTORS = (
    "topic_attractiveness",
    "hook_strength",
    "script_quality",
    "retention_potential",
    "visual_relevance",
    "audio_quality",
    "editing_quality",
    "thumbnail_quality",
    "title_quality",
    "originality",
)


def evaluate_video_quality(
    video_path: Path,
    meta: dict,
    script: dict,
    thumb_report: Optional[dict] = None,
    llm_json_fn: Optional[Callable] = None,
    offline: bool = False,
) -> dict:
    """
    Scores a finished video 1-10 across all 10 organic-growth factors before publishing.
    Combines real FFmpeg/ffprobe stream & structural checks with optional LLM editorial grading.
    """
    media = probe_media(video_path)
    scenes = script.get("scenes") or []
    first_line = str((scenes[0] if scenes else {}).get("text") or "").strip()
    low_first = first_line.lower()
    fmt = meta.get("format", "short")
    seo = meta.get("seo") or {}
    min_pass = float(os.environ.get("QC_MIN_SCORE", "6.5"))

    # Deterministic structural telemetry baselines
    has_banned_intro = any(low_first.startswith(b) for b in BANNED_OPENINGS)
    hook_words = len(first_line.split())
    hook_base = 3.5 if has_banned_intro else (8.4 if 4 <= hook_words <= 18 else 7.2)

    audio_base = 8.6 if (media.get("audio_codec") and media.get("sample_rate", 0) >= 44100) else 5.0
    if meta.get("bgm_mixed"):
        audio_base = min(9.5, audio_base + 0.7)

    dur = float(media.get("duration") or 0.0)
    expected_w, expected_h = (1920, 1080) if fmt == "long" else (1080, 1920)
    res_ok = media.get("width") == expected_w and media.get("height") == expected_h
    editing_base = 8.4 if (media.get("valid") and res_ok and dur >= 1.5) else 4.5
    if meta.get("transitions_applied"):
        editing_base = min(9.5, editing_base + 0.5)

    thumb_score = float((thumb_report or {}).get("winner_score") or (7.5 if (video_path.parent / "thumbnail.jpg").exists() else 4.5))
    title_str = str(seo.get("selected_title") or meta.get("title") or "")
    title_base = 8.2 if (15 <= len(title_str) <= 72 and "#viral" not in title_str.lower()) else 6.2

    scores = {
        "topic_attractiveness": round(float(meta.get("topic_score") or 7.6), 2),
        "hook_strength": round(hook_base, 2),
        "script_quality": round(min(9.2, 6.8 + min(2.0, len(scenes) * 0.25)), 2),
        "retention_potential": round(8.0 if (not has_banned_intro and len(scenes) >= 4) else 6.4, 2),
        "visual_relevance": round(8.3 if meta.get("ai_video_clips", 0) > 0 or len(scenes) >= 3 else 7.0, 2),
        "audio_quality": round(audio_base, 2),
        "editing_quality": round(editing_base, 2),
        "thumbnail_quality": round(min(10.0, max(1.0, thumb_score)), 2),
        "title_quality": round(title_base, 2),
        "originality": round(8.2 if not has_banned_intro else 5.8, 2),
    }
    weaknesses = []
    if has_banned_intro:
        weaknesses.append("Opening uses banned generic greeting instead of immediate curiosity hook.")
    if not res_ok:
        weaknesses.append(f"Resolution {media.get('width')}x{media.get('height')} != {expected_w}x{expected_h}.")

    if llm_json_fn and not offline:
        prompt = f"""You are an elite YouTube Growth & Quality Control Auditor.
Evaluate this produced video candidate across all 10 factors (integer or decimal 1-10):
Title: {title_str}
Topic: {meta.get('topic')}
Format: {fmt} ({dur:.1f}s, {len(scenes)} scenes)
0-3s Hook Line: "{first_line}"
Full Script Summary: {' | '.join(s.get('text', '')[:90] for s in scenes[:5])}
Thumbnail Hook Text: {(thumb_report or {}).get('hook_text', '')}

Return ONLY JSON:
{{
  "scores": {{
    "topic_attractiveness": 8.0,
    "hook_strength": 8.5,
    "script_quality": 8.0,
    "retention_potential": 8.0,
    "visual_relevance": 8.0,
    "audio_quality": 8.5,
    "editing_quality": 8.5,
    "thumbnail_quality": 8.0,
    "title_quality": 8.5,
    "originality": 8.0
  }},
  "weaknesses": ["short note if anything is weak"],
  "recommendations": ["concrete fix for next iteration"]
}}"""
        valid = lambda d: (
            isinstance(d, dict)
            and isinstance(d.get("scores"), dict)
            and all(k in d["scores"] for k in QC_FACTORS)
        )
        llm_res = llm_json_fn(prompt, rounds=1, valid=valid)
        if llm_res:
            for k in QC_FACTORS:
                try:
                    llm_v = max(1.0, min(10.0, float(llm_res["scores"][k])))
                    # Blend LLM judgement cleanly with objective stream/structure metrics
                    scores[k] = round(0.55 * llm_v + 0.45 * scores[k], 2)
                except Exception:
                    pass
            weaknesses.extend([str(w) for w in llm_res.get("weaknesses", []) if str(w).strip()][:3])

    overall = round(sum(scores.values()) / len(QC_FACTORS), 2)
    passed = overall >= min_pass and media.get("valid", False) and not has_banned_intro
    report = {
        "overall_score": overall,
        "min_threshold": min_pass,
        "passed": bool(passed),
        "scores": scores,
        "media_telemetry": media,
        "weaknesses": weaknesses,
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        (video_path.parent / "quality_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass
    return report


# ------------------------------------------------------------
# 5. YouTube Analytics API v2 & Channel Learning Engine
# ------------------------------------------------------------
def _query_yt_analytics(token: str, params: dict) -> Optional[dict]:
    try:
        r = requests.get(
            YT_ANALYTICS_URL,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=25,
        )
        if r.ok:
            return r.json()
        print(f"  YT Analytics ({params.get('dimensions', 'channel')}): HTTP {r.status_code}")
    except requests.RequestException as e:
        print(f"  YT Analytics request failed: {type(e).__name__}")
    return None


def _parse_analytics_rows(payload: Optional[dict]) -> list[dict]:
    if not payload or not isinstance(payload.get("rows"), list):
        return []
    cols = [h.get("name") for h in payload.get("columnHeaders", [])]
    out = []
    for row in payload["rows"]:
        if len(row) == len(cols):
            out.append(dict(zip(cols, row)))
    return out


def fetch_youtube_analytics(token: str, state: dict) -> dict:
    """
    Pulls real performance data from YouTube Analytics API v2:
      - views, averageViewDuration, averageViewPercentage, likes, comments, subscribersGained
      - impressions & CTR (requested separately so missing scope or low impressions won't break core metrics)
      - traffic sources (insightTrafficSourceType)
      - subscribed vs non-subscribed / returning behavior
      - audience retention drop-off curve on recent videos
    """
    if not token or os.environ.get("YT_ANALYTICS_SYNC", "1") != "1":
        return {}

    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=45)).strftime("%Y-%m-%d")
    end_date = now.strftime("%Y-%m-%d")
    snapshot: dict[str, Any] = {
        "synced_at": now.isoformat(timespec="seconds"),
        "videos": {},
        "traffic_sources": {},
        "subscribed_status": {},
        "retention_curves": {},
    }

    # 1. Per-video core engagement & retention
    vid_payload = _query_yt_analytics(
        token,
        {
            "ids": "channel==MINE",
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": "video",
            "metrics": "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,subscribersGained",
            "sort": "-views",
            "maxResults": 50,
        },
    )
    for row in _parse_analytics_rows(vid_payload):
        vid = row.get("video")
        if vid:
            snapshot["videos"][vid] = {
                "views": int(row.get("views") or 0),
                "estimated_minutes": float(row.get("estimatedMinutesWatched") or 0.0),
                "avg_view_duration": float(row.get("averageViewDuration") or 0.0),
                "avg_view_percentage": float(row.get("averageViewPercentage") or 0.0),
                "likes": int(row.get("likes") or 0),
                "comments": int(row.get("comments") or 0),
                "subscribers_gained": int(row.get("subscribersGained") or 0),
            }

    # 2. Impressions & CTR (separate query; safe if unsupported on channel yet)
    ctr_payload = _query_yt_analytics(
        token,
        {
            "ids": "channel==MINE",
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": "video",
            "metrics": "videoThumbnailImpressions,videoThumbnailImpressionsClickRate",
            "sort": "-videoThumbnailImpressions",
            "maxResults": 50,
        },
    )
    for row in _parse_analytics_rows(ctr_payload):
        vid = row.get("video")
        if vid:
            entry = snapshot["videos"].setdefault(vid, {})
            entry["impressions"] = int(row.get("videoThumbnailImpressions") or 0)
            entry["ctr"] = round(float(row.get("videoThumbnailImpressionsClickRate") or 0.0) * 100.0, 2)

    # 3. Traffic sources
    tr_payload = _query_yt_analytics(
        token,
        {
            "ids": "channel==MINE",
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": "insightTrafficSourceType",
            "metrics": "views,estimatedMinutesWatched",
            "sort": "-views",
        },
    )
    for row in _parse_analytics_rows(tr_payload):
        src = row.get("insightTrafficSourceType")
        if src:
            snapshot["traffic_sources"][src] = int(row.get("views") or 0)

    # 4. Returning / subscribed viewer breakdown
    sub_payload = _query_yt_analytics(
        token,
        {
            "ids": "channel==MINE",
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": "subscribedStatus",
            "metrics": "views,averageViewPercentage",
        },
    )
    for row in _parse_analytics_rows(sub_payload):
        st = row.get("subscribedStatus")
        if st:
            snapshot["subscribed_status"][st] = {
                "views": int(row.get("views") or 0),
                "avg_retention": float(row.get("averageViewPercentage") or 0.0),
            }

    # 5. Relative audience retention curve for top 3 videos
    for vid in list(snapshot["videos"].keys())[:3]:
        ret_payload = _query_yt_analytics(
            token,
            {
                "ids": "channel==MINE",
                "startDate": start_date,
                "endDate": end_date,
                "dimensions": "elapsedVideoTimeRatio",
                "metrics": "audienceWatchRatio",
                "filters": f"video=={vid}",
            },
        )
        rows = _parse_analytics_rows(ret_payload)
        if rows:
            drop_points = [
                round(float(r["elapsedVideoTimeRatio"]), 2)
                for r in rows
                if float(r.get("audienceWatchRatio") or 1.0) < 0.45
            ]
            snapshot["retention_curves"][vid] = {
                "points": len(rows),
                "first_drop_ratio": drop_points[0] if drop_points else None,
            }

    # Merge into state["videos"]
    for v in state.get("videos", []):
        m = snapshot["videos"].get(v.get("id"))
        if m:
            v.update(m)

    if snapshot["videos"] or snapshot["traffic_sources"]:
        state["analytics_snapshot"] = snapshot
    return snapshot


def analyze_channel_learnings(state: dict) -> dict:
    """
    Extracts actionable creative & packaging learnings from real video performance
    to guide future topic research, scripts, hooks, titles, thumbnails, and editing.
    """
    videos = list(state.get("videos") or [])
    snapshot = state.get("analytics_snapshot") or {}

    def _perf_score(v: dict) -> float:
        views = float(v.get("views") or 0)
        ret = float(v.get("avg_view_percentage") or 50.0) / 50.0
        ctr = 1.0 + (float(v.get("ctr") or 4.0) / 10.0)
        likes = float(v.get("likes") or 0) * 5.0
        return (views + likes) * ret * ctr

    ranked = sorted(videos, key=_perf_score, reverse=True)
    winning_styles = []
    top_topics = []
    top_hooks = []
    top_title_patterns = []
    top_thumb_concepts = []
    short_durs = []
    long_durs = []

    for v in ranked[:12]:
        if _perf_score(v) <= 0 and len(ranked) > 3:
            continue
        if v.get("style") and v["style"] not in winning_styles:
            winning_styles.append(v["style"])
        t_label = v.get("topic") or v.get("title")
        if t_label and t_label not in top_topics:
            top_topics.append(t_label)
        if v.get("hook") and v["hook"] not in top_hooks:
            top_hooks.append(v["hook"])
        if v.get("title") and len(top_title_patterns) < 4:
            top_title_patterns.append(v["title"])
        if v.get("thumbnail_concept") and v["thumbnail_concept"] not in top_thumb_concepts:
            top_thumb_concepts.append(v["thumbnail_concept"])
        dur = float(v.get("duration") or v.get("avg_view_duration") or 0)
        if dur > 0:
            if v.get("fmt") == "long":
                long_durs.append(dur)
            else:
                short_durs.append(dur)

    curves = snapshot.get("retention_curves") or {}
    drop_points = [c["first_drop_ratio"] for c in curves.values() if c.get("first_drop_ratio") is not None]
    avg_drop = round(sum(drop_points) / len(drop_points), 2) if drop_points else None

    learnings = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "videos_analyzed": len(videos),
        "top_topics": top_topics[:6],
        "winning_styles": winning_styles[:5],
        "best_hooks": top_hooks[:5],
        "top_title_patterns": top_title_patterns[:4],
        "top_thumbnail_concepts": top_thumb_concepts[:3],
        "optimal_short_duration": int(max(24, min(56, round(sum(short_durs) / len(short_durs))))) if short_durs else 38,
        "optimal_long_duration": int(max(240, min(480, round(sum(long_durs) / len(long_durs))))) if long_durs else 330,
        "avg_drop_off_ratio": avg_drop,
        "traffic_source_breakdown": snapshot.get("traffic_sources") or {},
        "returning_viewers": snapshot.get("subscribed_status") or {},
    }
    state["learnings"] = learnings

    # Also update style weights subtly when we have multi-video signal
    scored_rows = [(v, _perf_score(v)) for v in videos if _perf_score(v) > 0]
    if len(scored_rows) >= 4:
        avg_s = sum(s for _, s in scored_rows) / len(scored_rows) or 1.0
        weights = state.setdefault("weights", {})
        for key in ("category", "style"):
            buckets: dict[str, list[float]] = {}
            for v, sc in scored_rows:
                if v.get(key):
                    buckets.setdefault(v[key], []).append(sc)
            updated = {
                k: round(min(2.0, max(0.5, (sum(vals) / len(vals)) / avg_s)), 2)
                for k, vals in buckets.items()
                if len(vals) >= 1
            }
            if updated:
                weights.setdefault(key, {}).update(updated)

    return learnings
