#!/usr/bin/env python3
"""
Fully automatic short-video generator (1080x1920 vertical), 100% free tools.

  Gemini (random topic + script) -> edge-tts (voice) -> Pixabay/Pexels (footage) -> FFmpeg (assembly + captions)

Usage:
    python make_video.py                  # random topic
    python make_video.py "my own topic"   # optional manual topic
    OFFLINE_TEST=1 python make_video.py   # no internet/API keys: tests FFmpeg assembly only

Output: output/video.mp4 and output/metadata.json
"""
import asyncio
import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

OFFLINE = os.environ.get("OFFLINE_TEST") == "1"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")  # optional (Pexels paused new keys)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-GuyNeural")

WORK, OUT, HISTORY = Path("work"), Path("output"), Path("history.json")
W, H, FPS = 1080, 1920, 30
WORDS_PER_CAPTION = 3

# The bot picks one of these at random, then asks Gemini for a fresh topic inside it.
CATEGORIES = [
    "space and astronomy", "ocean and sea creatures", "the human body", "animal behavior",
    "ancient history", "psychology and human behavior", "weird science", "famous inventions",
    "geography and strange places", "food science", "money and personal finance habits",
    "technology and the internet", "unsolved mysteries", "nature and weather",
    "productivity and study tips", "languages and words", "world records", "dinosaurs and prehistoric life",
]

FONT_CANDIDATES = [
    os.environ.get("FONT_PATH", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def find_font() -> str:
    for p in FONT_CANDIDATES:
        if p and Path(p).exists():
            return p
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


# ------------------------------------------------------------ history (no repeats)
def load_history() -> list[str]:
    try:
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_history(items: list[str]) -> None:
    HISTORY.write_text(json.dumps(items[-200:], indent=2), encoding="utf-8")


# ------------------------------------------------------------ 1. random topic + script
def generate_script(topic: str | None, history: list[str]) -> dict:
    if OFFLINE:
        return {
            "topic": "offline test", "title": "Offline test video",
            "description": "Testing the FFmpeg pipeline.", "hashtags": ["#test", "#shorts"],
            "scenes": [
                {"text": "Did you know this video was made without any internet?", "search_term": "test"},
                {"text": "Every scene gets its own background and animated captions.", "search_term": "test"},
                {"text": "If you can see this, the assembly part works perfectly.", "search_term": "test"},
            ],
        }

    if topic:
        topic_line = f"Topic: {topic}"
    else:
        category = random.choice(CATEGORIES)
        avoid = "; ".join(history[-60:]) or "none yet"
        topic_line = (f"Category: {category}\nChoose ONE specific, surprising, fresh topic inside this category "
                      f"(not generic). Do NOT reuse or closely resemble any of these previous topics: {avoid}")
    prompt = f"""You write scripts for viral YouTube Shorts / Instagram Reels.
{topic_line}

Return ONLY JSON with this exact shape:
{{
  "topic": "short name of the chosen topic",
  "title": "catchy title under 70 characters",
  "description": "1-2 sentence description",
  "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5"],
  "scenes": [{{"text": "one spoken sentence", "search_term": "1-3 word stock footage query"}}]
}}
Rules:
- 6 to 8 scenes, about 40-55 seconds of narration in total.
- Scene 1 must be a strong hook. The last scene is a short call to action (e.g. follow for more).
- Facts must be accurate. No invented statistics or quotes.
- search_term must describe something visually filmable (e.g. "ocean waves", "city traffic", "microscope")."""
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent")
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 1.0}}
    for attempt in range(3):
        try:
            r = requests.post(url, json=body, timeout=90,
                              headers={"x-goog-api-key": GEMINI_API_KEY})
            if r.ok:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                data = json.loads(text.replace("```json", "").replace("```", "").strip())
                if data.get("scenes"):
                    data.setdefault("topic", data.get("title", "unknown"))
                    return data
            print(f"Gemini attempt {attempt + 1} failed: {r.status_code} {r.text[:200]}")
        except Exception as e:  # network / JSON problems: retry
            print(f"Gemini attempt {attempt + 1} error: {e}")
    sys.exit("Could not get a script from Gemini. Check GEMINI_API_KEY / GEMINI_MODEL.")


# ------------------------------------------------------------ 2. voice
async def _tts(text: str, path: Path) -> None:
    import edge_tts
    await edge_tts.Communicate(text, TTS_VOICE, rate="+5%").save(str(path))


def make_voice(text: str, path: Path) -> float:
    if OFFLINE:  # silent audio, roughly 0.4s per word
        secs = max(1.5, 0.4 * len(text.split()))
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
             "-t", f"{secs:.2f}", "-c:a", "libmp3lame", str(path)])
        return media_duration(path)
    for attempt in range(3):
        try:
            asyncio.run(_tts(text, path))
            return media_duration(path)
        except Exception as e:
            print(f"TTS attempt {attempt + 1} failed: {e}")
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
    for size in ("large", "medium", "small", "tiny"):
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
                     params={"query": query, "orientation": "portrait", "per_page": 15}, timeout=30)
    r.raise_for_status()
    vids = [v for v in r.json().get("videos", []) if v["id"] not in used]
    if not vids:
        return False
    video = random.choice(vids[:8])
    files = [f for f in video["video_files"] if f.get("file_type") == "video/mp4"]
    files.sort(key=lambda f: abs((f.get("height") or 0) - 1920))
    used.add(video["id"])
    _download(files[0]["link"], dest)
    return True


def _gradient(dest: Path, seconds: float) -> None:
    """Last-resort background so a video is ALWAYS produced, even if stock search fails."""
    c0 = "0x%06x" % random.randint(0x101040, 0x4040a0)
    c1 = "0x%06x" % random.randint(0x300030, 0x802060)
    run(["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"gradients=s={W}x{H}:c0={c0}:c1={c1}:duration={seconds:.1f}:speed=0.03:rate={FPS}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(dest)])


def fetch_clip(query: str, dest: Path, used: set, seconds: float) -> None:
    if not OFFLINE:
        for q in (query, " ".join(query.split()[:1]), "nature"):
            for provider in (_pexels, _pixabay):
                try:
                    if provider(q, dest, used):
                        return
                except Exception as e:
                    print(f"  {provider.__name__} failed for '{q}': {e}")
    print(f"  using gradient background for '{query}'")
    _gradient(dest, seconds + 1)


# ------------------------------------------------------------ 4. assembly
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


def build_scene(idx: int, text: str, clip: Path, audio: Path, dur: float, font: str) -> Path:
    total = dur + 0.25
    filters = [f"scale={W}:{H}:force_original_aspect_ratio=increase", f"crop={W}:{H}",
               "setsar=1", f"fps={FPS}"]
    for n, (chunk, start, end) in enumerate(caption_chunks(text, dur)):
        tf = WORK / f"cap_{idx}_{n}.txt"
        tf.write_text(chunk.upper(), encoding="utf-8")
        filters.append(
            f"drawtext=fontfile='{ff_escape(font)}':textfile='{ff_escape(tf)}'"
            f":fontsize=78:fontcolor=white:borderw=6:bordercolor=black"
            f":x=(w-text_w)/2:y=h*0.62:enable='between(t,{start:.2f},{end:.2f})'")
    out = WORK / f"scene_{idx}.mp4"
    run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(clip), "-i", str(audio),
         "-t", f"{total:.2f}", "-vf", ",".join(filters), "-af", "apad",
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-ar", "44100", "-ac", "2", str(out)])
    return out


def main() -> None:
    topic = " ".join(sys.argv[1:]).strip() or None
    if not OFFLINE and not GEMINI_API_KEY:
        sys.exit("Missing GEMINI_API_KEY.")
    if not OFFLINE and not (PIXABAY_API_KEY or PEXELS_API_KEY):
        print("WARNING: no PIXABAY_API_KEY set - videos will use plain gradient backgrounds.")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("FFmpeg not found.")

    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir()
    OUT.mkdir(exist_ok=True)
    font = find_font()
    history = load_history()

    print("1/4 Choosing topic and writing script...")
    script = generate_script(topic, history)
    print(f"    Topic: {script['topic']}\n    Title: {script['title']}")

    used: set = set()
    scenes = []
    for i, sc in enumerate(script["scenes"]):
        print(f"2-3/4 Scene {i + 1}/{len(script['scenes'])}: {sc['text'][:55]}")
        audio, clip = WORK / f"voice_{i}.mp3", WORK / f"clip_{i}.mp4"
        dur = make_voice(sc["text"], audio)
        fetch_clip(sc["search_term"], clip, used, dur + 0.5)
        scenes.append(build_scene(i, sc["text"], clip, audio, dur, font))

    print("4/4 Joining scenes...")
    listfile = WORK / "list.txt"
    listfile.write_text("".join(f"file '{s.name}'\n" for s in scenes), encoding="utf-8")
    final = OUT / "video.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
         "-c", "copy", "-movflags", "+faststart", str(final)])

    meta = {"topic": script["topic"], "title": script["title"],
            "description": script["description"] + "\n\n" + " ".join(script["hashtags"]),
            "hashtags": script["hashtags"]}
    (OUT / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if not OFFLINE:
        save_history(history + [script["topic"]])
    print(f"Done! -> {final}  ({media_duration(final):.1f}s)")


if __name__ == "__main__":
    main()
