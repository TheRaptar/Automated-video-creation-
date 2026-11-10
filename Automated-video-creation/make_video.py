#!/usr/bin/env python3
"""
Fully automatic video generator for YouTube - Shorts (vertical) and long-form (horizontal). Free tools only.

  LLM (topic, script, fact-check)  -> edge-tts (voice) -> Pixabay/Pexels (several clips per scene)
  -> FFmpeg (cuts, captions / chapter titles) -> thumbnail (long-form)

Usage:
    python make_video.py                       # random Short
    python make_video.py --format long         # random long-form video (5-7 minutes)
    python make_video.py "my own topic"        # manual topic
    OFFLINE_TEST=1 python make_video.py        # no internet/API keys: tests FFmpeg assembly only

Settings (environment variables, all optional):
    VIDEO_FORMAT     short | long (the --format flag wins)
    VIDEO_SECONDS    Short length in seconds, a number or a range (default "40-60")
    LONG_SECONDS     long-form length in seconds (default "300-420")
    CATEGORIES       comma-separated list to restrict random topics, e.g. "space,physics,ocean life"
    REVIEW_SCRIPT    1 = fact-check pass over the script (default 1)
    TTS_VOICE        edge-tts voice (default en-US-GuyNeural) - keep it fixed for a consistent channel voice
Output: output/video.mp4, output/metadata.json (and output/thumbnail.jpg for long-form)
"""
import argparse
import asyncio
import base64
import json
import os
import random
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
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")  # optional (Pexels paused new keys)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GEMINI_BASE = os.environ.get("GEMINI_BASE", "https://generativelanguage.googleapis.com/v1beta")
GROQ_BASE = os.environ.get("GROQ_BASE", "https://api.groq.com/openai/v1")
TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-GuyNeural")
REVIEW = os.environ.get("REVIEW_SCRIPT", "1") == "1"

try:
    from raptar_agent import RaptarAgent
except ImportError:
    RaptarAgent = None

WORK, OUT, HISTORY, STATE = Path("work"), Path("output"), Path("history.json"), Path("state.json")
FPS = 30
WORDS_PER_CAPTION = 3

# Per-format settings, filled in by configure()
W, H = 1080, 1920
CAPTIONS = True
CLIP_LEN = 4.5
SIZE_ORDER = ("large", "medium", "small", "tiny")
ORIENT = "portrait"


def configure(fmt: str) -> None:
    global W, H, CAPTIONS, CLIP_LEN, SIZE_ORDER, ORIENT
    if fmt == "long":
        W, H, CAPTIONS, ORIENT = 1920, 1080, False, "landscape"
        CLIP_LEN = float(os.environ.get("CLIP_SECONDS_LONG", "6"))
        SIZE_ORDER = ("medium", "large", "small", "tiny")      # 1080p is native for landscape
    else:
        W, H, CAPTIONS, ORIENT = 1080, 1920, True, "portrait"
        CLIP_LEN = float(os.environ.get("CLIP_SECONDS", "4.5"))
        SIZE_ORDER = ("large", "medium", "small", "tiny")      # big source -> sharp portrait crop


def pick_seconds(env_name: str, default: str) -> int:
    raw = os.environ.get(env_name, default)
    if "-" in raw:
        a, b = raw.split("-", 1)
        return random.randint(int(a), int(b))
    return int(raw)


DEFAULT_CATEGORIES = [
    "Horror & Supernatural Thrillers",
    "Children's Whimsical Fables & Adventures",
    "Adult Psychological Thrillers & Sci-Fi",
    "Ancient Myths, Legends & Epic Lore",
    "Dark Folklore & Urban Legends",
    "Scientific Mysteries Transformed into Stories",
    "Entertaining Fictional Mysteries",
]
CATEGORIES = [c.strip() for c in os.environ.get("CATEGORIES", "").split(",") if c.strip()] or DEFAULT_CATEGORIES

# Dynamic narrative storytelling styles across different target audiences:
STYLES = {
    "horror": "Supernatural horror & creepypasta: eerie dread, atmospheric suspense, and shocking dark twists.",
    "fable": "Children's storybook fable: whimsical magic, friendly characters, wonder-filled science, and uplifting morals.",
    "thriller": "Adult psychological thriller: high-stakes tension, hidden motives, and gripping dramatic twists.",
    "scifi": "Mind-bending sci-fi fiction: speculative science anomalies, time loops, and cosmic mysteries.",
    "legend": "Epic mythology & folklore: ancient lore, forgotten civilizations, and legendary heroic sagas.",
    "mystery": "Unraveling enigmatic fiction: sudden revelations, hidden clues, and clever narrative twists.",
    "allure": "Magnetic allure & psychological intrigue.",
    "chemistry": "Emotional dynamics & chemistry.",
    "charm": "Clever wit and charisma.",
    "seduction": "Seductive suspense and intrigue.",
    "romance": "Sensual romance and aesthetics.",
    "fact": "Fact-based storytelling with dramatic narrative.",
    "story": "Illustrated storybook visual narrative.",
}

FONT_CANDIDATES = [
    os.environ.get("FONT_PATH", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def report_status(stage: str, progress: int, message: str, details: dict = None) -> None:
    """Emits live agent telemetry to agent_status.json for dashboard monitoring."""
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


def find_font() -> str:
    for p in FONT_CANDIDATES:
        if p and Path(p).exists():
            return p
    # Fallback to any TTF found in /usr/share/fonts
    for fallback in Path("/usr/share/fonts").glob("**/*.ttf"):
        if "Bold" in fallback.name or "Sans" in fallback.name:
            return str(fallback)
    sys.exit("No font found. Set FONT_PATH to a .ttf file.")


def ff_escape(path) -> str:
    return str(path).replace("\\", "/").replace(":", r"\:")


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Command failed: {' '.join(cmd[:4])} ...\n{r.stderr[-2000:]}")


def media_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def fmt_ts(t: float) -> str:
    t = int(t)
    h, m, s = t // 3600, (t % 3600) // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ------------------------------------------------------------ history + state (no repeats, no clashes)
def load_history() -> list[str]:
    try:
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_history(items: list[str]) -> None:
    HISTORY.write_text(json.dumps(items[-300:], indent=2), encoding="utf-8")


def load_state() -> dict:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ------------------------------------------------------------ LLM layer (Gemini -> Groq)
_DEAD_GEMINI: set = set()   # models that reported "no free quota"


def _parse_json(text: str):
    return json.loads(text.replace("```json", "").replace("```", "").strip())


def _gemini_models() -> list[str]:
    names = [GEMINI_MODEL]
    try:
        r = requests.get(f"{GEMINI_BASE}/models", params={"pageSize": 200},
                         headers={"x-goog-api-key": GEMINI_API_KEY}, timeout=30)
        if r.ok:
            skip = ("image", "tts", "audio", "live", "embed", "native", "robotics", "computer",
                    "preview", "exp", "omni", "thinking")
            found = sorted((m["name"].split("/")[-1] for m in r.json().get("models", [])
                            if "generateContent" in m.get("supportedGenerationMethods", [])
                            and "flash" in m["name"] and not any(s in m["name"] for s in skip)),
                           reverse=True)
            names += [n for n in found if n not in names]
    except requests.RequestException as e:
        print(f"  (could not list Gemini models: {type(e).__name__})")
    return names[:5]


def _gemini_json(prompt: str, rounds: int, valid):
    if not GEMINI_API_KEY:
        return None
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 1.0}}
    headers = {"x-goog-api-key": GEMINI_API_KEY}
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
            time.sleep(15)
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
            time.sleep(15)
    return None


def llm_json(prompt: str, rounds: int, valid):
    """Try Gemini first, then Groq. Returns a dict or None."""
    return _gemini_json(prompt, rounds, valid) or _groq_json(prompt, rounds, valid)


# ------------------------------------------------------------ 1. topic + script + fact-check
def _valid_scenes(d, minimum=3) -> bool:
    return (isinstance(d, dict) and isinstance(d.get("scenes"), list) and len(d["scenes"]) >= minimum
            and all(isinstance(s, dict) and isinstance(s.get("text"), str) and s["text"].strip()
                    for s in d["scenes"]))


def _normalize(script: dict) -> dict:
    for sc in script["scenes"]:
        terms = sc.get("search_terms") or [sc.get("search_term")]
        terms = [t.strip() for t in terms if isinstance(t, str) and t.strip()]
        sc["search_terms"] = terms or ["nature"]
        sc["text"] = sc["text"].strip()
    script.setdefault("topic", script.get("title", "unknown"))
    script.setdefault("title", script["topic"])
    script.setdefault("description", "")
    script["hashtags"] = [h if h.startswith("#") else "#" + h
                          for h in script.get("hashtags", []) if isinstance(h, str)][:6]
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
    depth = ("a rich topic that supports a ~6 minute documentary-style explanation with a clear story arc"
             if long_form else "a specific, surprising topic (not the most commonly told fact)")
    return (f"Category: {category}\nChoose ONE fresh topic inside this category: {depth}. "
            f"Do NOT reuse or closely resemble any of these previous topics: {avoid}"), category


def _review_texts(title: str, texts: list[str]) -> list[str]:
    """Second AI pass: a strict fact-checker softens or fixes doubtful claims. Best effort."""
    if not REVIEW or OFFLINE:
        return texts
    prompt = f"""You are a strict fact-checker and editor for an educational video titled "{title}".
Narration scenes (JSON list): {json.dumps(texts)}

Return ONLY JSON like {{"scenes": ["...", "..."], "issues": ["short note per change"]}} where:
- "scenes" has exactly {len(texts)} strings, in the same order.
- Rewrite or soften any claim that is inaccurate, exaggerated, unverifiable, or contains a number/date you are not certain about.
- Keep the conversational style and roughly the same length; keep any hook and any final call to action.
- If everything is accurate, return the scenes unchanged."""
    valid = lambda d: (isinstance(d, dict) and isinstance(d.get("scenes"), list)
                       and len(d["scenes"]) == len(texts)
                       and all(isinstance(x, str) and x.strip() for x in d["scenes"]))
    data = llm_json(prompt, rounds=1, valid=valid)
    if not data:
        print("  Fact-check skipped (no answer) - keeping original text.")
        return texts
    new = [x.strip() for x in data["scenes"]]
    print(f"  Fact-check: {sum(a != b for a, b in zip(texts, new))} scene(s) revised.")
    return new


def generate_short(topic, history, state) -> dict:
    total = pick_seconds("VIDEO_SECONDS", "40-60")
    if OFFLINE:
        return _normalize({
            "topic": "offline test", "title": "Offline test video", "description": "Testing.",
            "hashtags": ["#test"], "category": None, "style": "fact",
            "scenes": [
                {"text": "Did you know this video was made without any internet?", "search_terms": ["a"]},
                {"text": "Longer scenes are cut into several short clips, so the picture changes "
                         "every few seconds and the video feels far more alive than before.",
                 "search_terms": ["a", "b", "c"]},
                {"text": "If you can see this, assembly works perfectly.", "search_terms": ["a"]},
            ]})
    lo, words = max(5, total // 9), int(total * 2.6)
    topic_line, category = _topic_line(topic, history, state, False)
    hint = state.get("_style_hint")
    if hint in STYLES:
        style_key = hint
    else:
        style_key = weighted_choice([k for k in STYLES if k != state.get("last_style")] or list(STYLES),
                                    state.get("weights", {}).get("style", {}))
    profile = RaptarAgent.get_audience_profile(category or style_key) if RaptarAgent else {
        "target_audience": "adults", "style": style_key, "voice": TTS_VOICE, "rate": "+2%",
        "tone": "gripping and suspenseful", "subtitle_color": "white",
        "art_style": "cinematic 8k", "guidelines": "gripping storytelling"
    }
    prompt = f"""You are a master storyteller, creative narrative director, and cinematic AI fiction creator.
Your goal is to transform scientific concepts, educational ideas, real-world phenomena, or creative prompts into captivating storytelling content tailored for: {profile['target_audience']}.

Genre Style: {STYLES.get(style_key, style_key)}
Target Audience: {profile['target_audience']}
Tone & Pacing: {profile['tone']}
Audience Guidelines: {profile['guidelines']}

{topic_line}
{_trend_hint(state)}

Return ONLY JSON with this exact shape:
{{
  "topic": "short name of the chosen story",
  "title": "high-CTR curiosity title under 65 characters with narrative emoji",
  "description": "Engaging 1-2 sentence story description",
  "hashtags": ["#story", "#{profile['target_audience']}", "#{style_key}", "#viral"],
  "target_audience": "{profile['target_audience']}",
  "style": "{style_key}",
  "voice_profile": {{"voice": "{profile['voice']}", "rate": "{profile['rate']}"}},
  "subtitle_color": "{profile['subtitle_color']}",
  "scenes": [{{"text": "narration for this scene", "search_terms": ["cinematic visual query 1", "cinematic visual query 2"]}}]
}}
Rules:
- {lo} to {lo + 2} scenes, about {total} seconds in total (roughly {int(words * 0.9)} words of narration).
- Language & Tone: Strictly calibrated for '{profile['target_audience']}':
  - If children: Warm, friendly, wonder-filled language, friendly characters, positive lesson.
  - If horror: Ominous, suspenseful, atmospheric dread, spine-tingling plot twist.
  - If adults: Sophisticated, sharp, intellectual tension, thought-provoking twist.
  - If legend: Theatrical, epic lore, mythic grandeur.
- Scene 1 is an INSTANT scroll-stopping narrative hook under 12 words establishing mystery, wonder, or danger.
- The last scene ends with a captivating line inviting viewers to follow for the next story.
- search_terms: 2 DIFFERENT concrete, cinematic visual queries per scene matching the genre."""
    data = llm_json(prompt, rounds=2, valid=_valid_scenes)
    if not data:
        sys.exit("Could not get a script from Gemini or Groq (services busy or keys invalid).")
    script = _normalize(data)
    new = _review_texts(script["title"], [s["text"] for s in script["scenes"]])
    for sc, t in zip(script["scenes"], new):
        sc["text"] = t
    script.update(category=category, style=style_key, target_audience=profile["target_audience"],
                  voice_profile=script.get("voice_profile", {"voice": profile["voice"], "rate": profile["rate"]}),
                  subtitle_color=profile.get("subtitle_color", "white"))
    return script


def generate_long(topic, history, state) -> dict:
    total = pick_seconds("LONG_SECONDS", "300-420")
    if OFFLINE:
        return _normalize({
            "topic": "offline long test", "title": "Offline long-form test video", "description": "Testing.",
            "hashtags": ["#test"], "category": None,
            "scenes": [
                {"text": "Welcome to the offline long-form test.", "search_terms": ["a"], "heading": "Intro"},
                {"text": "This second scene is deliberately long so that it gets cut into more than one "
                         "clip, which proves that the picture keeps changing during long explanations.",
                 "search_terms": ["a", "b"]},
                {"text": "A new chapter begins right here.", "search_terms": ["a"], "heading": "Chapter two"},
                {"text": "And this is the closing line of the test video.", "search_terms": ["a"]},
            ]})
    n = max(5, min(9, round(total / 55)))
    per_section = int(total * 2.5) // n
    topic_line, category = _topic_line(topic, history, state, True)
    outline_prompt = f"""You are the head writer of a documentary-style educational YouTube channel.
{topic_line}

Plan a video of about {total // 60} minutes. Return ONLY JSON:
{{
  "topic": "short name of the topic",
  "title": "compelling, honest title under 70 characters",
  "description": "2-3 sentence description",
  "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4"],
  "sections": [{{"heading": "chapter title, max 5 words", "summary": "what this chapter covers, 1-2 sentences"}}]
}}
Rules: exactly {n} sections. Section 1 is a cold-open hook that creates curiosity without revealing the
answer. The last section is a satisfying payoff plus a short invitation to subscribe. Middle sections build
logically and each ends by pulling the viewer into the next. Only include things you are highly confident are
true and widely documented."""
    valid_outline = lambda d: (isinstance(d, dict) and isinstance(d.get("sections"), list)
                               and len(d["sections"]) >= 4
                               and all(isinstance(s, dict) and isinstance(s.get("heading"), str)
                                       for s in d["sections"]))
    outline = llm_json(outline_prompt, rounds=2, valid=valid_outline)
    if not outline:
        sys.exit("Could not plan the long video (Gemini and Groq both failed).")
    sections = outline["sections"][:n + 1]
    title = str(outline.get("title") or outline.get("topic") or "Untitled")
    plan = "\n".join(f"{i + 1}. {s['heading']}: {s.get('summary', '')}" for i, s in enumerate(sections))

    scenes, prev, ok = [], "This is the opening of the video.", 0
    for i, sec in enumerate(sections):
        print(f"  Writing chapter {i + 1}/{len(sections)}: {sec['heading']}")
        prompt = f"""You are writing the narration for chapter {i + 1} of {len(sections)}, "{sec['heading']}",
of a documentary-style YouTube video titled "{title}".
Full plan:
{plan}

The previous chapter ended with: "{prev}"
Write about {per_section} words of narration for THIS chapter only. Return ONLY JSON:
{{"scenes": [{{"text": "narration", "search_terms": ["visual query 1", "visual query 2", "visual query 3"]}}]}}
Rules:
- {max(3, per_section // 30)} to {max(4, per_section // 30) + 2} scenes, each 1-3 sentences and under 40 words.
- Calm, engaging narrator voice speaking to "you". No greetings, no "in this video" (except in chapter 1),
  and do not repeat what earlier chapters already said.
- {"End with a line that pulls the viewer into the next chapter." if i < len(sections) - 1 else "Finish with a satisfying conclusion and one short line inviting viewers to subscribe."}
- ACCURACY IS CRITICAL: only facts you are highly confident are true. Avoid exact numbers/dates unless certain.
  Never invent quotes or studies.
- search_terms: 3 different concrete, filmable stock-footage queries per scene, 1-3 words each. Never abstract
  words, names or brands."""
        data = llm_json(prompt, rounds=2, valid=lambda d: _valid_scenes(d, minimum=2))
        if not data:
            print(f"  WARNING: chapter '{sec['heading']}' failed - skipping it.")
            continue
        texts = _review_texts(title, [s["text"].strip() for s in data["scenes"]])
        for j, (sc, t) in enumerate(zip(data["scenes"], texts)):
            scenes.append({"text": t, "search_terms": sc.get("search_terms"),
                           "heading": sec["heading"].strip() if j == 0 else None})
        prev, ok = texts[-1], ok + 1
    if ok < max(4, len(sections) - 2):
        sys.exit(f"Only {ok} of {len(sections)} chapters could be written - aborting.")
    script = {"topic": outline.get("topic") or title, "title": title,
              "description": outline.get("description", ""), "hashtags": outline.get("hashtags", []),
              "scenes": scenes, "category": category}
    return _normalize(script)


# ------------------------------------------------------------ helpers: weighting + trend hints
def weighted_choice(options: list, weights: dict):
    """Random pick that favours options whose past videos performed better (weights default to 1)."""
    return random.choices(options, weights=[max(0.1, float(weights.get(o, 1.0))) for o in options])[0]


def _trend_share(state: dict) -> float:
    """How often to use a trend idea. TREND_SHARE fixes it; otherwise it adapts to what performed better."""
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
    return ("Hints from today's trend research (use only if they fit the topic): " + " | ".join(bits)) if bits else ""


def generate_story(topic, history, state) -> dict:
    """An original illustrated story Short tailored for children, horror fans, or adult fiction audiences."""
    total = pick_seconds("VIDEO_SECONDS", "40-60")
    topic_line, category = _topic_line(topic, history, state, False)
    profile = RaptarAgent.get_audience_profile(category or "story") if RaptarAgent else {
        "target_audience": "all_ages", "style": "story", "voice": TTS_VOICE, "rate": "+2%",
        "tone": "gripping and imaginative", "subtitle_color": "white",
        "art_style": "cinematic 8k storytelling, rich atmospheric lighting, 35mm film",
        "guidelines": "captivating fictional storytelling"
    }
    if OFFLINE:
        STORY.update(art_style=profile["art_style"], characters="main character in distinctive attire")
        return _normalize({
            "topic": "offline story test", "title": "The Whispering Mystery", "description": "Offline story demonstration.",
            "hashtags": ["#story", f"#{profile['target_audience']}", "#fictional"], "category": None, "style": "story",
            "scenes": [{"text": "In an ancient forest bathed in starlight, a strange discovery was waiting.",
                        "image_prompt": "cinematic vertical shot of ancient enchanted forest with starlight filtering through canopy, 9:16"},
                       {"text": "A glowing silver key turned in an invisible lock, revealing a forgotten doorway.",
                        "image_prompt": "close-up of floating glowing silver key unlocking a shimmering doorway between trees, 9:16"},
                       {"text": "Step into the mystery, and follow for tomorrow's chapter.",
                        "image_prompt": "dramatic shot of figure stepping through luminous portal into another realm, 9:16"}]})
    n_lo = max(7, total // 7)
    prompt = f"""You are a master storyteller, creative narrative director, and cinematic AI fiction creator.
You write captivating, original short fictional stories for YouTube Shorts and Instagram Reels tailored for: {profile['target_audience']}.

Target Audience: {profile['target_audience']}
Tone & Pacing: {profile['tone']}
Audience Guidelines: {profile['guidelines']}

{topic_line}
{_trend_hint(state)}

Return ONLY JSON with this exact shape:
{{
  "topic": "short name of the topic",
  "title": "curiosity-driven story title under 60 characters",
  "description": "1-2 sentence alluring description",
  "hashtags": ["#story", "#{profile['target_audience']}", "#fiction", "#viral"],
  "art_style": "{profile['art_style']}",
  "characters": "one sentence describing the look of the recurring fictional character",
  "scenes": [{{"text": "narration, 1-2 short sentences", "image_prompt": "detailed vertical 9:16 prompt reflecting the {profile['target_audience']} art style", "search_terms": ["cinematic fallback query"]}}]
}}
Rules:
- {n_lo} to {n_lo + 2} scenes, about {total} seconds of narration in total.
- Arc: captivating hook, rising tension/wonder, emotional or spooky turning point, climax, and closing call to action.
- Calibrate language and visuals strictly for '{profile['target_audience']}'.
- image_prompt must never ask for text, letters, logos or signs inside the picture."""
    data = llm_json(prompt, rounds=2, valid=lambda d: _valid_scenes(d, 5))
    if not data:
        sys.exit("Could not get a story script from Gemini or Groq.")
    script = _normalize(data)
    STORY.update(art_style=str(data.get("art_style") or profile["art_style"]),
                 characters=str(data.get("characters") or "main fictional character"))
    for sc in script["scenes"]:
        sc["image_prompt"] = str(sc.get("image_prompt") or sc["text"])
    script.update(category=category, style="story", target_audience=profile["target_audience"],
                  voice_profile=script.get("voice_profile", {"voice": profile["voice"], "rate": profile["rate"]}),
                  subtitle_color=profile.get("subtitle_color", "white"))
    return script


# ------------------------------------------------------------ 2. voice
async def _tts(text: str, path: Path, voice: str = None, rate: str = None) -> None:
    import edge_tts
    v = voice or TTS_VOICE
    r = rate or "+3%"
    await edge_tts.Communicate(text, v, rate=r).save(str(path))


def make_voice(text: str, path: Path, voice_profile: dict = None) -> float:
    if OFFLINE:  # silent audio, roughly 0.4s per word
        secs = max(1.5, 0.4 * len(text.split()))
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
             "-t", f"{secs:.2f}", "-c:a", "libmp3lame", str(path)])
        return media_duration(path)
    voice = (voice_profile or {}).get("voice") if isinstance(voice_profile, dict) else None
    rate = (voice_profile or {}).get("rate") if isinstance(voice_profile, dict) else None
    for attempt in range(3):
        try:
            asyncio.run(_tts(text, path, voice=voice, rate=rate))
            return media_duration(path)
        except Exception as e:
            print(f"TTS attempt {attempt + 1} failed: {e}")
            time.sleep(3)
    sys.exit("Voice generation failed (edge-tts).")


# ------------------------------------------------------------ 3. footage
def _download(link: str, dest: Path) -> None:
    with requests.get(link, stream=True, timeout=180) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(1 << 20):
                fh.write(chunk)


def _pixabay(query: str, dest: Path, used: set) -> bool:
    if not PIXABAY_API_KEY:
        return False
    r = requests.get("https://pixabay.com/api/videos/",
                     params={"key": PIXABAY_API_KEY, "q": query, "per_page": 20, "safesearch": "true"},
                     timeout=30)
    r.raise_for_status()
    hits = [h for h in r.json().get("hits", []) if h["id"] not in used]
    if not hits:
        return False
    hit = random.choice(hits[:10])
    for size in SIZE_ORDER:
        v = hit["videos"].get(size) or {}
        if v.get("url"):
            used.add(hit["id"])
            _download(v["url"], dest)
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
    _download(files[0]["link"], dest)
    return True


def _gradient(dest: Path, seconds: float, style: str = "") -> None:
    """Last-resort background with color palettes tailored to the storytelling genre."""
    if style == "horror":
        # Eerie pitch black void to blood-tinged charcoal shadow
        c0 = "0x%06x" % random.randint(0x05050a, 0x14050a)
        c1 = "0x%06x" % random.randint(0x150505, 0x2e0808)
    elif style == "fable":
        # Whimsical cheerful sky blue to pastel magical violet
        c0 = "0x%06x" % random.randint(0x205090, 0x4070b0)
        c1 = "0x%06x" % random.randint(0x904070, 0xb06090)
    elif style == "legend":
        # Ancient mythic gold and parchment bronze
        c0 = "0x%06x" % random.randint(0x302010, 0x503515)
        c1 = "0x%06x" % random.randint(0x503010, 0x754520)
    else:
        # Cinematic neo-noir deep navy to moody amber
        c0 = "0x%06x" % random.randint(0x0a1020, 0x182434)
        c1 = "0x%06x" % random.randint(0x1a1525, 0x2e1e30)
    run(["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"gradients=s={W}x{H}:c0={c0}:c1={c1}:duration={seconds:.1f}:speed=0.03:rate={FPS}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(dest)])


def fetch_clip(query: str, dest: Path, used: set, seconds: float, style: str = "") -> None:
    if not OFFLINE:
        fallbacks = ("creepy shadows", "foggy night") if style == "horror" else (
            ("cute cartoon animation", "magical starry sky") if style == "fable" else ("cinematic night city", "mysterious lighting")
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


# ------------------------------------------------------------ 4. assembly
def make_visual(idx: int, terms: list[str], total: float, used: set, style: str = "") -> Path:
    """Picture track of one scene, built from several short clips (a cut every few seconds)."""
    n = max(1, min(5, round(total / CLIP_LEN)))
    seg_len = total / n
    segs = []
    for k in range(n):
        raw = WORK / f"raw_{idx}_{k}.mp4"
        fetch_clip(terms[k % len(terms)], raw, used, seg_len + 0.5, style=style)
        seg = WORK / f"seg_{idx}_{k}.mp4"
        run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(raw), "-t", f"{seg_len:.2f}",
             "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}",
             "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(seg)])
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


# ------------------------------------------------------------ story format: AI illustrations + Ken Burns motion
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
    if not GEMINI_API_KEY or "gemini" in _IMG_DEAD:
        return False
    headers = {"x-goog-api-key": GEMINI_API_KEY}
    if not _IMG_MODELS:
        try:
            r = requests.get(f"{GEMINI_BASE}/models", params={"pageSize": 200}, headers=headers, timeout=30)
            if r.ok:
                _IMG_MODELS.extend(sorted((m["name"].split("/")[-1] for m in r.json().get("models", [])
                                           if "image" in m["name"] and "imagen" not in m["name"]
                                           and "generateContent" in m.get("supportedGenerationMethods", [])),
                                          reverse=True)[:2])
        except requests.RequestException:
            pass
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}}
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
                time.sleep(20)
                continue
            print(f"  image model {model}: HTTP {r.status_code} {r.text[:80].strip()}")
            if r.status_code in (403, 429):
                _IMG_DEAD.add("gemini")
                return False
            break
    return False


def _pollinations(prompt: str, dest: Path) -> bool:
    if "pollinations" in _IMG_DEAD:
        return False
    from urllib.parse import quote
    base = os.environ.get("POLLINATIONS_BASE", "https://image.pollinations.ai/prompt/")
    try:
        r = requests.get(base + quote(prompt[:800]), timeout=150,
                         params={"width": 768, "height": 1344, "nologo": "true", "seed": random.randint(1, 99999)})
        if r.ok and r.headers.get("content-type", "").startswith("image"):
            dest.write_bytes(r.content)
            return True
        print(f"  pollinations: HTTP {r.status_code}")
        if r.status_code in (401, 402, 403, 429):
            _IMG_DEAD.add("pollinations")
    except requests.RequestException as e:
        print(f"  pollinations: {type(e).__name__}")
    return False


def gen_image(prompt: str, dest: Path) -> bool:
    if OFFLINE:
        run(["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"gradients=s={W}x{H}:c0=0x{random.randint(0x202060, 0x6060c0):06x}:c1=0x{random.randint(0x602020, 0xc06060):06x}"
             ":duration=1:rate=1", "-frames:v", "1", str(dest)])
        return True
    return (_gemini_image(prompt, dest) and _valid_image(dest)) or (_pollinations(prompt, dest) and _valid_image(dest))


def make_story_visual(idx: int, sc: dict, total: float):
    """One AI illustration per scene, animated with a slow zoom or pan. Returns None if no image could be made."""
    img = WORK / f"img_{idx}.png"
    prompt = (f"{STORY['art_style']}. {STORY['characters']}. Scene: {sc.get('image_prompt', sc['text'])}. "
              "Vertical 9:16 composition, no text, no letters, no logos, no watermark.")
    if not gen_image(prompt, img):
        return None
    frames = max(2, int(total * FPS) + 2)
    mode = idx % 3
    z = {0: "min(1.0+0.0007*on,1.18)", 1: "max(1.18-0.0007*on,1.0)", 2: "1.12"}[mode]
    x = {0: "iw/2-(iw/zoom/2)", 1: "iw/2-(iw/zoom/2)", 2: f"(iw-iw/zoom)*on/{frames}"}[mode]
    out = WORK / f"story_{idx}.mp4"
    big_w, big_h = int(W * 1.5), int(H * 1.5)
    run(["ffmpeg", "-y", "-i", str(img), "-vf",
         f"scale={big_w}:{big_h}:force_original_aspect_ratio=increase,crop={big_w}:{big_h},"
         f"zoompan=z='{z}':x='{x}':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},setsar=1",
         "-t", f"{total:.2f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", str(out)])
    img.unlink(missing_ok=True)
    return out


def caption_chunks(text: str, duration: float):
    words = text.split()
    groups = [" ".join(words[i:i + WORDS_PER_CAPTION]) for i in range(0, len(words), WORDS_PER_CAPTION)]
    total = sum(len(g) for g in groups) or 1
    t, out = 0.0, []
    for g in groups:
        span = duration * len(g) / total
        out.append((g, t, t + span))
        t += span
    return out


def _drawtext(font: str, textfile: Path, style: str, enable: str) -> str:
    return (f"drawtext=fontfile='{ff_escape(font)}':textfile='{ff_escape(textfile)}':expansion=none"
            f":{style}:enable='{enable}'")


def build_scene(idx: int, text: str, visual: Path, audio: Path, dur: float, font: str, heading=None, style_meta: dict = None) -> Path:
    total = dur + 0.25
    filters = []
    if CAPTIONS:                                        # Shorts: high-energy kinetic typography
        highlight_color = (style_meta or {}).get("subtitle_color", "0x00E5FF") if isinstance(style_meta, dict) else "0x00E5FF"
        shadow_color = (style_meta or {}).get("subtitle_shadow", "black@0.85") if isinstance(style_meta, dict) else "black@0.85"
        for n, (chunk, start, end) in enumerate(caption_chunks(text, dur)):
            tf = WORK / f"cap_{idx}_{n}.txt"
            tf.write_text(chunk.upper(), encoding="utf-8")
            color = highlight_color if n % 2 == 1 else "white"
            filters.append(_drawtext(font, tf, f"fontsize=82:fontcolor={color}:borderw=7:bordercolor=black"
                                               f":shadowx=3:shadowy=3:shadowcolor={shadow_color}"
                                               f":x=(w-text_w)/2:y=h*0.58", f"between(t,{start:.2f},{end:.2f})"))
    if heading:                                         # long-form: chapter title card for a few seconds
        tf = WORK / f"head_{idx}.txt"
        tf.write_text(heading, encoding="utf-8")
        filters.append(_drawtext(font, tf, "fontsize=56:fontcolor=white:box=1:boxcolor=black@0.6"
                                           ":boxborderw=24:x=80:y=80", "between(t,0,3.5)"))
    out = WORK / f"scene_{idx}.mp4"
    run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(visual), "-i", str(audio),
         "-t", f"{total:.2f}", "-vf", ",".join(filters) or "null", "-af", "apad",
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-ar", "44100", "-ac", "2", str(out)])
    return out


def make_thumbnail(video: Path, title: str, font: str) -> Path:
    """1280x720 thumbnail: a frame from the video, darkened, with the title in big yellow letters."""
    lines = textwrap.wrap(title.upper(), width=16)[:3]
    tf = WORK / "thumb.txt"
    tf.write_text("\n".join(lines), encoding="utf-8")
    vf = ("scale=1280:720,eq=brightness=-0.10:saturation=1.35,"
          "drawbox=x=0:y=ih*0.45:w=iw:h=ih*0.55:color=black@0.55:t=fill,"
          f"drawtext=fontfile='{ff_escape(font)}':textfile='{ff_escape(tf)}':expansion=none"
          ":fontsize=96:fontcolor=yellow:borderw=7:bordercolor=black:line_spacing=12:x=60:y=h*0.5")
    out = OUT / "thumbnail.jpg"
    run(["ffmpeg", "-y", "-ss", f"{media_duration(video) * 0.3:.2f}", "-i", str(video),
         "-frames:v", "1", "-vf", vf, "-q:v", "3", str(out)])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("topic", nargs="*")
    ap.add_argument("--format", choices=["short", "long", "story"], default=os.environ.get("VIDEO_FORMAT", "short"))
    args = ap.parse_args()
    fmt, topic = args.format, " ".join(args.topic).strip() or None
    configure(fmt)

    if not OFFLINE and not (GEMINI_API_KEY or GROQ_API_KEY):
        sys.exit("Missing GEMINI_API_KEY (and/or GROQ_API_KEY).")
    if not OFFLINE and not (PIXABAY_API_KEY or PEXELS_API_KEY):
        print("WARNING: no PIXABAY_API_KEY set - videos will use plain gradient backgrounds.")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("FFmpeg not found.")

    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir()
    OUT.mkdir(exist_ok=True)
    for stale in ("thumbnail.jpg", "video.mp4", "metadata.json"):
        (OUT / stale).unlink(missing_ok=True)
    font = find_font()
    history, state = load_history(), load_state()

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
        topic = (f"{idea['topic']}. Angle: {idea.get('angle', '')}. (Trending because: "
                 f"{idea.get('why_trending', '')}. Use the trend only as inspiration for an accurate, evergreen "
                 "explainer; never present unverified news as fact.)")
        if idea.get("style") in STYLES:
            state["_style_hint"] = idea["style"]
        print(f"    Trend idea picked: {idea['topic']}")

    print(f"1/4 Choosing topic and writing the {fmt} script...")
    script = {"short": generate_short, "long": generate_long, "story": generate_story}[fmt](topic, history, state)
    if RaptarAgent and not OFFLINE:
        try:
            script = RaptarAgent().audit_and_fact_check(script)
        except Exception as e:
            print(f"  (agent audit pass skipped: {e})")
    print(f"    Topic: {script['topic']}\n    Title: {script['title']}\n    Scenes: {len(script['scenes'])}")

    used: set = set()
    scenes, chapters, elapsed, img_fail = [], [], 0.0, 0
    voice_prof = script.get("voice_profile")
    script_style = script.get("style", "")
    style_meta = {
        "subtitle_color": script.get("subtitle_color") or ("0x0000CC" if script_style == "horror" else ("0x00E5FF" if script_style == "fable" else "white")),
        "subtitle_shadow": "0x000000" if script_style == "horror" else "black@0.85"
    }

    for i, sc in enumerate(script["scenes"]):
        if i % 5 == 0 or fmt == "short":
            print(f"2-3/4 Scene {i + 1}/{len(script['scenes'])}: {sc['text'][:55]}")
        audio = WORK / f"voice_{i}.mp3"
        dur = make_voice(sc["text"], audio, voice_profile=voice_prof)
        if sc.get("heading"):
            chapters.append((elapsed, sc["heading"]))
        visual = None
        if fmt == "story":
            visual = make_story_visual(i, sc, dur + 0.25)
            if visual is None:
                img_fail += 1
                if img_fail >= 3 and img_fail == i + 1:
                    sys.exit("Image generation is not working (no provider answered) - aborting the story video.")
        if visual is None:
            visual = make_visual(i, sc["search_terms"], dur + 0.25, used, style=script_style)
        scenes.append(build_scene(i, sc["text"], visual, audio, dur, font, sc.get("heading"), style_meta=style_meta))
        elapsed += dur + 0.25

    if fmt == "story" and img_fail > len(script["scenes"]) * 0.2:
        sys.exit(f"{img_fail} of {len(script['scenes'])} illustrations failed - not publishing a mismatched story.")

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
    desc += "\n\nNarrated with an AI voice. Stock footage via Pixabay."
    meta = {"format": fmt, "topic": script["topic"], "title": script["title"],
            "description": desc, "hashtags": script["hashtags"],
            "category": script.get("category"), "style": script.get("style"),
            "source": "trend" if idea else "category"}
    (OUT / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    if not OFFLINE:
        save_history(history + [script["topic"]])
        if script.get("category"):
            state["recent_categories"] = (state.get("recent_categories", []) + [script["category"]])[-10:]
        if script.get("style"):
            state["last_style"] = script["style"]
        state.pop("_style_hint", None)
        save_state(state)
    print(f"Done! -> {final}  ({fmt_ts(media_duration(final))})")


if __name__ == "__main__":
    main()
