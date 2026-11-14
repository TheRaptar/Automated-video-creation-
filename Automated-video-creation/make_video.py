#!/usr/bin/env python3
"""
RAPTAR Fully Automatic Video Generator
=====================================
Generates animated Reels, YouTube Shorts, Storybooks, and Long-form YouTube videos
across multiple global languages.

Pipeline:
  Gemini 4 Hydrogen (topic, script, choreography, SVG vector scenes, localization)
  -> Edge-TTS (multilingual neural voiceovers)
  -> AI Animation / Stock Footage (Pollinations, Gemini SVG, Pexels, Pixabay, 2.5D Ken Burns)
  -> FFmpeg (libass multilingual kinetic subtitles, constant-timebase concat, chapter thumbnails)

Usage:
    python make_video.py                         # auto Short / Animated Reel
    python make_video.py --format animated       # 100% AI animated Reel / Short
    python make_video.py --format story          # AI illustrated/animated story
    python make_video.py --format long           # 5-7 min long-form video
    python make_video.py --lang ta               # native Tamil narration & subtitles
    python make_video.py --lang en --dub ta,hi   # primary EN + localized TA & HI outputs
"""
import argparse
import asyncio
import base64
import json
import os
import random
import re
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

OFFLINE = os.environ.get("OFFLINE_TEST") == "1"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-4-hydrogen")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GEMINI_BASE = os.environ.get("GEMINI_BASE", "https://generativelanguage.googleapis.com/v1beta")
GROQ_BASE = os.environ.get("GROQ_BASE", "https://api.groq.com/openai/v1")
TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-GuyNeural")
REVIEW = os.environ.get("REVIEW_SCRIPT", "1") == "1"
ANIMATED_MODE = os.environ.get("ANIMATED_MODE", "auto").strip().lower()  # auto | always | never
HF_TOKEN = (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN") or "").strip()
FREE_VIDEO_PROVIDER = os.environ.get("FREE_VIDEO_PROVIDER", "auto").strip().lower()  # auto | i2v | t2v | kenburns
LOCAL_COMFY_URL = os.environ.get("LOCAL_COMFY_URL", "").strip().rstrip("/")
VIDEO_AI_CLIPS_MAX = max(0, int(os.environ.get("VIDEO_AI_CLIPS_MAX", "8")))

try:
    from raptar_agent import RaptarAgent, LANGUAGES, ANIMATED_STYLES
except ImportError:
    RaptarAgent = None
    LANGUAGES = {"en": {"name": "English", "native_name": "English", "yt_code": "en", "font_family": "Noto Sans", "rtl": False, "voices": {"default": TTS_VOICE}, "cta": "Follow for more!"}}
    ANIMATED_STYLES = {"animated_myth", "animated_comedy", "animated_anime", "fable", "story", "legend"}

WORK, OUT, HISTORY, STATE = Path("work"), Path("output"), Path("history.json"), Path("state.json")
FPS = 30
WORDS_PER_CAPTION = 3

# Per-format settings, filled in by configure()
W, H = 1080, 1920
CAPTIONS = True
CLIP_LEN = 4.5
SIZE_ORDER = ("large", "medium", "small", "tiny")
ORIENT = "portrait"
CURRENT_FORMAT = "short"


def configure(fmt: str) -> None:
    global W, H, CAPTIONS, CLIP_LEN, SIZE_ORDER, ORIENT, CURRENT_FORMAT
    CURRENT_FORMAT = fmt
    if fmt == "long":
        W, H, CAPTIONS, ORIENT = 1920, 1080, False, "landscape"
        CLIP_LEN = float(os.environ.get("CLIP_SECONDS_LONG", "6"))
        SIZE_ORDER = ("medium", "large", "small", "tiny")
    else:
        W, H, CAPTIONS, ORIENT = 1080, 1920, True, "portrait"
        CLIP_LEN = float(os.environ.get("CLIP_SECONDS", "4.5"))
        SIZE_ORDER = ("large", "medium", "small", "tiny")


def pick_seconds(env_name: str, default: str) -> int:
    raw = os.environ.get(env_name, default)
    if "-" in raw:
        a, b = raw.split("-", 1)
        return random.randint(int(a), int(b))
    return int(raw)


DEFAULT_CATEGORIES = [
    "3D Animated Mythological & Cultural Epics",
    "3D Cartoon Character Comedies & Adventures",
    "Anime Fantasy & Folklore Shorts",
    "Horror & Supernatural Thrillers",
    "Children's Whimsical Fables & Adventures",
    "Adult Psychological Thrillers & Sci-Fi",
    "Ancient Myths, Legends & Epic Lore",
    "Photorealistic AI Influencer & Fitness Routines",
]
CATEGORIES = [c.strip() for c in os.environ.get("CATEGORIES", "").split(",") if c.strip()] or DEFAULT_CATEGORIES

STYLES = {
    "animated_myth": "3D Pixar/cinematic mythological animation: sacred fables, ancient wisdom, luminous lighting.",
    "animated_comedy": "3D cartoon buddy comedy: vibrant expressive characters, humorous cultural twists.",
    "animated_anime": "Cinematic Japanese anime aesthetic: dramatic skies, vivid motion, emotional twists.",
    "horror": "Supernatural horror & creepypasta: eerie dread, atmospheric suspense, and shocking dark twists.",
    "fable": "Children's storybook fable: whimsical magic, friendly characters, and uplifting morals.",
    "thriller": "Adult psychological thriller: high-stakes tension, hidden motives, and gripping dramatic twists.",
    "scifi": "Mind-bending sci-fi fiction: speculative science anomalies, time loops, and cosmic mysteries.",
    "legend": "Epic mythology & folklore: ancient lore, forgotten civilizations, and legendary heroic sagas.",
    "mystery": "Unraveling enigmatic fiction: sudden revelations, hidden clues, and clever narrative twists.",
    "fitness_glamour": "Photorealistic AI influencer fitness & lifestyle: aesthetic activewear routines and glow.",
    "allure": "Magnetic allure & psychological intrigue.",
    "chemistry": "Emotional dynamics & chemistry.",
    "charm": "Clever wit and charisma.",
    "seduction": "Seductive suspense and intrigue.",
    "romance": "Sensual romance and aesthetics.",
    "fact": "Fact-based storytelling with dramatic narrative.",
    "story": "Illustrated storybook visual narrative.",
}

LANG_FONT_MAP = {
    "ta": [
        "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSerifTamil-Bold.ttf",
    ],
    "hi": [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSerifDevanagari-Bold.ttf",
    ],
    "ar": [
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoKufiArabic-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
    ],
    "ja": [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/unifont/unifont_jp.otf",
    ],
    "ko": [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/unifont/unifont.otf",
    ],
}

FONT_CANDIDATES = [
    os.environ.get("FONT_PATH", ""),
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def report_status(stage: str, progress: int, message: str, details: dict = None) -> None:
    """Emits live agent telemetry to agent_status.json."""
    try:
        data = {
            "stage": stage,
            "progress": progress,
            "message": message,
            "timestamp": time.time(),
            "details": details or {},
        }
        Path("agent_status.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def find_font(lang: str = "en") -> str:
    """Finds the best bold TTF/TTC font for the requested language script."""
    lang = (lang or "en").lower().strip()
    for p in LANG_FONT_MAP.get(lang, []):
        if p and Path(p).exists():
            return p
    # Try dynamic search for CJK/Noto script fonts via fc-match or glob
    if lang in ("ja", "ko"):
        for pat in ("**/*CJK*Bold*", "**/*CJK*", "**/unifont_jp*"):
            for m in Path("/usr/share/fonts").glob(pat):
                if m.is_file():
                    return str(m)
    for p in FONT_CANDIDATES:
        if p and Path(p).exists():
            return p
    for fallback in Path("/usr/share/fonts").glob("**/*.ttf"):
        if "Bold" in fallback.name or "Sans" in fallback.name:
            return str(fallback)
    sys.exit("No font found. Set FONT_PATH to a .ttf file.")


def ff_escape(path) -> str:
    return str(path).replace("\\", "/").replace(":", r"\:")


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Command failed: {' '.join(cmd[:6])} ...\n{r.stderr[-2000:]}")


def media_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def _valid_video(path: Path) -> bool:
    """Checks via ffprobe that a downloaded or rendered video has a valid video stream and >0.3s duration."""
    try:
        if not path.exists() or path.stat().st_size < 1024:
            return False
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height:format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=20,
        )
        if r.returncode != 0:
            return False
        parts = [x.strip() for x in r.stdout.replace("\n", ",").split(",") if x.strip()]
        if len(parts) < 3:
            return False
        w, h, dur = int(float(parts[0])), int(float(parts[1])), float(parts[2])
        return w >= 120 and h >= 120 and dur >= 0.3
    except Exception:
        return False


def fmt_ts(t: float) -> str:
    t = int(t)
    h, m, s = t // 3600, (t % 3600) // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ------------------------------------------------------------ history + state
def load_history() -> list[str]:
    try:
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_history(items: list[str]) -> None:
    HISTORY.write_text(json.dumps(items[-300:], indent=2, ensure_ascii=False), encoding="utf-8")


def load_state() -> dict:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------ LLM layer (Gemini -> Groq)
_DEAD_GEMINI: set = set()


def _parse_json(text: str):
    cleaned = text.strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0]
    return json.loads(cleaned.strip())


def _gemini_models() -> list[str]:
    names = [GEMINI_MODEL, "gemini-3.8-flash", "gemini-3.1-flash-lite", "gemini-flash-latest"]
    names = list(dict.fromkeys(names))
    if GEMINI_API_KEY and not OFFLINE:
        try:
            r = requests.get(
                f"{GEMINI_BASE}/models",
                params={"pageSize": 200},
                headers={"x-goog-api-key": GEMINI_API_KEY, "User-Agent": "aistudio-build"},
                timeout=30,
            )
            if r.ok:
                skip = ("image", "tts", "audio", "live", "embed", "native", "robotics", "computer",
                        "preview", "exp", "omni", "thinking", "pro", "carbon", "argon", "1.5", "2.0")
                found = sorted(
                    (m["name"].split("/")[-1] for m in r.json().get("models", [])
                     if "generateContent" in m.get("supportedGenerationMethods", [])
                     and "flash" in m["name"] and not any(s in m["name"] for s in skip)),
                    reverse=True,
                )
                names += [n for n in found if n not in names]
        except requests.RequestException as e:
            print(f"  (could not list Gemini models: {type(e).__name__})")
    return names[:5]


def _gemini_json(prompt: str, rounds: int, valid):
    if not GEMINI_API_KEY:
        return None
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    headers = {"x-goog-api-key": GEMINI_API_KEY, "User-Agent": "aistudio-build"}
    models = _gemini_models()
    print(f"  Gemini models: {', '.join(models)}")
    for rnd in range(rounds):
        for model in models:
            if model in _DEAD_GEMINI:
                continue
            try:
                r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent",
                                  json=body, headers=headers, timeout=60)
            except requests.RequestException as e:
                print(f"  {model}: network error ({type(e).__name__})")
                continue
            if r.ok:
                try:
                    data = _parse_json(r.json()["candidates"][0]["content"]["parts"][0]["text"])
                    if valid(data):
                        return data
                    print(f"  {model}: answer failed validation")
                except Exception as e:
                    print(f"  {model}: unusable answer ({e})")
                continue
            print(f"  {model}: HTTP {r.status_code} {r.text[:100].strip()}")
            if r.status_code in (401, 403):
                print("  Gemini rejected the API key.")
                return None
            if r.status_code == 429 and "quota" in r.text.lower():
                _DEAD_GEMINI.add(model)
        if rnd < rounds - 1:
            time.sleep(10)
    return None


def _groq_json(prompt: str, rounds: int, valid):
    if not GROQ_API_KEY:
        return None
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    models = [GROQ_MODEL]
    try:
        r = requests.get(f"{GROQ_BASE}/models", headers=headers, timeout=30)
        if r.ok:
            skip = ("whisper", "guard", "tts", "embed", "playai", "vision", "distil", "orpheus")
            found = sorted((m["id"] for m in r.json().get("data", [])
                            if not any(x in m["id"] for x in skip)), reverse=True)
            models += [m for m in found if m not in models][:3]
    except requests.RequestException:
        pass
    print(f"  Groq models: {', '.join(models)}")
    for rnd in range(rounds):
        for model in models:
            try:
                r = requests.post(f"{GROQ_BASE}/chat/completions", headers=headers, timeout=60, json={
                    "model": model, "temperature": 0.9,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": prompt}]})
            except requests.RequestException as e:
                print(f"  groq {model}: network error ({type(e).__name__})")
                continue
            if r.ok:
                try:
                    data = _parse_json(r.json()["choices"][0]["message"]["content"])
                    if valid(data):
                        return data
                    print(f"  groq {model}: answer failed validation")
                except Exception as e:
                    print(f"  groq {model}: unusable answer ({e})")
                continue
            print(f"  groq {model}: HTTP {r.status_code} {r.text[:100].strip()}")
            if r.status_code in (401, 403):
                return None
        if rnd < rounds - 1:
            time.sleep(10)
    return None


def llm_json(prompt: str, rounds: int, valid):
    """Try Gemini first, then Groq. Returns a dict or None."""
    return _gemini_json(prompt, rounds, valid) or _groq_json(prompt, rounds, valid)


# ------------------------------------------------------------ 1. topic + script + review
def _valid_scenes(d, minimum=3) -> bool:
    return (isinstance(d, dict) and isinstance(d.get("scenes"), list) and len(d["scenes"]) >= minimum
            and all(isinstance(s, dict) and isinstance(s.get("text"), str) and s["text"].strip()
                    for s in d["scenes"]))


def _normalize(script: dict) -> dict:
    motions = ("zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "dolly_pulse")
    for idx, sc in enumerate(script["scenes"]):
        terms = sc.get("search_terms") or [sc.get("search_term")]
        terms = [t.strip() for t in terms if isinstance(t, str) and t.strip()]
        sc["search_terms"] = terms or ["nature"]
        sc["text"] = sc["text"].strip()
        if not sc.get("camera_motion"):
            sc["camera_motion"] = motions[idx % len(motions)]
        sc.setdefault("fx", "cinematic")
    script.setdefault("topic", script.get("title", "unknown"))
    script.setdefault("title", script["topic"])
    script.setdefault("description", "")
    script.setdefault("language", "en")
    script["hashtags"] = [h if h.startswith("#") else "#" + h
                          for h in script.get("hashtags", []) if isinstance(h, str)][:6]
    chapters = [s["heading"] for s in script["scenes"] if s.get("heading")]
    if chapters:
        script["chapters"] = chapters
    return script


def _topic_line(topic, history, state, long_form: bool):
    """Returns (prompt text about the topic, chosen category). Avoids recent categories and topics."""
    if topic:
        return f"Topic: {topic}", None
    recent = state.get("recent_categories", [])
    keep = recent[-min(4, max(0, len(CATEGORIES) - 1)):] if len(CATEGORIES) > 1 else []
    category = weighted_choice([c for c in CATEGORIES if c not in keep] or CATEGORIES,
                               state.get("weights", {}).get("category", {}))
    avoid = "; ".join(history[-80:]) or "none yet"
    depth = ("a rich narrative epic or deep-dive story supporting 5-7 minutes with distinct chapters"
             if long_form else "a captivating, surprising story or animated tale")
    return (f"Category: {category}\nChoose ONE fresh topic inside this category: {depth}. "
            f"Do NOT reuse or closely resemble any of these previous topics: {avoid}"), category


def _review_texts(title: str, texts: list[str], lang: str = "en", style: str = "story") -> list[str]:
    """Secondary AI pass checking quality, storytelling flow, and policy safety."""
    if not REVIEW or OFFLINE:
        return texts
    lang_name = (LANGUAGES.get(lang) or LANGUAGES["en"])["name"]
    prompt = f"""You are a senior editor and safety reviewer for a {lang_name} ({style}) video titled "{title}".
Narration scenes (JSON list in {lang_name}): {json.dumps(texts, ensure_ascii=False)}

Return ONLY JSON like {{"scenes": ["...", "..."], "issues": ["short note per change"]}} where:
- "scenes" has exactly {len(texts)} strings, in the same order, written in {lang_name}.
- Keep creative/mythological/animated storytelling intact; polish clarity, hooks, and spoken rhythm.
- Remove anything unsafe or policy-violating (hate speech, graphic violence, explicit content).
- Keep roughly the same word count per scene (do not shorten!)."""
    valid = lambda d: (isinstance(d, dict) and isinstance(d.get("scenes"), list)
                       and len(d["scenes"]) == len(texts)
                       and all(isinstance(x, str) and x.strip() for x in d["scenes"]))
    data = llm_json(prompt, rounds=1, valid=valid)
    if not data:
        print("  Quality check skipped (no answer) - keeping original text.")
        return texts
    new = [x.strip() for x in data["scenes"]]
    print(f"  Quality check: {sum(a != b for a, b in zip(texts, new))} scene(s) polished.")
    return new


def _get_profile(category_or_style: str, lang: str = "en") -> dict:
    if RaptarAgent:
        return RaptarAgent.get_audience_profile(category_or_style, lang=lang)
    lang_meta = LANGUAGES.get(lang, LANGUAGES["en"])
    voice = lang_meta["voices"].get("default", TTS_VOICE)
    return {
        "target_audience": "all_ages", "style": "animated_myth", "voice": voice, "rate": "+2%",
        "tone": "engaging and cinematic", "subtitle_color": "0x00E5FF", "subtitle_shadow": "0x000000",
        "animated": True, "art_style": "3D Pixar cinematic animation, 9:16 vertical",
        "guidelines": "captivating storytelling", "language": lang,
    }


def generate_short(topic, history, state, lang: str = "en") -> dict:
    total = pick_seconds("VIDEO_SECONDS", "40-60")
    lang_meta = LANGUAGES.get(lang, LANGUAGES["en"])
    if OFFLINE:
        prof = _get_profile("animated_myth", lang=lang)
        return _normalize({
            "topic": "offline test", "title": "Offline Animated Test", "description": "Testing.",
            "hashtags": ["#test", "#animation"], "category": None, "style": "animated_myth",
            "language": lang, "voice_profile": {"voice": prof["voice"], "rate": prof["rate"]},
            "subtitle_color": prof["subtitle_color"],
            "scenes": [
                {"text": "Every grain of sand builds an unforgettable bridge across the ocean.",
                 "search_terms": ["ocean"], "image_prompt": "3D Pixar squirrel carrying sand by ocean bridge"},
                {"text": "Even the smallest hero can change destiny when guided by kindness and courage.",
                 "search_terms": ["forest", "sunset"], "image_prompt": "glowing golden sunset forest blessing"},
                {"text": lang_meta["cta"],
                 "search_terms": ["sunrise"], "image_prompt": "finished grand ocean bridge sunrise"},
            ]})

    lo, words = max(5, total // 9), int(total * 2.5)
    topic_line, category = _topic_line(topic, history, state, False)
    hint = state.get("_style_hint")
    if hint in STYLES:
        style_key = hint
    else:
        style_key = weighted_choice([k for k in STYLES if k != state.get("last_style")] or list(STYLES),
                                    state.get("weights", {}).get("style", {}))
    profile = _get_profile(category or style_key, lang=lang)
    style_key = profile.get("style", style_key)

    prompt = f"""You are a master animation director, storyteller, and multi-language creator.
Your mission is to craft a captivating video tailored for target audience '{profile['target_audience']}' in language {lang_meta['name']} ({lang}).

Genre Style: {STYLES.get(style_key, style_key)}
Narration Language: {lang_meta['name']} ({lang}) — Write "title", "description", "hashtags", and all scene "text" in natural, idiomatic {lang_meta['name']}.
Visual Prompts: Write "image_prompt" and "search_terms" strictly in ENGLISH.
Art Style: {profile['art_style']}
Tone & Pacing: {profile['tone']}
Guidelines: {profile['guidelines']}

{topic_line}
{_trend_hint(state)}

Return ONLY JSON:
{{
  "topic": "short topic name",
  "title": "high-CTR title under 65 chars in {lang_meta['name']} with emoji",
  "description": "1-2 sentence alluring description in {lang_meta['name']}",
  "hashtags": ["#story", "#animation", "#{lang}", "#viral"],
  "language": "{lang}",
  "target_audience": "{profile['target_audience']}",
  "style": "{style_key}",
  "art_style": "{profile['art_style']}",
  "characters": "one English sentence describing consistent character design",
  "voice_profile": {{"voice": "{profile['voice']}", "rate": "{profile['rate']}"}},
  "subtitle_color": "{profile['subtitle_color']}",
  "scenes": [{{
    "text": "spoken narration in {lang_meta['name']}",
    "search_terms": ["english visual query 1", "english visual query 2"],
    "image_prompt": "detailed 9:16 animated/cinematic scene prompt in ENGLISH, no text/letters",
    "motion_prompt": "dynamic character action and smooth camera motion in ENGLISH for 24fps AI video",
    "camera_motion": "zoom_in|zoom_out|pan_left|pan_right|pan_up|dolly_pulse",
    "fx": "cinematic|warm_glow|sparkles|eerie_vignette|vibrant"
  }}]
}}
Rules:
- {lo} to {lo + 2} scenes, about {total} seconds (~{int(words * 0.9)} words total).
- Scene 1 is an instant scroll-stopping hook under 12 words.
- Last scene ends with a compelling follow CTA in {lang_meta['name']}.
- No text, watermarks, or letters requested inside image_prompt."""

    data = llm_json(prompt, rounds=2, valid=_valid_scenes)
    if not data:
        if RaptarAgent:
            agent = RaptarAgent()
            pick = agent.evaluate_and_pick_topic({}, CATEGORIES, format_type="short", lang=lang)
            data = agent.plan_script(pick, format_type="short", lang=lang)
        else:
            sys.exit("Could not get a script from Gemini or Groq.")

    script = _normalize(data)
    new = _review_texts(script["title"], [s["text"] for s in script["scenes"]], lang=lang, style=style_key)
    for sc, t in zip(script["scenes"], new):
        sc["text"] = t
    script.update(category=category, style=style_key, language=lang,
                  target_audience=profile["target_audience"],
                  voice_profile=script.get("voice_profile", {"voice": profile["voice"], "rate": profile["rate"]}),
                  subtitle_color=profile.get("subtitle_color", "0x00E5FF"),
                  art_style=script.get("art_style", profile["art_style"]))
    return script


def generate_story(topic, history, state, lang: str = "en", animated: bool = False) -> dict:
    """Produces a 100% AI-animated Reel / Storybook Short with multi-language voiceover & camera choreography."""
    total = pick_seconds("VIDEO_SECONDS", "40-60")
    topic_line, category = _topic_line(topic, history, state, False)
    style_hint = state.get("_style_hint") or ""
    if animated and not style_hint and not category:
        category = random.choice([
            "3D Animated Mythological & Cultural Epics",
            "3D Cartoon Character Comedies & Adventures",
            "Anime Fantasy & Folklore Shorts",
        ])
    profile = _get_profile(style_hint or category or "animated_myth", lang=lang)
    lang_meta = LANGUAGES.get(lang, LANGUAGES["en"])
    style_key = profile.get("style", "animated_myth" if animated else "story")

    if OFFLINE:
        STORY.update(art_style=profile["art_style"], characters="expressive 3D animated character")
        return _normalize({
            "topic": "offline animated story", "title": "The Golden Bridge Squirrel",
            "description": "Offline animated story demonstration.",
            "hashtags": ["#AIAnimation", "#story", f"#{lang}"], "category": category,
            "style": style_key, "language": lang, "target_audience": profile["target_audience"],
            "voice_profile": {"voice": profile["voice"], "rate": profile["rate"]},
            "subtitle_color": profile["subtitle_color"],
            "scenes": [
                {"text": "In an enchanted forest bathed in golden light, a tiny hero began an impossible journey.",
                 "image_prompt": "3D Pixar animated forest with golden sunbeams and cute animal hero, 9:16",
                 "camera_motion": "zoom_in", "fx": "warm_glow", "search_terms": ["enchanted forest sunset"]},
                {"text": "Though the giants laughed, each small step built something greater than fear.",
                 "image_prompt": "3D animated squirrel placing sand grain by gleaming turquoise ocean bridge, 9:16",
                 "camera_motion": "pan_right", "fx": "sparkles", "search_terms": ["ocean bridge sunrise"]},
                {"text": lang_meta["cta"],
                 "image_prompt": "epic wide shot of glowing golden bridge over ocean at dawn, 9:16",
                 "camera_motion": "zoom_out", "fx": "cinematic", "search_terms": ["golden sunrise landscape"]},
            ]})

    n_lo = max(6, total // 7)
    prompt = f"""You are a world-class AI Animation Director creating viral animated Instagram Reels & YouTube Shorts.
Narration Language: {lang_meta['name']} ({lang}) — Write "title", "description", "hashtags", and all narration "text" natively in {lang_meta['name']}.
Visual Prompts: Write all "image_prompt" and "search_terms" strictly in ENGLISH.
Genre Style: {STYLES.get(style_key, style_key)}
Art Style: {profile['art_style']}
Tone: {profile['tone']}
Guidelines: {profile['guidelines']}

{topic_line}
{_trend_hint(state)}

Return ONLY JSON:
{{
  "topic": "short topic name",
  "title": "high-CTR animated Reel title in {lang_meta['name']} under 60 chars",
  "description": "1-2 sentence engaging caption in {lang_meta['name']}",
  "hashtags": ["#AIAnimation", "#Reels", "#{lang}", "#Storytelling"],
  "art_style": "{profile['art_style']}",
  "characters": "one English sentence defining consistent animated character appearances",
  "scenes": [{{
    "text": "punchy spoken narration in {lang_meta['name']} (1-2 sentences)",
    "image_prompt": "detailed vertical 9:16 3D/anime visual frame description in ENGLISH, no text/letters",
    "motion_prompt": "dynamic character action, expressive movement, and smooth camera tracking in ENGLISH",
    "camera_motion": "zoom_in|zoom_out|pan_left|pan_right|pan_up|dolly_pulse",
    "fx": "cinematic|warm_glow|sparkles|eerie_vignette|vibrant",
    "search_terms": ["english fallback query"]
  }}]
}}
Rules:
- {n_lo} to {n_lo + 2} scenes totaling ~{total} seconds of narration.
- Arc: 1.5s scroll-stopping hook, escalating comedy/wonder/drama, emotional turning point, unforgettable climax, and CTA in {lang_meta['name']}.
- Keep image_prompt strictly free of any text, words, letters, logos, or watermarks."""

    data = llm_json(prompt, rounds=2, valid=lambda d: _valid_scenes(d, 5))
    if not data:
        if RaptarAgent:
            agent = RaptarAgent()
            pick = agent.evaluate_and_pick_topic({}, CATEGORIES, format_type="animated", lang=lang)
            data = agent.plan_script(pick, format_type="animated", lang=lang)
        else:
            sys.exit("Could not get an animated story script from Gemini or Groq.")

    script = _normalize(data)
    STORY.update(art_style=str(data.get("art_style") or profile["art_style"]),
                 characters=str(data.get("characters") or "expressive animated characters"))
    for sc in script["scenes"]:
        sc["image_prompt"] = str(sc.get("image_prompt") or sc["text"])
    script.update(category=category, style=style_key, language=lang,
                  target_audience=profile["target_audience"],
                  voice_profile=script.get("voice_profile", {"voice": profile["voice"], "rate": profile["rate"]}),
                  subtitle_color=profile.get("subtitle_color", "0x00E5FF"),
                  art_style=STORY["art_style"])
    return script


def generate_long(topic, history, state, lang: str = "en") -> dict:
    """Generates a full 5-7+ minute multi-chapter video with guaranteed word-count/duration pacing."""
    total = pick_seconds("LONG_SECONDS", "300-420")
    lang_meta = LANGUAGES.get(lang, LANGUAGES["en"])
    topic_line, category = _topic_line(topic, history, state, True)
    hint = state.get("_style_hint")
    profile = _get_profile(hint or category or "legend", lang=lang)
    style_key = profile.get("style", "legend")

    if OFFLINE:
        # Produce an offline 4-chapter / 12-scene test structure validating chapter transitions + concat
        offline_chapters = [
            ("Chapter 1: The Awakening", "ancient ruins", "16:9 widescreen 3D cinematic ancient temple sunrise", "zoom_in"),
            ("Chapter 2: The Ocean Bridge", "ocean waves", "16:9 widescreen animated ocean bridge dramatic waves", "pan_right"),
            ("Chapter 3: The Hidden Truth", "glowing crystals", "16:9 widescreen glowing crystal ruins twilight", "zoom_out"),
            ("Chapter 4: The Dawn Legacy", "golden sunrise", "16:9 widescreen golden horizon sunrise clouds", "dolly_pulse"),
        ]
        offline_scenes = []
        for ch_idx, (ch_title, ch_term, ch_img, ch_mot) in enumerate(offline_chapters):
            for part in range(3):
                offline_scenes.append({
                    "text": f"{ch_title} part {part + 1}: Across the horizon, small acts of courage reshaped history forever.",
                    "search_terms": [ch_term, "cinematic sky"],
                    "heading": ch_title if part == 0 else None,
                    "image_prompt": ch_img,
                    "camera_motion": ch_mot,
                })
        return _normalize({
            "topic": "offline long test", "title": "Offline Long-Form Story Test",
            "description": "Testing multi-chapter long-form video assembly.",
            "hashtags": ["#longform", "#animation", f"#{lang}"],
            "category": category or "Ancient Myths, Legends & Epic Lore",
            "style": style_key, "language": lang, "target_audience": profile["target_audience"],
            "voice_profile": {"voice": profile["voice"], "rate": profile["rate"]},
            "art_style": profile["art_style"].replace("9:16 vertical", "16:9 widescreen cinematic"),
            "_already_reviewed": True,
            "scenes": offline_scenes,
        })

    n = max(5, min(8, round(total / 55)))
    target_total_words = int(total * 2.45)  # ~147 words/min spoken pace
    per_section = max(125, target_total_words // n)
    widescreen_art = profile["art_style"].replace("9:16 vertical", "16:9 widescreen cinematic")

    outline_prompt = f"""You are the head writer and creative director of a viral storytelling & animated documentary YouTube channel.
{topic_line}
Output Language: {lang_meta['name']} ({lang}) — Write "title", "description", "hashtags", and chapter headings natively in {lang_meta['name']}.
Genre Style: {STYLES.get(style_key, style_key)}
Tone: {profile['tone']}

Plan a full {total // 60}-minute multi-chapter video (~{target_total_words} spoken words total). Return ONLY JSON:
{{
  "topic": "short English/tracking name of the topic",
  "title": "compelling title under 70 chars in {lang_meta['name']}",
  "description": "2-3 sentence summary in {lang_meta['name']}",
  "hashtags": ["#story", "#animation", "#{lang}", "#youtube"],
  "characters": "one English sentence defining consistent visual character/world style",
  "sections": [{{"heading": "chapter title max 5 words in {lang_meta['name']}", "summary": "what this chapter covers in 1-2 sentences"}}]
}}
Rules:
- Exactly {n} sections.
- Section 1 is an irresistible cold-open hook. Middle sections escalate mystery/wonder/stakes cleanly.
- Final section delivers a powerful climax and short invitation to subscribe in {lang_meta['name']}."""

    valid_outline = lambda d: (
        isinstance(d, dict) and isinstance(d.get("sections"), list) and len(d["sections"]) >= 4
        and all(isinstance(s, dict) and isinstance(s.get("heading"), str) for s in d["sections"])
    )
    outline = llm_json(outline_prompt, rounds=2, valid=valid_outline)
    if not outline:
        sys.exit("Could not plan the long video (Gemini and Groq both failed).")

    sections = outline["sections"][:n]
    title = str(outline.get("title") or outline.get("topic") or "Untitled")
    characters = str(outline.get("characters") or "expressive cinematic characters")
    STORY.update(art_style=widescreen_art, characters=characters)
    plan = "\n".join(f"{i + 1}. {s['heading']}: {s.get('summary', '')}" for i, s in enumerate(sections))

    scenes, prev, ok, total_words = [], "Opening of the story.", 0, 0
    scenes_per_chap = max(4, per_section // 28)

    for i, sec in enumerate(sections):
        print(f"  Writing chapter {i + 1}/{len(sections)}: {sec['heading']}")
        prompt = f"""Write the full spoken narration for chapter {i + 1} of {len(sections)}, "{sec['heading']}",
of a {total // 60}-minute {lang_meta['name']} ({style_key}) video titled "{title}".
Full plan:
{plan}

Previous chapter ended with: "{prev}"
Write AT LEAST {per_section} words of rich, engaging narration for THIS chapter ONLY in {lang_meta['name']}.
Return ONLY JSON:
{{"scenes": [{{
  "text": "spoken narration in {lang_meta['name']} (2-3 vivid sentences, ~30-45 words each)",
  "search_terms": ["english visual query 1", "english visual query 2"],
  "image_prompt": "detailed 16:9 widescreen cinematic/animated scene in ENGLISH, no text/letters",
  "motion_prompt": "dynamic character action and smooth 24fps cinematic motion in ENGLISH",
  "camera_motion": "zoom_in|zoom_out|pan_left|pan_right|pan_up|dolly_pulse"
}}]}}
Rules:
- Exactly {scenes_per_chap} to {scenes_per_chap + 2} scenes totaling AT LEAST {per_section} words.
- Keep narration vivid, flowing seamlessly from the previous chapter without repeating earlier info.
- {"End with a cliffhanger pulling viewers into the next chapter." if i < len(sections) - 1 else f"End with a powerful resolution and subscribe invitation in {lang_meta['name']}."}
- Write ALL "search_terms" and "image_prompt" in ENGLISH."""

        data = llm_json(prompt, rounds=2, valid=lambda d: _valid_scenes(d, minimum=2))
        if not data:
            print(f"  WARNING: chapter '{sec['heading']}' failed LLM — generating structured continuation.")
            data = {
                "scenes": [
                    {
                        "text": f"{sec['heading']}. {sec.get('summary', 'The story deepens as new revelations unfold.')}",
                        "search_terms": ["cinematic landscape", "dramatic clouds"],
                        "image_prompt": f"{widescreen_art}, {characters}, atmospheric visual for {sec['heading']}",
                        "camera_motion": "zoom_in",
                    },
                    {
                        "text": "Every detail connected to a larger mystery waiting just beyond the horizon.",
                        "search_terms": ["mystic sunset", "starry horizon"],
                        "image_prompt": f"{widescreen_art}, sweeping scenic transition at twilight",
                        "camera_motion": "pan_right",
                    },
                ]
            }

        chap_scenes = data["scenes"]
        chap_words = sum(len(sc["text"].split()) for sc in chap_scenes)

        # Automatic duration-protection pass: if a chapter came back too brief, expand it!
        if chap_words < int(per_section * 0.72) and GEMINI_API_KEY:
            expand_prompt = f"""The chapter "{sec['heading']}" only had {chap_words} words, which is too short for a {total // 60}-minute video.
Expand this narrative in {lang_meta['name']} by adding 2-3 rich, detailed continuation scenes (~{per_section - chap_words + 40} extra words) continuing smoothly from:
"{chap_scenes[-1]['text']}"
Return ONLY JSON: {{"scenes": [{{"text": "...", "search_terms": ["..."], "image_prompt": "...", "camera_motion": "zoom_out"}}]}}"""
            extra = llm_json(expand_prompt, rounds=1, valid=lambda d: _valid_scenes(d, minimum=2))
            if extra:
                chap_scenes = chap_scenes + extra["scenes"]
                chap_words = sum(len(sc["text"].split()) for sc in chap_scenes)

        for j, sc in enumerate(chap_scenes):
            txt = sc["text"].strip()
            scenes.append({
                "text": txt,
                "search_terms": sc.get("search_terms"),
                "image_prompt": sc.get("image_prompt") or txt,
                "camera_motion": sc.get("camera_motion"),
                "heading": sec["heading"].strip() if j == 0 else None,
            })
        total_words += chap_words
        prev = chap_scenes[-1]["text"].strip()
        ok += 1

    # Final safety expansion pass if total cumulative script words are still below 80% of target_total_words
    if total_words < int(target_total_words * 0.80):
        needed = target_total_words - total_words
        print(f"  Duration safeguard: expanding epilogue by ~{needed} words to meet {total}s target...")
        epilogue_prompt = f"""Write an extended epilogue & deep reflection chapter in {lang_meta['name']} for "{title}" continuing from "{prev}".
Write AT LEAST {max(120, needed)} words across 4 scenes so the full video reaches {total // 60} minutes cleanly.
Return ONLY JSON: {{"scenes": [{{"text": "...", "search_terms": ["sunset horizon", "starry night"], "image_prompt": "16:9 cinematic sunrise landscape", "camera_motion": "zoom_out"}}]}}"""
        extra_ep = llm_json(epilogue_prompt, rounds=1, valid=lambda d: _valid_scenes(d, minimum=2))
        if extra_ep:
            for j, sc in enumerate(extra_ep["scenes"]):
                scenes.append({
                    "text": sc["text"].strip(),
                    "search_terms": sc.get("search_terms"),
                    "image_prompt": sc.get("image_prompt") or sc["text"],
                    "camera_motion": sc.get("camera_motion"),
                    "heading": "Final Reflections" if j == 0 else None,
                })
            total_words += sum(len(sc["text"].split()) for sc in extra_ep["scenes"])

    print(f"  Long-form script ready: {len(scenes)} scenes, ~{total_words} words (target ~{target_total_words}).")
    script = {
        "topic": outline.get("topic") or title,
        "title": title,
        "description": outline.get("description", ""),
        "hashtags": outline.get("hashtags", []),
        "scenes": scenes,
        "category": category,
        "style": style_key,
        "language": lang,
        "target_audience": profile["target_audience"],
        "voice_profile": {"voice": profile["voice"], "rate": profile["rate"]},
        "subtitle_color": profile["subtitle_color"],
        "art_style": widescreen_art,
        "_already_reviewed": True,
    }
    return _normalize(script)


# ------------------------------------------------------------ helpers: weighting + trend hints
def weighted_choice(options: list, weights: dict):
    return random.choices(options, weights=[max(0.1, float(weights.get(o, 1.0))) for o in options])[0]


def _trend_share(state: dict) -> float:
    if os.environ.get("TREND_SHARE"):
        return float(os.environ["TREND_SHARE"])
    w = state.get("weights", {}).get("source", {})
    if "trend" in w and "category" in w:
        return min(0.85, max(0.3, w["trend"] / (w["trend"] + w["category"])))
    return 0.7


def _trend_hint(state: dict) -> str:
    t = state.get("trends") or {}
    bits = []
    if t.get("format_trends"):
        bits.append("formats that currently work: " + "; ".join(t["format_trends"]))
    if t.get("title_patterns"):
        bits.append("title patterns: " + "; ".join(t["title_patterns"]))
    return ("Hints from today's trend research: " + " | ".join(bits)) if bits else ""


# ------------------------------------------------------------ 2. multilingual neural voice
async def _tts(text: str, path: Path, voice: str = None, rate: str = None) -> None:
    import edge_tts
    v = voice or TTS_VOICE
    r = rate or "+2%"
    await edge_tts.Communicate(text, v, rate=r).save(str(path))


def make_voice(text: str, path: Path, voice_profile: dict = None) -> float:
    if OFFLINE:
        secs = max(1.5, 0.35 * len(text.split()))
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
             "-t", f"{secs:.2f}", "-c:a", "libmp3lame", str(path)])
        return media_duration(path)
    voice = (voice_profile or {}).get("voice") if isinstance(voice_profile, dict) else None
    rate = (voice_profile or {}).get("rate") if isinstance(voice_profile, dict) else None
    for attempt in range(3):
        try:
            asyncio.run(_tts(text, path, voice=voice, rate=rate))
            if path.exists() and path.stat().st_size > 200:
                return media_duration(path)
        except Exception as e:
            print(f"TTS attempt {attempt + 1} failed ({voice}): {e}")
            # Fallback to default English voice if localized voice transient failure occurs
            if attempt == 1 and voice and voice != TTS_VOICE:
                print(f"  Falling back to {TTS_VOICE} after retry...")
                voice = TTS_VOICE
            time.sleep(2)
    sys.exit("Voice generation failed (edge-tts).")


# ------------------------------------------------------------ 3. stock footage + caching
_PIXABAY_CACHE: dict[str, list] = {}


def _download(link: str, dest: Path) -> bool:
    try:
        with requests.get(link, stream=True, timeout=180) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in resp.iter_content(1 << 20):
                    fh.write(chunk)
        return _valid_video(dest)
    except Exception as e:
        print(f"  Download failed ({type(e).__name__})")
        dest.unlink(missing_ok=True)
        return False


def _pixabay(query: str, dest: Path, used: set) -> bool:
    if not PIXABAY_API_KEY:
        return False
    hits = _PIXABAY_CACHE.get(query)
    if hits is None:
        for attempt in range(2):
            r = requests.get("https://pixabay.com/api/videos/",
                             params={"key": PIXABAY_API_KEY, "q": query, "per_page": 20, "safesearch": "true"},
                             timeout=30)
            if r.status_code == 429 and attempt == 0:
                time.sleep(5)
                continue
            r.raise_for_status()
            hits = r.json().get("hits", [])
            _PIXABAY_CACHE[query] = hits
            break
    avail = [h for h in (hits or []) if h["id"] not in used]
    if not avail:
        return False
    for hit in random.sample(avail[:10], min(3, len(avail[:10]))):
        for size in SIZE_ORDER:
            v = hit["videos"].get(size) or {}
            if v.get("url"):
                used.add(hit["id"])
                if _download(v["url"], dest):
                    return True
    return False


def _pexels(query: str, dest: Path, used: set) -> bool:
    if not PEXELS_API_KEY:
        return False
    r = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": PEXELS_API_KEY},
                     params={"query": query, "orientation": ORIENT, "per_page": 15}, timeout=30)
    r.raise_for_status()
    vids = [v for v in r.json().get("videos", []) if v["id"] not in used]
    if not vids:
        return False
    video = random.choice(vids[:8])
    files = [f for f in video["video_files"] if f.get("file_type") == "video/mp4"]
    files.sort(key=lambda f: abs((f.get("height") or 0) - H))
    used.add(video["id"])
    return bool(files and _download(files[0]["link"], dest))


def _gradient(dest: Path, seconds: float, style: str = "") -> None:
    if style == "horror":
        c0 = "0x%06x" % random.randint(0x05050a, 0x14050a)
        c1 = "0x%06x" % random.randint(0x150505, 0x2e0808)
    elif style in ("fable", "animated_comedy"):
        c0 = "0x%06x" % random.randint(0x205090, 0x4070b0)
        c1 = "0x%06x" % random.randint(0x904070, 0xb06090)
    elif style in ("legend", "animated_myth"):
        c0 = "0x%06x" % random.randint(0x302010, 0x503515)
        c1 = "0x%06x" % random.randint(0x503010, 0x754520)
    else:
        c0 = "0x%06x" % random.randint(0x0a1020, 0x182434)
        c1 = "0x%06x" % random.randint(0x1a1525, 0x2e1e30)
    run(["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"gradients=s={W}x{H}:c0={c0}:c1={c1}:duration={seconds:.1f}:speed=0.04:rate={FPS}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), str(dest)])


def fetch_clip(query: str, dest: Path, used: set, seconds: float, style: str = "") -> None:
    if not OFFLINE:
        fallbacks = ("creepy shadows", "foggy night") if style == "horror" else (
            ("colorful cartoon clouds", "starry night sky") if style in ("fable", "animated_comedy", "animated_myth")
            else ("cinematic night city", "golden sunset nature")
        )
        for q in (query, " ".join(query.split()[:2]), *fallbacks):
            for provider in (_pexels, _pixabay):
                try:
                    if provider(q, dest, used):
                        return
                except Exception as e:
                    print(f"  {provider.__name__} failed for '{q}': {e}")
    print(f"  using gradient background for '{query}'")
    _gradient(dest, seconds + 1, style=style)


# ------------------------------------------------------------ 4. assembly (stock + AI animation)
def make_visual(idx: int, terms: list[str], total: float, used: set, style: str = "") -> Path:
    """Picture track of one scene, normalized to constant FPS & timebase for seamless concat."""
    n = max(1, min(5, round(total / CLIP_LEN)))
    seg_len = total / n
    segs = []
    for k in range(n):
        raw = WORK / f"raw_{idx}_{k}.mp4"
        fetch_clip(terms[k % len(terms)], raw, used, seg_len + 0.5, style=style)
        seg = WORK / f"seg_{idx}_{k}.mp4"
        try:
            run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(raw), "-t", f"{seg_len:.3f}",
                 "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}",
                 "-an", "-r", str(FPS), "-vsync", "cfr", "-video_track_timescale", "90000",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(seg)])
        except SystemExit:
            # Self-healing fallback if a stock file had unexpected decoding quirks
            _gradient(raw, seg_len + 1, style=style)
            run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(raw), "-t", f"{seg_len:.3f}",
                 "-vf", f"scale={W}:{H}:setsar=1,fps={FPS}",
                 "-an", "-r", str(FPS), "-vsync", "cfr", "-video_track_timescale", "90000",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(seg)])
        segs.append(seg)
        raw.unlink(missing_ok=True)
    if n == 1:
        return segs[0]
    lst = WORK / f"segs_{idx}.txt"
    lst.write_text("".join(f"file '{s.name}'\n" for s in segs), encoding="utf-8")
    out = WORK / f"visual_{idx}.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
    for s in segs:
        s.unlink(missing_ok=True)
    return out


# ------------------------------------------------------------ AI Animation & Vector SVG Engine
STORY: dict = {"art_style": "", "characters": ""}
_IMG_DEAD: set = set()
_IMG_MODELS: list = []


def _valid_image(path: Path) -> bool:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True, timeout=30)
        w, h = (int(x) for x in r.stdout.strip().split(",")[:2])
        return w >= 256 and h >= 256
    except Exception:
        return False


def _gemini_image(prompt: str, dest: Path) -> bool:
    """Attempts image generation using free/available Gemini image models discovered on the user's key."""
    if not GEMINI_API_KEY or "gemini" in _IMG_DEAD:
        return False
    headers = {"x-goog-api-key": GEMINI_API_KEY, "User-Agent": "aistudio-build"}
    if not _IMG_MODELS:
        try:
            r = requests.get(f"{GEMINI_BASE}/models", params={"pageSize": 200}, headers=headers, timeout=30)
            if r.ok:
                # Filter out paid-only/Pro/Nano-Banana models so free keys work smoothly without 403s
                paid_only = ("imagen", "nano-banana", "pro-image", "3.1-flash-lite-image")
                _IMG_MODELS.extend(sorted(
                    (m["name"].split("/")[-1] for m in r.json().get("models", [])
                     if "image" in m["name"] and not any(p in m["name"] for p in paid_only)
                     and "generateContent" in m.get("supportedGenerationMethods", [])),
                    reverse=True,
                )[:2])
        except requests.RequestException:
            pass
    if not _IMG_MODELS:
        return False
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    for model in _IMG_MODELS:
        for attempt in range(2):
            try:
                r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent", json=body,
                                  headers=headers, timeout=120)
            except requests.RequestException:
                break
            if r.ok:
                for part in r.json().get("candidates", [{}])[0].get("content", {}).get("parts", []):
                    inline = part.get("inlineData") or part.get("inline_data")
                    if inline and inline.get("data"):
                        dest.write_bytes(base64.b64decode(inline["data"]))
                        return True
                break
            if r.status_code == 429 and attempt == 0:
                time.sleep(10)
                continue
            print(f"  image model {model}: HTTP {r.status_code}")
            if r.status_code in (403, 429):
                _IMG_DEAD.add("gemini")
                return False
            break
    return False


def _pollinations(prompt: str, dest: Path) -> bool:
    """Free AI keyframe generation via Pollinations Flux/Turbo adapted to portrait (9:16) or landscape (16:9)."""
    if "pollinations" in _IMG_DEAD:
        return False
    from urllib.parse import quote
    base = os.environ.get("POLLINATIONS_BASE", "https://image.pollinations.ai/prompt/")
    pw, ph = (1344, 768) if W > H else (768, 1344)
    for model_name in ("flux", "turbo"):
        try:
            r = requests.get(
                base + quote(prompt[:800]),
                timeout=120,
                params={"width": pw, "height": ph, "model": model_name, "nologo": "true",
                        "seed": random.randint(1, 999999)},
            )
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                dest.write_bytes(r.content)
                return True
            print(f"  pollinations ({model_name}): HTTP {r.status_code}")
            if r.status_code in (401, 402, 403):
                _IMG_DEAD.add("pollinations")
                return False
        except requests.RequestException as e:
            print(f"  pollinations ({model_name}): {type(e).__name__}")
    return False


def _procedural_svg(style: str, idx: int) -> str:
    """Rich layered vector artwork fallback rendered cleanly via FFmpeg librsvg."""
    palettes = {
        "animated_myth": ("#1b1035", "#ff7b39", "#ffd166", "#2a1f4d"),
        "animated_comedy": ("#1167b1", "#ff9f1c", "#ffffff", "#2ec4b6"),
        "animated_anime": ("#0b132b", "#ff4d6d", "#ffb3c6", "#1c2541"),
        "horror": ("#05050a", "#3a0ca3", "#e63946", "#0b0b12"),
        "fable": ("#2b2d42", "#4cc9f0", "#ffd166", "#3a0ca3"),
    }
    bg1, bg2, acc, hill = palettes.get(style, ("#0f172a", "#38bdf8", "#fbbf24", "#1e293b"))
    cx = int(W * (0.35 + (idx % 3) * 0.15))
    cy = int(H * 0.34)
    r_orb = int(min(W, H) * 0.18)
    stars = "".join(
        f'<circle cx="{(k * 173 + idx * 91) % W}" cy="{(k * 97 + idx * 53) % int(H * 0.55)}" '
        f'r="{2 + (k % 4)}" fill="#ffffff" opacity="{0.35 + (k % 5) * 0.12:.2f}"/>'
        for k in range(28)
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{bg1}"/>
      <stop offset="65%" stop-color="{bg2}"/>
      <stop offset="100%" stop-color="{hill}"/>
    </linearGradient>
    <radialGradient id="orb" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.95"/>
      <stop offset="45%" stop-color="{acc}" stop-opacity="0.85"/>
      <stop offset="100%" stop-color="{acc}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="{W}" height="{H}" fill="url(#sky)"/>
  {stars}
  <circle cx="{cx}" cy="{cy}" r="{int(r_orb * 1.9)}" fill="url(#orb)"/>
  <circle cx="{cx}" cy="{cy}" r="{r_orb}" fill="{acc}" opacity="0.92"/>
  <path d="M0 {int(H*0.72)} Q {int(W*0.3)} {int(H*0.62)} {int(W*0.62)} {int(H*0.70)} T {W} {int(H*0.66)} L {W} {H} L 0 {H} Z" fill="{hill}" opacity="0.85"/>
  <path d="M0 {int(H*0.80)} Q {int(W*0.45)} {int(H*0.74)} {W} {int(H*0.82)} L {W} {H} L 0 {H} Z" fill="{bg1}" opacity="0.95"/>
</svg>'''


def _gemini_svg_illustration(prompt: str, dest: Path, style: str = "", idx: int = 0) -> bool:
    """Uses Gemini 4 Hydrogen to synthesize rich multi-layered SVG vector artwork, rendered to PNG via FFmpeg."""
    svg_text = ""
    if GEMINI_API_KEY and not OFFLINE and "svg" not in _DEAD_GEMINI:
        svg_prompt = f"""Generate a vivid, layered, expressive SVG scene illustration (no text elements!) matching:
Scene: {prompt[:400]}
Dimensions: width="{W}" height="{H}" viewBox="0 0 {W} {H}"
Style: {style or '3D stylized vector art'}
Include rich linearGradient/radialGradient backgrounds, glowing celestial or lighting elements, layered foreground scenery, and stylized character/object silhouettes using <path>, <circle>, <ellipse>, <polygon>. Never use <text> or external URLs.
Return ONLY raw valid <svg ...>...</svg> markup."""
        try:
            r = requests.post(
                f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
                json={"contents": [{"parts": [{"text": svg_prompt}]}]},
                headers={"x-goog-api-key": GEMINI_API_KEY, "User-Agent": "aistudio-build"},
                timeout=45,
            )
            if r.ok:
                raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                m = re.search(r"<svg[\s\S]*?</svg>", raw)
                if m and "<text" not in m.group(0).lower():
                    svg_text = m.group(0)
            elif r.status_code == 429:
                _DEAD_GEMINI.add("svg")
        except Exception:
            pass

    if not svg_text:
        svg_text = _procedural_svg(style, idx)

    svg_path = dest.with_suffix(".svg")
    try:
        svg_path.write_text(svg_text, encoding="utf-8")
        res = subprocess.run(["ffmpeg", "-y", "-i", str(svg_path), "-frames:v", "1", str(dest)],
                             capture_output=True, text=True, timeout=30)
        svg_path.unlink(missing_ok=True)
        if res.returncode == 0 and _valid_image(dest):
            return True
    except Exception:
        pass

    # Guaranteed fallback if Gemini's SVG had an invalid attribute
    try:
        svg_path.write_text(_procedural_svg(style, idx), encoding="utf-8")
        run(["ffmpeg", "-y", "-i", str(svg_path), "-frames:v", "1", str(dest)])
        svg_path.unlink(missing_ok=True)
        return _valid_image(dest)
    except Exception:
        return False


def gen_image(prompt: str, dest: Path, style: str = "", idx: int = 0) -> bool:
    if OFFLINE:
        return _gemini_svg_illustration(prompt, dest, style=style, idx=idx)
    if (_gemini_image(prompt, dest) and _valid_image(dest)):
        return True
    if (_pollinations(prompt, dest) and _valid_image(dest)):
        return True
    return _gemini_svg_illustration(prompt, dest, style=style, idx=idx)


_VIDEO_DEAD: set = set()
_AI_VIDEO_COUNT: int = 0


def _hf_headers() -> dict:
    h = {"User-Agent": "Mozilla/5.0"}
    if HF_TOKEN:
        h["Authorization"] = f"Bearer {HF_TOKEN}"
    return h


def _extract_gradio_media_url(payload, host: str) -> str | None:
    """Recursively extracts the downloadable MP4 URL or file path from a Gradio SSE completion payload."""
    if isinstance(payload, str):
        if payload.startswith("http"):
            return payload
        if ".mp4" in payload or "/tmp/gradio" in payload:
            return f"{host}/gradio_api/file={payload}"
        return None
    if isinstance(payload, dict):
        vid = payload.get("video")
        if isinstance(vid, dict):
            url = vid.get("url") or vid.get("path")
            if isinstance(url, str) and url:
                return url if url.startswith("http") else f"{host}/gradio_api/file={url}"
        url = payload.get("url")
        if isinstance(url, str) and url:
            return url if url.startswith("http") else f"{host}/gradio_api/file={url}"
        path = payload.get("path")
        if isinstance(path, str) and (".mp4" in path or "/tmp/gradio" in path):
            return path if path.startswith("http") else f"{host}/gradio_api/file={path}"
        for v in payload.values():
            found = _extract_gradio_media_url(v, host)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _extract_gradio_media_url(item, host)
            if found:
                return found
    return None


def _hf_gradio_upload(host: str, file_path: Path, timeout: int = 45) -> str | None:
    """Uploads an image frame to a Gradio Space and returns its server file path."""
    try:
        mime = "image/png" if file_path.suffix.lower() == ".png" else "image/jpeg"
        with open(file_path, "rb") as fh:
            r = requests.post(
                f"{host}/gradio_api/upload",
                headers=_hf_headers(),
                files={"files": (file_path.name, fh, mime)},
                timeout=timeout,
            )
        if r.ok:
            res = r.json()
            if isinstance(res, list) and res and isinstance(res[0], str):
                return res[0]
    except Exception as e:
        print(f"  ZeroGPU upload ({host}): {type(e).__name__}")
    return None


def _hf_gradio_call(
    host: str,
    endpoint: str,
    data: list,
    dest: Path,
    provider_key: str,
    timeout: int = 180,
) -> bool:
    """Invokes a Hugging Face ZeroGPU Gradio REST+SSE endpoint ($0 cost) and downloads the MP4 clip."""
    if provider_key in _VIDEO_DEAD:
        return False
    ep = endpoint.lstrip("/")
    headers = _hf_headers()
    try:
        r = requests.post(
            f"{host}/gradio_api/call/{ep}",
            json={"data": data},
            headers={**headers, "Content-Type": "application/json"},
            timeout=30,
        )
        if not r.ok:
            print(f"  {provider_key}: submit HTTP {r.status_code}")
            if r.status_code in (401, 402, 403, 404, 429):
                _VIDEO_DEAD.add(provider_key)
            return False
        event_id = r.json().get("event_id")
        if not event_id:
            return False

        sse_url = f"{host}/gradio_api/call/{ep}/{event_id}"
        with requests.get(sse_url, headers=headers, stream=True, timeout=timeout) as resp:
            if not resp.ok:
                if resp.status_code in (401, 402, 429):
                    _VIDEO_DEAD.add(provider_key)
                return False
            ev = None
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = raw_line.strip()
                if line.startswith("event:"):
                    ev = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    raw_data = line[5:].strip()
                    if ev == "complete":
                        try:
                            payload = json.loads(raw_data)
                        except Exception:
                            payload = raw_data
                        media_url = _extract_gradio_media_url(payload, host)
                        if not media_url:
                            return False
                        dl = requests.get(media_url, headers=headers, stream=True, timeout=120)
                        if dl.ok:
                            with open(dest, "wb") as out_fh:
                                for chunk in dl.iter_content(1 << 16):
                                    out_fh.write(chunk)
                            if _valid_video(dest):
                                return True
                        dest.unlink(missing_ok=True)
                        return False
                    elif ev == "error":
                        low = raw_data.lower()
                        print(f"  {provider_key}: ZeroGPU error ({raw_data[:120]})")
                        if any(k in low for k in ("quota", "limit", "exceeded", "token", "unauthorized", "null")):
                            _VIDEO_DEAD.add(provider_key)
                        return False
    except Exception as e:
        print(f"  {provider_key}: {type(e).__name__}: {e}")
    dest.unlink(missing_ok=True)
    return False


def _build_motion_prompt(sc: dict, style: str = "") -> str:
    """Combines scene art style, character continuity, and motion cues for real AI video synthesis."""
    base = (sc.get("motion_prompt") or sc.get("image_prompt") or sc.get("text") or "").strip()
    art = STORY.get("art_style") or "3D Pixar cinematic animation"
    chars = STORY.get("characters") or ""
    prompt = (
        f"{art}. {chars}. {base}. "
        f"Fluid 24fps character movement, blinking expressive eyes, natural cloth and atmospheric motion, "
        f"smooth cinematic camera tracking, zero text, zero watermark."
    )
    return re.sub(r"\s+", " ", prompt).strip()[:650]


def _wan22_i2v(img_path: Path, motion_prompt: str, dest: Path) -> bool:
    """Free Wan 2.2 14B 4-step Lightning Image-to-Video via Hugging Face ZeroGPU."""
    host = "https://saravutw-wan2-2-i2v-lightning-4-8step-custom.hf.space"
    if "wan2.2-i2v" in _VIDEO_DEAD:
        return False
    up = _hf_gradio_upload(host, img_path)
    if not up:
        return False
    fobj = {"path": up, "meta": {"_type": "gradio.FileData"}}
    neg = "blurry, static, frozen frame, low quality, deformed anatomy, jittery camera, text, watermark, logo"
    data = [fobj, None, motion_prompt, 4, neg, 3.5, 1, 1, random.randint(1, 999999), True, 5, "UniPCMultistep", 3.0, 16, False, True]
    return _hf_gradio_call(host, "generate_video", data, dest, "wan2.2-i2v", timeout=180)


def _ltx_i2v(img_path: Path, motion_prompt: str, dest: Path) -> bool:
    """Free Lightricks LTX-Video Distilled Image-to-Video via Hugging Face ZeroGPU."""
    host = "https://lightricks-ltx-video-distilled.hf.space"
    if "ltx-i2v" in _VIDEO_DEAD:
        return False
    up = _hf_gradio_upload(host, img_path)
    if not up:
        return False
    fobj = {"path": up, "meta": {"_type": "gradio.FileData"}}
    vh, vw = (768, 512) if H > W else (512, 768)
    neg = "worst quality, inconsistent motion, blurry, jittery, distorted, static, text, watermark"
    data = [motion_prompt, neg, fobj, None, vh, vw, "image-to-video", 3.0, 9, random.randint(1, 999999), True, 1, True]
    return _hf_gradio_call(host, "image_to_video", data, dest, "ltx-i2v", timeout=180)


def _ltx_t2v(motion_prompt: str, dest: Path) -> bool:
    """Free Lightricks LTX-Video Distilled Text-to-Video via Hugging Face ZeroGPU."""
    host = "https://lightricks-ltx-video-distilled.hf.space"
    if "ltx-t2v" in _VIDEO_DEAD:
        return False
    vh, vw = (768, 512) if H > W else (512, 768)
    neg = "worst quality, inconsistent motion, blurry, jittery, distorted, static, text, watermark"
    data = [motion_prompt, neg, None, None, vh, vw, "text-to-video", 3.0, 9, random.randint(1, 999999), True, 1, True]
    return _hf_gradio_call(host, "text_to_video", data, dest, "ltx-t2v", timeout=180)


def _ltx23_video(img_path: Path | None, motion_prompt: str, dest: Path) -> bool:
    """Free Lightricks LTX-2.3 Image-to-Video / Text-to-Video via Hugging Face ZeroGPU (recommended with HF_TOKEN)."""
    host = "https://lightricks-ltx-2-3.hf.space"
    if "ltx-2.3" in _VIDEO_DEAD:
        return False
    fobj = None
    if img_path and img_path.exists():
        up = _hf_gradio_upload(host, img_path)
        if up:
            fobj = {"path": up, "meta": {"_type": "gradio.FileData"}}
    vh, vw = (1024, 576) if H > W else (576, 1024)
    data = [fobj, motion_prompt, 3.0, False, random.randint(1, 999999), True, vh, vw]
    return _hf_gradio_call(host, "generate_video", data, dest, "ltx-2.3", timeout=210)


def _wan21_fast_i2v(img_path: Path, motion_prompt: str, dest: Path) -> bool:
    """Free Wan 2.1 14B 4-step Fast Image-to-Video via Hugging Face ZeroGPU (recommended with HF_TOKEN)."""
    host = "https://multimodalart-wan2-1-fast.hf.space"
    if "wan2.1-fast" in _VIDEO_DEAD:
        return False
    up = _hf_gradio_upload(host, img_path)
    if not up:
        return False
    fobj = {"path": up, "meta": {"_type": "gradio.FileData"}}
    vh, vw = (768, 512) if H > W else (512, 768)
    neg = "static, blurred details, overexposed, worst quality, deformed, text, watermark"
    data = [fobj, motion_prompt, vh, vw, neg, 3, 1.0, 4, random.randint(1, 999999), True]
    return _hf_gradio_call(host, "generate_video", data, dest, "wan2.1-fast", timeout=210)


def _comfyui_video(img_path: Path | None, motion_prompt: str, dest: Path) -> bool:
    """Optional self-hosted local GPU ComfyUI endpoint (100% free unlimited local Wan 2.2 / LTX-2 runner)."""
    if not LOCAL_COMFY_URL or "comfyui" in _VIDEO_DEAD:
        return False
    try:
        r = requests.get(f"{LOCAL_COMFY_URL}/system_stats", timeout=5)
        if not r.ok:
            _VIDEO_DEAD.add("comfyui")
            return False
    except Exception:
        _VIDEO_DEAD.add("comfyui")
        return False
    return False


def _i2v_free(img_path: Path, motion_prompt: str, dest: Path) -> str | None:
    """Tries tiered zero-cost Image-to-Video AI models with automatic quota failover."""
    providers = [
        ("Wan2.2-Lightning-I2V", lambda: _wan22_i2v(img_path, motion_prompt, dest)),
        ("LTX-Video-I2V", lambda: _ltx_i2v(img_path, motion_prompt, dest)),
    ]
    if HF_TOKEN:
        providers.insert(0, ("LTX-2.3-I2V", lambda: _ltx23_video(img_path, motion_prompt, dest)))
        providers.append(("Wan2.1-Fast-I2V", lambda: _wan21_fast_i2v(img_path, motion_prompt, dest)))
    if LOCAL_COMFY_URL:
        providers.insert(0, ("Local-ComfyUI", lambda: _comfyui_video(img_path, motion_prompt, dest)))

    for name, fn in providers:
        if fn():
            print(f"    [AI Video] Generated real temporal clip via {name}")
            return name
    return None


def _t2v_free(motion_prompt: str, dest: Path) -> str | None:
    """Tries tiered zero-cost Text-to-Video AI models with automatic quota failover."""
    providers = [
        ("LTX-Video-T2V", lambda: _ltx_t2v(motion_prompt, dest)),
    ]
    if HF_TOKEN:
        providers.insert(0, ("LTX-2.3-T2V", lambda: _ltx23_video(None, motion_prompt, dest)))
    for name, fn in providers:
        if fn():
            print(f"    [AI Video] Generated real temporal clip via {name}")
            return name
    return None


def _fx_filter_chain(fx: str) -> str:
    if fx == "eerie_vignette":
        return "eq=contrast=1.12:saturation=0.82,vignette=angle=PI/4"
    if fx in ("warm_glow", "sparkles", "golden_glow"):
        return "eq=contrast=1.06:saturation=1.22:brightness=0.02"
    if fx == "vibrant":
        return "eq=contrast=1.08:saturation=1.28"
    return "eq=contrast=1.05:saturation=1.12"


def _normalize_ai_video_clip(raw_clip: Path, out: Path, total: float, fx: str = "cinematic") -> None:
    """Upscale AI video clips smoothly and match scene duration via trim, gentle slow-mo, or seamless boomerang loop."""
    raw_dur = media_duration(raw_clip)
    base_vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=bicubic,"
        f"crop={W}:{H},{_fx_filter_chain(fx)},fps={FPS},setsar=1"
    )
    if raw_dur >= max(0.3, total - 0.05):
        run([
            "ffmpeg", "-y", "-i", str(raw_clip), "-t", f"{total:.3f}",
            "-vf", base_vf, "-an", "-r", str(FPS), "-vsync", "cfr", "-video_track_timescale", "90000",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", str(out),
        ])
        return

    if total <= raw_dur * 1.45:
        ratio = total / max(0.3, raw_dur)
        run([
            "ffmpeg", "-y", "-i", str(raw_clip), "-t", f"{total:.3f}",
            "-vf", f"{base_vf},setpts={ratio:.5f}*PTS",
            "-an", "-r", str(FPS), "-vsync", "cfr", "-video_track_timescale", "90000",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", str(out),
        ])
        return

    # Seamless forward+reverse boomerang cycle so longer scenes never suffer hard jump-cut loops
    boom = raw_clip.with_suffix(".boom.mp4")
    try:
        run([
            "ffmpeg", "-y", "-i", str(raw_clip),
            "-filter_complex", f"[0:v]{base_vf}[f];[f]split[f1][f2];[f2]reverse[rev];[f1][rev]concat=n=2:v=1:a=0[v]",
            "-map", "[v]", "-an", "-r", str(FPS), "-vsync", "cfr", "-video_track_timescale", "90000",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", str(boom),
        ])
        run([
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(boom), "-t", f"{total:.3f}",
            "-an", "-r", str(FPS), "-vsync", "cfr", "-video_track_timescale", "90000",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", str(out),
        ])
    finally:
        boom.unlink(missing_ok=True)


def _animate_frame_to_video(img: Path, out: Path, total: float, motion: str = "zoom_in", fx: str = "cinematic") -> None:
    """Transforms a keyframe into smooth 30fps animated motion with camera choreography and atmospheric FX."""
    frames = max(2, int(total * FPS) + 2)
    zp_w, zp_h = (1280, 720) if W > H else (720, 1280)
    big_w, big_h = int(zp_w * 1.22), int(zp_h * 1.22)

    motion_map = {
        "zoom_in": (f"min(1.0+0.0008*on,1.20)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        "zoom_out": (f"max(1.20-0.0008*on,1.0)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        "pan_right": ("1.14", f"(iw-iw/zoom)*on/{frames}", "ih/2-(ih/zoom/2)"),
        "pan_left": ("1.14", f"(iw-iw/zoom)*(1-on/{frames})", "ih/2-(ih/zoom/2)"),
        "pan_up": ("1.14", "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*(1-on/{frames})"),
        "dolly_pulse": (f"1.08+0.05*sin(2*PI*on/{frames})", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        "dramatic_shake": ("1.15", f"iw/2-(iw/zoom/2)+6*sin(on*0.9)", f"ih/2-(ih/zoom/2)+4*cos(on*1.1)"),
    }
    z, x, y = motion_map.get(motion, motion_map["zoom_in"])

    vf = (
        f"scale={big_w}:{big_h}:force_original_aspect_ratio=increase,crop={big_w}:{big_h},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={zp_w}x{zp_h}:fps={FPS},"
        f"scale={W}:{H}:flags=bicubic,{_fx_filter_chain(fx)},setsar=1"
    )
    run([
        "ffmpeg", "-y", "-i", str(img), "-vf", vf,
        "-t", f"{total:.3f}", "-an", "-r", str(FPS), "-vsync", "cfr", "-video_track_timescale", "90000",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(out),
    ])


def make_animated_visual(idx: int, sc: dict, total: float, style: str = "") -> Path | None:
    """Real AI video generator (Wan 2.2 Lightning I2V, LTX-Video I2V/T2V) with multi-shot Ken Burns & SVG fallback."""
    global _AI_VIDEO_COUNT
    base_prompt = sc.get("image_prompt") or sc.get("text", "")
    full_prompt = (
        f"{STORY['art_style']}. {STORY['characters']}. Scene: {base_prompt}. "
        f"{'Widescreen 16:9 composition' if W > H else 'Vertical 9:16 composition'}, no text, no letters, no watermark."
    )
    motion = sc.get("camera_motion") or ("zoom_in", "zoom_out", "pan_right", "pan_left", "pan_up")[idx % 5]
    fx = sc.get("fx") or ("eerie_vignette" if style == "horror" else ("warm_glow" if "myth" in style else "vibrant"))
    out = WORK / f"story_{idx}.mp4"

    # 1. Live Real AI Video Generation (Image-to-Video for character consistency -> Text-to-Video backup)
    pre_keyframe: Path | None = None
    if not OFFLINE and FREE_VIDEO_PROVIDER != "kenburns" and _AI_VIDEO_COUNT < VIDEO_AI_CLIPS_MAX:
        motion_prompt = _build_motion_prompt(sc, style=style)
        raw_ai = WORK / f"ai_raw_{idx}.mp4"
        if FREE_VIDEO_PROVIDER in ("auto", "i2v"):
            kf = WORK / f"kf_{idx}.png"
            if gen_image(full_prompt, kf, style=style, idx=idx):
                pre_keyframe = kf
                if _i2v_free(kf, motion_prompt, raw_ai):
                    _AI_VIDEO_COUNT += 1
                    _normalize_ai_video_clip(raw_ai, out, total, fx=fx)
                    raw_ai.unlink(missing_ok=True)
                    kf.unlink(missing_ok=True)
                    return out
        if FREE_VIDEO_PROVIDER in ("auto", "t2v"):
            if _t2v_free(motion_prompt, raw_ai):
                _AI_VIDEO_COUNT += 1
                _normalize_ai_video_clip(raw_ai, out, total, fx=fx)
                raw_ai.unlink(missing_ok=True)
                if pre_keyframe:
                    pre_keyframe.unlink(missing_ok=True)
                return out
        raw_ai.unlink(missing_ok=True)

    # 2. Multi-shot Ken Burns animation for scenes >= 6.5s (reusing pre_keyframe if already generated)
    if total >= 6.5 and not OFFLINE:
        half1 = total * 0.5
        half2 = total - half1
        img1 = pre_keyframe if (pre_keyframe and pre_keyframe.exists()) else WORK / f"img_{idx}_a.png"
        img2 = WORK / f"img_{idx}_b.png"
        shot1, shot2 = WORK / f"anim_{idx}_a.mp4", WORK / f"anim_{idx}_b.mp4"
        alt_motion = "dolly_pulse" if motion != "dolly_pulse" else "zoom_out"

        ok1 = img1.exists() and _valid_image(img1) or gen_image(full_prompt + ", establishing wide angle", img1, style=style, idx=idx * 2)
        ok2 = gen_image(full_prompt + ", expressive cinematic close-up reaction", img2, style=style, idx=idx * 2 + 1)
        if ok1 and ok2:
            _animate_frame_to_video(img1, shot1, half1, motion=motion, fx=fx)
            _animate_frame_to_video(img2, shot2, half2, motion=alt_motion, fx=fx)
            img1.unlink(missing_ok=True)
            img2.unlink(missing_ok=True)
            lst = WORK / f"anim_segs_{idx}.txt"
            lst.write_text(f"file '{shot1.name}'\nfile '{shot2.name}'\n", encoding="utf-8")
            run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
            shot1.unlink(missing_ok=True)
            shot2.unlink(missing_ok=True)
            return out

    # 3. Single-shot Keyframe / SVG 2.5D Ken Burns guaranteed fallback
    img = pre_keyframe if (pre_keyframe and pre_keyframe.exists()) else WORK / f"img_{idx}.png"
    if not (img.exists() and _valid_image(img)):
        if not gen_image(full_prompt, img, style=style, idx=idx):
            return None
    _animate_frame_to_video(img, out, total, motion=motion, fx=fx)
    img.unlink(missing_ok=True)
    return out


# Keep backwards-compatible alias for external scripts/tests
def make_story_visual(idx: int, sc: dict, total: float):
    return make_animated_visual(idx, sc, total)


# ------------------------------------------------------------ Subtitles (Multilingual ASS + Legacy Chunking)
def caption_chunks(text: str, duration: float):
    """Splits narration cleanly into timed caption chunks for both space-separated & CJK languages."""
    words = text.split()
    if len(words) <= 2 and len(text.strip()) > 16:
        # CJK / unspaced script chunking (~10 chars per chunk)
        raw = text.strip()
        groups = [raw[i:i + 10] for i in range(0, len(raw), 10)]
    else:
        groups = [" ".join(words[i:i + WORDS_PER_CAPTION]) for i in range(0, len(words), WORDS_PER_CAPTION)]
    total = sum(len(g) for g in groups) or 1
    t, out = 0.0, []
    for g in groups:
        span = duration * len(g) / total
        out.append((g, t, t + span))
        t += span
    return out


def _fmt_ass_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _color_to_ass_bgr(c: str) -> str:
    """Converts 0xBBGGRR or named FFmpeg hex colors into ASS &H00BBGGRR format."""
    c = (c or "white").strip().lower()
    named = {
        "white": "&H00FFFFFF",
        "yellow": "&H0000FFFF",
        "cyan": "&H00FFFF00",
    }
    if c in named:
        return named[c]
    if c.startswith("0x") and len(c) == 8:
        return "&H00" + c[2:].upper()
    return "&H0000E5FF"


def _write_ass_subtitles(idx: int, text: str, dur: float, font_path: str, style_meta: dict, heading: str = None, lang: str = "en") -> Path:
    """Creates a styled ASS subtitle file supporting complex scripts (Tamil, Hindi, Arabic, CJK, Latin)."""
    lang_meta = LANGUAGES.get(lang, LANGUAGES["en"])
    font_name = lang_meta.get("font_family") or Path(font_path).stem.split("-")[0]
    hl_bgr = _color_to_ass_bgr((style_meta or {}).get("subtitle_color", "0x00E5FF"))
    fontsize = 78 if W == 1080 else 64
    margin_v = int(H * 0.28) if W == 1080 else int(H * 0.12)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 1
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{fontsize},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,60,60,{margin_v},1
Style: Highlight,{font_name},{fontsize},{hl_bgr},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,60,60,{margin_v},1
Style: Heading,{font_name},52,&H00FFFFFF,&H000000FF,&H00000000,&HC0000000,-1,0,0,0,100,100,0,0,3,16,0,7,80,80,70,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    if CAPTIONS and text.strip():
        for n, (chunk, start, end) in enumerate(caption_chunks(text, dur)):
            display = chunk.upper() if lang in ("en", "es", "fr", "pt", "de", "id") else chunk
            display = display.replace("{", "(").replace("}", ")").replace("\n", " ")
            st_name = "Highlight" if n % 2 == 1 else "Default"
            pop = r"{\fscx92\fscy92\t(0,70,\fscx100\fscy100)}"
            events.append(
                f"Dialogue: 0,{_fmt_ass_time(start)},{_fmt_ass_time(end)},{st_name},,0,0,0,,{pop}{display}"
            )
    if heading:
        safe_head = heading.replace("{", "(").replace("}", ")").replace("\n", " ")
        events.append(
            f"Dialogue: 1,0:00:00.00,0:00:03.60,Heading,,0,0,0,,{safe_head}"
        )

    ass_path = WORK / f"sub_{idx}.ass"
    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return ass_path


def _drawtext(font: str, textfile: Path, style: str, enable: str) -> str:
    return (f"drawtext=fontfile='{ff_escape(font)}':textfile='{ff_escape(textfile)}':expansion=none"
            f":{style}:enable='{enable}'")


def build_scene(idx: int, text: str, visual: Path, audio: Path, dur: float, font: str, heading=None, style_meta: dict = None, lang: str = "en") -> Path:
    total = dur + 0.25
    filters = []
    if CAPTIONS or heading:
        ass_path = _write_ass_subtitles(idx, text, dur, font, style_meta or {}, heading=heading, lang=lang)
        fonts_dir = ff_escape(Path(font).parent)
        filters.append(f"ass='{ff_escape(ass_path)}':fontsdir='{fonts_dir}'")

    out = WORK / f"scene_{idx}.mp4"
    run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(visual), "-i", str(audio),
        "-t", f"{total:.3f}",
        "-vf", ",".join(filters) or "null",
        "-af", f"apad,atrim=0:{total:.3f}",
        "-map", "0:v:0", "-map", "1:a:0",
        "-r", str(FPS), "-vsync", "cfr", "-video_track_timescale", "90000",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", str(out),
    ])
    return out


def make_thumbnail(video: Path, title: str, font: str) -> Path:
    """1280x720 thumbnail rendered from the video frame with wrapped bold title."""
    clean_title = re.sub(r"[^\w\s!?.,:'\-\u0080-\uffff]", "", title).strip() or title
    lines = textwrap.wrap(clean_title.upper(), width=18)[:3]
    tf = WORK / "thumb.txt"
    tf.write_text("\n".join(lines), encoding="utf-8")
    vf = ("scale=1280:720,eq=brightness=-0.10:saturation=1.35,"
          "drawbox=x=0:y=ih*0.45:w=iw:h=ih*0.55:color=black@0.55:t=fill,"
          f"drawtext=fontfile='{ff_escape(font)}':textfile='{ff_escape(tf)}':expansion=none"
          ":fontsize=86:fontcolor=yellow:borderw=7:bordercolor=black:line_spacing=12:x=60:y=h*0.52")
    out = OUT / "thumbnail.jpg"
    vid_dur = media_duration(video)
    run(["ffmpeg", "-y", "-ss", f"{max(0.5, vid_dur * 0.3):.2f}", "-i", str(video),
         "-frames:v", "1", "-vf", vf, "-q:v", "3", str(out)])
    return out


# ------------------------------------------------------------ Audio + Visual rendering & Multi-Language Dubbing
def _render_language_variant(
    script: dict,
    fmt: str,
    visual_tracks: list[Path],
    out_dir: Path,
    lang: str,
    idea_used: bool,
) -> Path:
    """Renders localized voiceovers and native subtitles onto pre-rendered visual_tracks."""
    out_dir.mkdir(parents=True, exist_ok=True)
    font = find_font(lang)
    voice_prof = script.get("voice_profile")
    script_style = script.get("style", "")
    style_meta = {
        "subtitle_color": script.get("subtitle_color") or "0x00E5FF",
        "subtitle_shadow": "0x000000",
    }

    scenes, chapters, elapsed = [], [], 0.0
    for i, (sc, vis) in enumerate(zip(script["scenes"], visual_tracks)):
        audio = WORK / f"voice_{lang}_{i}.mp3"
        dur = make_voice(sc["text"], audio, voice_profile=voice_prof)
        vis_dur = media_duration(vis)
        # Ensure we use clean matching duration so audio never overruns or desyncs
        if sc.get("heading"):
            chapters.append((elapsed, sc["heading"]))
        scene_vid = build_scene(i, sc["text"], vis, audio, dur, font, sc.get("heading"), style_meta=style_meta, lang=lang)
        scenes.append(scene_vid)
        elapsed += dur + 0.25

    listfile = WORK / f"list_{lang}.txt"
    listfile.write_text("".join(f"file '{s.name}'\n" for s in scenes), encoding="utf-8")
    final = out_dir / "video.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
         "-c", "copy", "-movflags", "+faststart", str(final)])

    desc = script["description"].strip()
    if fmt == "long":
        if len(chapters) >= 3 and chapters[0][0] == 0:
            desc += "\n\nChapters:\n" + "\n".join(f"{fmt_ts(t)} {h}" for t, h in chapters)
        make_thumbnail(final, script["title"], font)
    desc += "\n\n" + " ".join(script["hashtags"])
    desc += "\n\nGenerated with AI animation & neural voice narration."
    meta = {
        "format": fmt, "language": lang, "topic": script["topic"], "title": script["title"],
        "description": desc, "hashtags": script["hashtags"],
        "category": script.get("category"), "style": script.get("style"),
        "source": "trend" if idea_used else "category",
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return final


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("topic", nargs="*")
    ap.add_argument("--format", choices=["short", "long", "story", "animated"], default=os.environ.get("VIDEO_FORMAT", "short"))
    ap.add_argument("--lang", default=os.environ.get("TARGET_LANGUAGE", "en"),
                    help="Primary language code (en, ta, hi, es, fr, pt, de, ja, ko, ar, id, or 'auto')")
    ap.add_argument("--dub", default=os.environ.get("DUB_LANGUAGES", ""),
                    help="Comma-separated extra languages to dub from the same animated visual track")
    args = ap.parse_args()
    fmt, topic = args.format, " ".join(args.topic).strip() or None
    configure(fmt)
    global _AI_VIDEO_COUNT
    _AI_VIDEO_COUNT = 0

    if not OFFLINE and not (GEMINI_API_KEY or GROQ_API_KEY):
        sys.exit("Missing GEMINI_API_KEY (and/or GROQ_API_KEY).")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("FFmpeg not found.")

    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir()
    OUT.mkdir(exist_ok=True)
    for stale in ("thumbnail.jpg", "video.mp4", "metadata.json"):
        (OUT / stale).unlink(missing_ok=True)
    for old_lang_dir in OUT.glob("lang_*"):
        shutil.rmtree(old_lang_dir, ignore_errors=True)

    history, state = load_history(), load_state()
    primary_lang = RaptarAgent.resolve_language(args.lang, state) if RaptarAgent else (args.lang if args.lang in LANGUAGES else "en")
    font = find_font(primary_lang)

    idea = None
    if not topic and not OFFLINE and os.environ.get("TRENDS", "1") == "1":
        try:
            import trends
            trends.ensure_fresh(state, llm_json, CATEGORIES)
            save_state(state)
            if random.random() < _trend_share(state):
                idea = trends.pick_idea(fmt, state)
        except Exception as e:
            print(f"  (trend research skipped: {type(e).__name__}: {e})")
    if idea:
        topic = f"{idea['topic']}. Angle: {idea.get('angle', '')}."
        if idea.get("style") in STYLES:
            state["_style_hint"] = idea["style"]
        print(f"    Trend idea picked: {idea['topic']}")

    print(f"1/4 Scripting ({fmt} | language={primary_lang})...")
    if fmt in ("story", "animated"):
        script = generate_story(topic, history, state, lang=primary_lang, animated=(fmt == "animated"))
    elif fmt == "long":
        script = generate_long(topic, history, state, lang=primary_lang)
    else:
        script = generate_short(topic, history, state, lang=primary_lang)

    if RaptarAgent and not OFFLINE and not script.get("_already_reviewed"):
        try:
            script = RaptarAgent().audit_and_fact_check(script)
        except Exception as e:
            print(f"  (agent audit pass skipped: {e})")

    script_style = script.get("style", "")
    STORY.setdefault("art_style", script.get("art_style") or "3D Pixar cinematic animation")
    STORY.setdefault("characters", script.get("characters") or "expressive animated characters")
    if not STORY["art_style"]:
        STORY["art_style"] = script.get("art_style") or "3D Pixar cinematic animation"

    use_animation = (
        ANIMATED_MODE == "always"
        or fmt in ("story", "animated")
        or (ANIMATED_MODE == "auto" and script_style in ANIMATED_STYLES)
    )
    print(f"    Topic: {script['topic']}\n    Title: {script['title']}\n    Style: {script_style} (Animated Engine: {use_animation})\n    Scenes: {len(script['scenes'])}")

    used: set = set()
    scenes, chapters, visual_tracks, elapsed = [], [], [], 0.0
    voice_prof = script.get("voice_profile")
    style_meta = {
        "subtitle_color": script.get("subtitle_color") or ("0x0000CC" if script_style == "horror" else "0x00E5FF"),
        "subtitle_shadow": "0x000000" if script_style == "horror" else "black@0.85",
    }

    for i, sc in enumerate(script["scenes"]):
        if i % 5 == 0 or fmt != "long":
            print(f"2-3/4 Scene {i + 1}/{len(script['scenes'])}: {sc['text'][:55]}")
        audio = WORK / f"voice_{i}.mp3"
        dur = make_voice(sc["text"], audio, voice_profile=voice_prof)
        if sc.get("heading"):
            chapters.append((elapsed, sc["heading"]))

        visual = None
        if use_animation or (fmt == "long" and i % 3 == 0 and sc.get("image_prompt")):
            visual = make_animated_visual(i, sc, dur + 0.25, style=script_style)
        if visual is None:
            visual = make_visual(i, sc["search_terms"], dur + 0.25, used, style=script_style)

        visual_tracks.append(visual)
        scenes.append(build_scene(i, sc["text"], visual, audio, dur, font, sc.get("heading"), style_meta=style_meta, lang=primary_lang))
        elapsed += dur + 0.25

    print("4/4 Joining scenes...")
    listfile = WORK / "list.txt"
    listfile.write_text("".join(f"file '{s.name}'\n" for s in scenes), encoding="utf-8")
    final = OUT / "video.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
         "-c", "copy", "-movflags", "+faststart", str(final)])

    desc = script["description"].strip()
    if fmt == "long":
        if len(chapters) >= 3 and chapters[0][0] == 0:
            desc += "\n\nChapters:\n" + "\n".join(f"{fmt_ts(t)} {h}" for t, h in chapters)
        make_thumbnail(final, script["title"], font)
    desc += "\n\n" + " ".join(script["hashtags"])
    desc += "\n\nAI Animated & Narrated via Raptar Autonomous Engine."
    meta = {
        "format": fmt, "language": primary_lang, "topic": script["topic"], "title": script["title"],
        "description": desc, "hashtags": script["hashtags"],
        "category": script.get("category"), "style": script.get("style"),
        "animated": use_animation, "ai_video_clips": _AI_VIDEO_COUNT,
        "source": "trend" if idea else "category",
    }
    (OUT / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    # Optional multi-language dubbing from the same rendered visual tracks
    dub_langs = [c.strip().lower() for c in (args.dub or "").split(",") if c.strip() and c.strip().lower() != primary_lang and c.strip().lower() in LANGUAGES]
    if dub_langs and RaptarAgent:
        agent = RaptarAgent()
        for dlang in dub_langs:
            print(f"    Dubbing localized version -> {dlang}...")
            loc_script = script if OFFLINE else agent.translate_script(script, dlang)
            loc_script["language"] = dlang
            if OFFLINE:
                prof = _get_profile(script_style, lang=dlang)
                loc_script["voice_profile"] = {"voice": prof["voice"], "rate": prof["rate"]}
            _render_language_variant(loc_script, fmt, visual_tracks, OUT / f"lang_{dlang}", dlang, bool(idea))

    if not OFFLINE:
        save_history(history + [script["topic"]])
        if script.get("category"):
            state["recent_categories"] = (state.get("recent_categories", []) + [script["category"]])[-10:]
        if script.get("style"):
            state["last_style"] = script["style"]
        state.pop("_style_hint", None)
        save_state(state)

    print(f"Done! -> {final} ({fmt_ts(media_duration(final))} | lang={primary_lang} | ai_video_clips={_AI_VIDEO_COUNT})")


if __name__ == "__main__":
    main()
