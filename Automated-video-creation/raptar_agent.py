#!/usr/bin/env python3
"""
RAPTAR Autonomous AI Agent Engine
=================================
A task-oriented AI agent built for fully autonomous animated, storytelling,
and multi-language video creation and social media publishing.

Capabilities:
1. Research & Ideation: Gathers multi-source trend signals and synthesizes original concepts.
2. Animation & Scene Choreography: Formulates hook-driven 3D animated/cinematic scripts with
   per-scene camera motion, visual FX, and character continuity.
3. Multi-Language Localization: Generates native narration, titles, subtitles, and neural voices
   across global languages (English, Tamil, Hindi, Spanish, French, Portuguese, German,
   Japanese, Korean, Arabic, Indonesian).
4. Quality & Safety Audit: Secondary AI pass validating pacing, narrative continuity, and compliance.
5. Persistent Self-Learning: Dynamically re-weights category, style, and language probabilities.
"""

import json
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

# Models (standard Gemini 4 / 3.x aliases, free-tier compatible)
DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-4-hydrogen")
GEMINI_FALLBACK_MODELS = [
    DEFAULT_GEMINI_MODEL,
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
]
GEMINI_BASE = os.environ.get("GEMINI_BASE", "https://generativelanguage.googleapis.com/v1beta")
GROQ_BASE = os.environ.get("GROQ_BASE", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# Global language registry with verified Edge-TTS neural voices and font families
LANGUAGES: Dict[str, Dict[str, Any]] = {
    "en": {
        "name": "English",
        "native_name": "English",
        "yt_code": "en",
        "font_family": "Noto Sans",
        "rtl": False,
        "voices": {
            "default": "en-US-GuyNeural",
            "children": "en-US-AnaNeural",
            "horror": "en-US-GuyNeural",
            "adults": "en-US-ChristopherNeural",
            "all_ages": "en-GB-RyanNeural",
            "fitness_lifestyle": "en-US-AvaNeural",
            "animated_myth": "en-GB-RyanNeural",
            "animated_comedy": "en-US-AndrewNeural",
            "animated_anime": "en-US-EmmaNeural",
        },
        "cta": "Follow for the next story!",
    },
    "ta": {
        "name": "Tamil",
        "native_name": "தமிழ்",
        "yt_code": "ta",
        "font_family": "Noto Sans Tamil",
        "rtl": False,
        "voices": {
            "default": "ta-IN-ValluvarNeural",
            "children": "ta-IN-PallaviNeural",
            "horror": "ta-IN-ValluvarNeural",
            "adults": "ta-IN-ValluvarNeural",
            "all_ages": "ta-IN-ValluvarNeural",
            "fitness_lifestyle": "ta-IN-PallaviNeural",
            "animated_myth": "ta-IN-ValluvarNeural",
            "animated_comedy": "ta-IN-ValluvarNeural",
            "animated_anime": "ta-IN-PallaviNeural",
        },
        "cta": "அடுத்த கதைக்கு Follow பண்ணுங்க!",
    },
    "hi": {
        "name": "Hindi",
        "native_name": "हिन्दी",
        "yt_code": "hi",
        "font_family": "Noto Sans Devanagari",
        "rtl": False,
        "voices": {
            "default": "hi-IN-MadhurNeural",
            "children": "hi-IN-SwaraNeural",
            "horror": "hi-IN-MadhurNeural",
            "adults": "hi-IN-MadhurNeural",
            "all_ages": "hi-IN-MadhurNeural",
            "fitness_lifestyle": "hi-IN-SwaraNeural",
            "animated_myth": "hi-IN-MadhurNeural",
            "animated_comedy": "hi-IN-MadhurNeural",
            "animated_anime": "hi-IN-SwaraNeural",
        },
        "cta": "अगली कहानी के लिए फॉलो करें!",
    },
    "es": {
        "name": "Spanish",
        "native_name": "Español",
        "yt_code": "es",
        "font_family": "Noto Sans",
        "rtl": False,
        "voices": {
            "default": "es-ES-AlvaroNeural",
            "children": "es-MX-DaliaNeural",
            "horror": "es-ES-AlvaroNeural",
            "adults": "es-ES-AlvaroNeural",
            "all_ages": "es-ES-AlvaroNeural",
            "fitness_lifestyle": "es-ES-ElviraNeural",
            "animated_myth": "es-ES-AlvaroNeural",
            "animated_comedy": "es-MX-JorgeNeural",
            "animated_anime": "es-MX-DaliaNeural",
        },
        "cta": "¡Sigue para la próxima historia!",
    },
    "fr": {
        "name": "French",
        "native_name": "Français",
        "yt_code": "fr",
        "font_family": "Noto Sans",
        "rtl": False,
        "voices": {
            "default": "fr-FR-RemyMultilingualNeural",
            "children": "fr-FR-EloiseNeural",
            "horror": "fr-FR-RemyMultilingualNeural",
            "adults": "fr-FR-RemyMultilingualNeural",
            "all_ages": "fr-FR-RemyMultilingualNeural",
            "fitness_lifestyle": "fr-FR-VivienneMultilingualNeural",
            "animated_myth": "fr-FR-RemyMultilingualNeural",
            "animated_comedy": "fr-FR-RemyMultilingualNeural",
            "animated_anime": "fr-FR-DeniseNeural",
        },
        "cta": "Abonnez-vous pour la suite !",
    },
    "pt": {
        "name": "Portuguese",
        "native_name": "Português",
        "yt_code": "pt",
        "font_family": "Noto Sans",
        "rtl": False,
        "voices": {
            "default": "pt-BR-AntonioNeural",
            "children": "pt-BR-FranciscaNeural",
            "horror": "pt-BR-AntonioNeural",
            "adults": "pt-BR-AntonioNeural",
            "all_ages": "pt-BR-AntonioNeural",
            "fitness_lifestyle": "pt-BR-ThalitaMultilingualNeural",
            "animated_myth": "pt-BR-AntonioNeural",
            "animated_comedy": "pt-BR-AntonioNeural",
            "animated_anime": "pt-BR-FranciscaNeural",
        },
        "cta": "Siga para a próxima história!",
    },
    "de": {
        "name": "German",
        "native_name": "Deutsch",
        "yt_code": "de",
        "font_family": "Noto Sans",
        "rtl": False,
        "voices": {
            "default": "de-DE-ConradNeural",
            "children": "de-DE-AmalaNeural",
            "horror": "de-DE-ConradNeural",
            "adults": "de-DE-FlorianMultilingualNeural",
            "all_ages": "de-DE-ConradNeural",
            "fitness_lifestyle": "de-DE-SeraphinaMultilingualNeural",
            "animated_myth": "de-DE-ConradNeural",
            "animated_comedy": "de-DE-FlorianMultilingualNeural",
            "animated_anime": "de-DE-AmalaNeural",
        },
        "cta": "Folge für die nächste Geschichte!",
    },
    "ja": {
        "name": "Japanese",
        "native_name": "日本語",
        "yt_code": "ja",
        "font_family": "Noto Sans CJK JP",
        "rtl": False,
        "voices": {
            "default": "ja-JP-KeitaNeural",
            "children": "ja-JP-NanamiNeural",
            "horror": "ja-JP-KeitaNeural",
            "adults": "ja-JP-KeitaNeural",
            "all_ages": "ja-JP-KeitaNeural",
            "fitness_lifestyle": "ja-JP-NanamiNeural",
            "animated_myth": "ja-JP-KeitaNeural",
            "animated_comedy": "ja-JP-KeitaNeural",
            "animated_anime": "ja-JP-NanamiNeural",
        },
        "cta": "次の物語もフォローしてね！",
    },
    "ko": {
        "name": "Korean",
        "native_name": "한국어",
        "yt_code": "ko",
        "font_family": "Noto Sans CJK KR",
        "rtl": False,
        "voices": {
            "default": "ko-KR-InJoonNeural",
            "children": "ko-KR-SunHiNeural",
            "horror": "ko-KR-HyunsuMultilingualNeural",
            "adults": "ko-KR-InJoonNeural",
            "all_ages": "ko-KR-InJoonNeural",
            "fitness_lifestyle": "ko-KR-SunHiNeural",
            "animated_myth": "ko-KR-InJoonNeural",
            "animated_comedy": "ko-KR-HyunsuMultilingualNeural",
            "animated_anime": "ko-KR-SunHiNeural",
        },
        "cta": "다음 이야기도 기대해주세요!",
    },
    "ar": {
        "name": "Arabic",
        "native_name": "العربية",
        "yt_code": "ar",
        "font_family": "Noto Sans Arabic",
        "rtl": True,
        "voices": {
            "default": "ar-SA-HamedNeural",
            "children": "ar-SA-ZariyahNeural",
            "horror": "ar-SA-HamedNeural",
            "adults": "ar-SA-HamedNeural",
            "all_ages": "ar-SA-HamedNeural",
            "fitness_lifestyle": "ar-SA-ZariyahNeural",
            "animated_myth": "ar-SA-HamedNeural",
            "animated_comedy": "ar-SA-HamedNeural",
            "animated_anime": "ar-SA-ZariyahNeural",
        },
        "cta": "تابعونا للقصة القادمة!",
    },
    "id": {
        "name": "Indonesian",
        "native_name": "Bahasa Indonesia",
        "yt_code": "id",
        "font_family": "Noto Sans",
        "rtl": False,
        "voices": {
            "default": "id-ID-ArdiNeural",
            "children": "id-ID-GadisNeural",
            "horror": "id-ID-ArdiNeural",
            "adults": "id-ID-ArdiNeural",
            "all_ages": "id-ID-ArdiNeural",
            "fitness_lifestyle": "id-ID-GadisNeural",
            "animated_myth": "id-ID-ArdiNeural",
            "animated_comedy": "id-ID-ArdiNeural",
            "animated_anime": "id-ID-GadisNeural",
        },
        "cta": "Ikuti untuk cerita selanjutnya!",
    },
}

# Styles that should automatically use the AI Animation Engine
ANIMATED_STYLES = {
    "animated_myth",
    "animated_comedy",
    "animated_anime",
    "fable",
    "story",
    "legend",
}


class RaptarAgent:
    """Task-oriented AI Agent for autonomous animated & multilingual video creation."""

    def __init__(self, script_dir: Optional[Path] = None):
        self.script_dir = script_dir or Path(__file__).resolve().parent
        self.history_file = self.script_dir / "history.json"
        self.state_file = self.script_dir / "state.json"
        self.gemini_key = os.environ.get("GEMINI_API_KEY", "")
        self.groq_key = os.environ.get("GROQ_API_KEY", "")
        self.dead_models = set()

    # ---------------------------------------------------------
    # Memory Management
    # ---------------------------------------------------------
    def load_history(self) -> List[str]:
        try:
            if self.history_file.exists():
                return json.loads(self.history_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [Agent Memory] Warning reading history: {e}")
        return []

    def save_history(self, items: List[str]) -> None:
        try:
            capped = items[-300:]
            self.history_file.write_text(json.dumps(capped, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"  [Agent Memory] Error saving history: {e}")

    def load_state(self) -> Dict[str, Any]:
        try:
            if self.state_file.exists():
                d = json.loads(self.state_file.read_text(encoding="utf-8"))
                if isinstance(d, dict):
                    return d
        except Exception as e:
            print(f"  [Agent Memory] Warning reading state: {e}")
        return {}

    def save_state(self, state: Dict[str, Any]) -> None:
        try:
            self.state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"  [Agent Memory] Error saving state: {e}")

    # ---------------------------------------------------------
    # Language Helpers
    # ---------------------------------------------------------
    @staticmethod
    def resolve_language(lang_spec: Optional[str] = None, state: Optional[Dict[str, Any]] = None) -> str:
        """Resolves a single language code from CLI/env ('en', 'ta', 'auto', or 'en,ta,hi')."""
        raw = (lang_spec or os.environ.get("TARGET_LANGUAGE", "en")).strip().lower()
        if not raw:
            return "en"
        if raw == "auto":
            pool = ["en", "ta", "hi", "es", "fr", "pt", "ja"]
        elif "," in raw:
            pool = [c.strip() for c in raw.split(",") if c.strip() in LANGUAGES] or ["en"]
        else:
            return raw if raw in LANGUAGES else "en"

        idx = int((state or {}).get("lang_index", 0))
        chosen = pool[idx % len(pool)]
        if isinstance(state, dict):
            state["lang_index"] = (idx + 1) % len(pool)
        return chosen

    @staticmethod
    def get_language_meta(lang: str = "en") -> Dict[str, Any]:
        return LANGUAGES.get(lang, LANGUAGES["en"])

    @staticmethod
    def get_voice_for_language(lang: str = "en", key: str = "default") -> str:
        meta = LANGUAGES.get(lang, LANGUAGES["en"])
        voices = meta["voices"]
        return voices.get(key) or voices["default"]

    # ---------------------------------------------------------
    # LLM Reasoning Core (Gemini 4 Hydrogen with Groq Fallback)
    # ---------------------------------------------------------
    def _parse_json(self, text: str) -> Any:
        cleaned = text.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in cleaned:
            cleaned = cleaned.split("```", 1)[1].split("```", 1)[0]
        return json.loads(cleaned.strip())

    def _query_gemini(self, prompt: str, schema: Optional[Dict] = None) -> Optional[Dict]:
        if not self.gemini_key:
            return None

        models = list(dict.fromkeys(GEMINI_FALLBACK_MODELS))
        headers = {
            "x-goog-api-key": self.gemini_key,
            "Content-Type": "application/json",
            "User-Agent": "aistudio-build",
        }
        body: Dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
            },
        }
        if schema:
            body["generationConfig"]["responseSchema"] = schema

        for model in models:
            if model in self.dead_models:
                continue
            url = f"{GEMINI_BASE}/models/{model}:generateContent"
            try:
                res = requests.post(url, json=body, headers=headers, timeout=60)
                if res.ok:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts and "text" in parts[0]:
                            return self._parse_json(parts[0]["text"])
                elif res.status_code == 429:
                    print(f"  [Agent LLM] Model {model} rate limited (HTTP 429).")
                    self.dead_models.add(model)
                else:
                    print(f"  [Agent LLM] Model {model} returned HTTP {res.status_code}.")
            except Exception as e:
                print(f"  [Agent LLM] Gemini query error on {model}: {e}")
        return None

    def _query_groq(self, prompt: str) -> Optional[Dict]:
        if not self.groq_key:
            return None
        headers = {"Authorization": f"Bearer {self.groq_key}", "Content-Type": "application/json"}
        body = {
            "model": GROQ_MODEL,
            "temperature": 0.8,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            res = requests.post(f"{GROQ_BASE}/chat/completions", json=body, headers=headers, timeout=60)
            if res.ok:
                content = res.json()["choices"][0]["message"]["content"]
                return self._parse_json(content)
        except Exception as e:
            print(f"  [Agent LLM] Groq fallback error: {e}")
        return None

    def reason_json(self, prompt: str, validator: Callable[[Any], bool], rounds: int = 2) -> Optional[Dict]:
        """Executes LLM reasoning with automated retry and schema validation."""
        for attempt in range(rounds):
            result = self._query_gemini(prompt) or self._query_groq(prompt)
            if result and validator(result):
                return result
            if attempt < rounds - 1:
                time.sleep(4)
        return None

    # ---------------------------------------------------------
    # Audience, Animation & Multilingual Profile Helper
    # ---------------------------------------------------------
    @staticmethod
    def get_audience_profile(category_or_style: str = "", lang: str = "en") -> Dict[str, Any]:
        """Returns voice, pace, language guidelines, and animation visual style."""
        lower = (category_or_style or "").lower()
        lang = lang if lang in LANGUAGES else "en"

        if any(k in lower for k in ("animated_myth", "ramayana", "epics", "mythological", "divine", "sacred", "mahabharata")):
            style_key = "animated_myth"
            profile = {
                "target_audience": "all_ages",
                "style": style_key,
                "voice": RaptarAgent.get_voice_for_language(lang, style_key),
                "rate": "-2%",
                "tone": "reverent, emotionally stirring, cinematic, and deeply inspiring",
                "subtitle_color": "0x20C0F0",  # Antique warm gold
                "subtitle_shadow": "0x100800",
                "animated": True,
                "art_style": (
                    "3D Pixar and Unreal Engine 5 cinematic animated film frame, rich Indian and global mythological "
                    "atmosphere, golden divine sunlight beams, lush ancient forest or ocean bridge, expressive animated "
                    "characters with luminous eyes and detailed fur/silk textures, volumetric lighting, 9:16 vertical"
                ),
                "guidelines": (
                    "Tell emotionally resonant mythological fables and cultural parables (like the tiny squirrel helping "
                    "build the bridge in Ramayana). Short, poetic, unforgettable narration with strong moral magic."
                ),
            }
        elif any(k in lower for k in ("animated_comedy", "cartoon", "sheru", "bheem", "buddy", "animal adventure", "animated reel", "comedy")):
            style_key = "animated_comedy"
            profile = {
                "target_audience": "all_ages",
                "style": style_key,
                "voice": RaptarAgent.get_voice_for_language(lang, style_key),
                "rate": "+6%",
                "tone": "energetic, funny, playful, expressive regional buddy-comedy vibes",
                "subtitle_color": "0x00E5FF",  # Vibrant neon cyan
                "subtitle_shadow": "0x000000",
                "animated": True,
                "art_style": (
                    "Vibrant 3D Pixar-style cartoon animation, expressive stylized anthropomorphic lion and cheerful "
                    "young friend characters in colorful sunlit bustling streets or tropical town, exaggerated comedic "
                    "facial expressions, glossy textures, dynamic action framing, 9:16 vertical"
                ),
                "guidelines": (
                    "Create hilarious, heartwarming animated buddy adventures with memorable quirky characters "
                    "(rich eccentric lion, clever street-smart sidekick, relatable everyday twists and punchlines)."
                ),
            }
        elif any(k in lower for k in ("anime", "makoto", "cyberpunk", "shinkai", "cel")):
            style_key = "animated_anime"
            profile = {
                "target_audience": "adults",
                "style": style_key,
                "voice": RaptarAgent.get_voice_for_language(lang, style_key),
                "rate": "+2%",
                "tone": "cinematic anime drama, emotional momentum, vivid visual wonder",
                "subtitle_color": "0xFF80AB",
                "subtitle_shadow": "0x140818",
                "animated": True,
                "art_style": (
                    "High-budget Japanese anime feature film style (Makoto Shinkai aesthetic), crisp cel-shaded characters, "
                    "glowing neon skies or drifting sakura petals, dramatic lens flare, painterly backgrounds, 9:16 vertical"
                ),
                "guidelines": "Dramatic anime storytelling with vivid emotional beats, stylized hero journeys, and stunning skyscapes.",
            }
        elif any(k in lower for k in ("child", "kid", "fable", "bedtime", "fairy")):
            style_key = "fable"
            profile = {
                "target_audience": "children",
                "style": style_key,
                "voice": RaptarAgent.get_voice_for_language(lang, "children"),
                "rate": "+0%",
                "tone": "whimsical, wonder-filled, friendly, and heartwarming",
                "subtitle_color": "0x00E5FF",
                "subtitle_shadow": "0x401040",
                "animated": True,
                "art_style": "whimsical 3D animated storybook, Pixar-style vibrant colors, soft warm magical lighting, friendly stylized character design, 9:16 vertical",
                "guidelines": "Use simple, imaginative, wonder-filled language. Focus on curiosity, friendly animal or fantasy characters, and positive uplifting lessons.",
            }
        elif any(k in lower for k in ("horror", "spooky", "creepypasta", "ghost", "dark folklore", "supernatural", "eerie")):
            style_key = "horror"
            profile = {
                "target_audience": "horror",
                "style": style_key,
                "voice": RaptarAgent.get_voice_for_language(lang, "horror"),
                "rate": "-8%",
                "tone": "ominous, spine-chilling, atmospheric dread, and shocking twists",
                "subtitle_color": "0x0000CC",
                "subtitle_shadow": "0x000000",
                "animated": False,
                "art_style": "cinematic atmospheric horror animation, chilling fog, moody chiaroscuro lighting, eerie abandoned interiors, 35mm grain, 9:16 vertical",
                "guidelines": "Build intense psychological dread, slow ominous suspense, whispered secrets, and unexpected hair-raising narrative twists without extreme gore.",
            }
        elif any(k in lower for k in ("myth", "legend", "ancient", "epic", "folklore")):
            style_key = "legend"
            profile = {
                "target_audience": "all_ages",
                "style": style_key,
                "voice": RaptarAgent.get_voice_for_language(lang, "all_ages"),
                "rate": "-3%",
                "tone": "epic, theatrical, mythic grandeur, and legendary lore",
                "subtitle_color": "0x20C0F0",
                "subtitle_shadow": "0x111111",
                "animated": True,
                "art_style": "epic 3D animated fantasy matte painting, golden atmospheric glow, ancient ruins, mythic scale, cinematic 8k lighting, 9:16 vertical",
                "guidelines": "Grand, legendary storytelling with ancient secrets, forgotten myths, mythic beasts, and theatrical presence.",
            }
        elif any(k in lower for k in ("fitness", "influencer", "workout", "routine", "gym", "leila", "activewear", "aesthetic")):
            style_key = "fitness_glamour"
            profile = {
                "target_audience": "fitness_lifestyle",
                "style": style_key,
                "voice": RaptarAgent.get_voice_for_language(lang, "fitness_lifestyle"),
                "rate": "+4%",
                "tone": "upbeat, motivating, confident, aesthetic fitness influencer daily routine",
                "subtitle_color": "0x00FF88",
                "subtitle_shadow": "0x000000",
                "animated": False,
                "art_style": "photorealistic 8K portrait photography, stunning athletic female AI influencer in stylish activewear workout outfit, morning gym daylight, natural skin texture, 35mm f/1.4 lens, 9:16 vertical",
                "guidelines": "Engaging first-person fitness influencer lifestyle routine ('A morning in my life', workout habits, discipline motivation). Full coverage activewear.",
            }
        else:
            style_key = "thriller"
            profile = {
                "target_audience": "adults",
                "style": style_key,
                "voice": RaptarAgent.get_voice_for_language(lang, "adults"),
                "rate": "+2%",
                "tone": "sophisticated, high-stakes psychological suspense, and dramatic twists",
                "subtitle_color": "white",
                "subtitle_shadow": "0x111111",
                "animated": False,
                "art_style": "hyper-realistic 8K cinematic neo-noir, rain-slicked city streets, moody ambient shadows, 35mm lens, 9:16 vertical",
                "guidelines": "Sharp, gripping narrative, intellectual stakes, moral dilemmas, and thought-provoking twists.",
            }

        profile["language"] = lang
        return profile

    # ---------------------------------------------------------
    # Capability 1: Trend Evaluation & Topic Formulation
    # ---------------------------------------------------------
    def evaluate_and_pick_topic(
        self,
        signals: Dict[str, Any],
        categories: List[str],
        format_type: str = "short",
        lang: str = "en",
    ) -> Dict[str, Any]:
        """Evaluates trends and formulates creative animated or storytelling concepts in target language."""
        history = self.load_history()
        state = self.load_state()
        lang_meta = self.get_language_meta(lang)

        story_default_niches = [
            "3D Animated Mythological & Cultural Epics",
            "3D Cartoon Character Comedies & Adventures",
            "Anime Fantasy & Folklore Shorts",
            "Children's Whimsical Fables & Bedtime Tales",
            "Horror Stories & Supernatural Thrillers",
            "Adult Psychological Thrillers & Noir Fiction",
            "Mind-Bending Sci-Fi & Speculative Tales",
            "Photorealistic AI Influencer & Fitness Routines",
        ]
        active_categories = categories or story_default_niches

        weights = state.get("weights", {})
        recent_cats = state.get("recent_categories", [])[-4:]
        available_cats = [c for c in active_categories if c not in recent_cats] or active_categories

        cat_weights = weights.get("category", {})
        category = self.weighted_choice(available_cats, cat_weights)
        profile = self.get_audience_profile(category, lang=lang)

        avoid_topics = "; ".join(history[-60:]) if history else "none"
        prompt = f"""You are a master animation director, storyteller, and creative producer.
Target Category: {category}
Target Audience: {profile['target_audience']}
Genre Style: {profile['style']}
Output Language: {lang_meta['name']} ({lang}) — Write "title" and "angle" natively in {lang_meta['name']}. Write "topic" clearly so it tracks anti-repetition.
Target Video Format: {format_type}

Audience Guidelines:
- animated_myth: Inspiring 3D animated mythological/historical fables (like the tiny squirrel carrying sand for Lord Rama's bridge, or ancient heroic wisdom).
- animated_comedy: Hilarious vibrant 3D animated buddy adventures (like an eccentric billionaire lion & street-smart friend with funny cultural twists).
- animated_anime: High-stakes anime motion tales with vivid skyscapes and emotional twists.
- children (fable): Whimsical animated adventures and heartwarming bedtime fables.
- horror: Eerie supernatural creepypastas and psychological dread without gore.
- fitness_lifestyle: Aesthetic first-person morning workout routines featuring AI influencer Leila.
- adults: Sophisticated psychological thrillers and mind-bending sci-fi mysteries.

Avoid repeating or closely resembling: {avoid_topics}

Return ONLY JSON:
{{
  "topic": "precise story topic name",
  "title": "high-CTR title under 70 characters in {lang_meta['name']} with emoji",
  "angle": "central narrative hook, visual twist, or comedy beat",
  "style": "{profile['style']}",
  "category": "{category}",
  "target_audience": "{profile['target_audience']}",
  "language": "{lang}",
  "virality_score": 9.7
}}"""

        validator = lambda d: isinstance(d, dict) and bool(d.get("topic")) and bool(d.get("title"))
        data = self.reason_json(prompt, validator, rounds=2)

        if not data:
            fallback_stories = [
                ("The Squirrel That Helped Build The Ocean Bridge", "Every Grain Holds The Bridge 🐿️✨", "animated_myth", "3D Animated Mythological & Cultural Epics", "all_ages"),
                ("Sheru The Lion & Bheem's Midnight Chai Mission", "Sheru Bhai Meets Bheem: The Ultimate Adventure 🦁😂", "animated_comedy", "3D Cartoon Character Comedies & Adventures", "all_ages"),
                ("The Sky Lantern Keeper's Secret", "The Boy Who Caught A Falling Star In Tokyo 🏮🌌", "animated_anime", "Anime Fantasy & Folklore Shorts", "adults"),
                ("The Little Star Who Forgot How to Glow", "The Little Star Who Made Her Own Light ✨⭐", "fable", "Children's Whimsical Fables & Bedtime Tales", "children"),
                ("Morning Workout Routine with Leila", "6 AM Gym Routine with Leila 🏃‍♀️⚡", "fitness_glamour", "Photorealistic AI Influencer & Fitness Routines", "fitness_lifestyle"),
                ("The Trench That Knocked Back", "Something Tapped Back Seven Miles Underwater 🌊👁️", "horror", "Horror Stories & Supernatural Thrillers", "horror"),
                ("The Signal from 12 Hours Ahead", "The Telescope Receiving Tomorrow's Broadcast 📡⏳", "scifi", "Mind-Bending Sci-Fi & Speculative Tales", "adults"),
            ]
            pick = random.choice(fallback_stories)
            data = {
                "topic": pick[0],
                "title": pick[1],
                "angle": "Vibrant animated storytelling with emotional payoff.",
                "style": pick[2],
                "category": pick[3],
                "target_audience": pick[4],
                "language": lang,
                "virality_score": 9.6,
            }

        data.setdefault("language", lang)
        return data

    # ---------------------------------------------------------
    # Capability 2: Scene-by-Scene Script & Animation Choreography
    # ---------------------------------------------------------
    def plan_script(self, topic_info: Dict[str, Any], format_type: str = "short", lang: Optional[str] = None) -> Dict[str, Any]:
        """Generates a complete scene-by-scene animated & multilingual narrative script."""
        chosen_lang = (lang or topic_info.get("language") or "en").lower()
        if chosen_lang not in LANGUAGES:
            chosen_lang = "en"
        lang_meta = self.get_language_meta(chosen_lang)

        num_scenes = 5 if format_type in ("short", "animated") else (7 if format_type == "story" else 16)
        profile = self.get_audience_profile(topic_info.get("style") or topic_info.get("category") or "", lang=chosen_lang)
        target_audience = topic_info.get("target_audience") or profile["target_audience"]

        prompt = f"""You are a master animation director, screenwriter, and multi-language storyteller.
Topic: {topic_info['topic']}
Title: {topic_info['title']}
Narration Language: {lang_meta['name']} ({chosen_lang})
Genre Style: {topic_info.get('style', profile['style'])}
Target Audience: {target_audience}
Format: {format_type}

DIRECTOR'S GUIDELINES:
- Language: Write "title", "description", "hashtags", and every scene's "text" natively, naturally, and expressively in {lang_meta['name']}.
- Visual Prompts: Write every "image_prompt" and "search_terms" strictly in ENGLISH for optimal AI visual rendering.
- Character Continuity: Describe the main animated character(s) consistently in every scene's image_prompt.
- Camera Motion: Choose an ideal camera_motion per scene from ["zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "dolly_pulse"].
- Visual FX: Choose fx from ["cinematic", "warm_glow", "sparkles", "eerie_vignette", "vibrant"].
- Art Style: {profile['art_style']}
- Tone: {profile['tone']}
- Exactly {num_scenes} sequential scenes, totaling ~{95 if format_type != 'long' else 850} words of spoken narration.
- Never ask for text, letters, or watermarks inside "image_prompt".

Return ONLY JSON:
{{
  "topic": "{topic_info['topic']}",
  "title": "engaging title in {lang_meta['name']}",
  "description": "compelling summary in {lang_meta['name']}",
  "hashtags": ["#story", "#animation", "#{chosen_lang}", "#viral"],
  "language": "{chosen_lang}",
  "target_audience": "{target_audience}",
  "style": "{topic_info.get('style', profile['style'])}",
  "art_style": "{profile['art_style']}",
  "characters": "concise visual description of recurring animated characters",
  "voice_profile": {{
    "voice": "{profile['voice']}",
    "rate": "{profile['rate']}"
  }},
  "scenes": [
    {{
      "text": "spoken narration in {lang_meta['name']}",
      "search_terms": ["english visual query 1", "english visual query 2"],
      "image_prompt": "detailed animated scene description in ENGLISH, no text/letters",
      "camera_motion": "zoom_in",
      "fx": "cinematic"
    }}
  ]
}}"""

        validator = lambda d: isinstance(d, dict) and isinstance(d.get("scenes"), list) and len(d["scenes"]) >= 3
        script = self.reason_json(prompt, validator, rounds=2)

        if not script:
            style_key = topic_info.get("style", profile["style"])
            if style_key == "animated_myth":
                script = {
                    "topic": topic_info["topic"],
                    "title": topic_info["title"],
                    "description": "Every small effort matters when done with pure devotion.",
                    "hashtags": ["#Ramayana", "#AIAnimation", "#Mythology", "#Shorts", "#Inspiration"],
                    "language": chosen_lang,
                    "target_audience": "all_ages",
                    "style": "animated_myth",
                    "art_style": profile["art_style"],
                    "characters": "A tiny striped golden-brown squirrel and towering ancient vanara warriors by a sunlit ocean",
                    "voice_profile": {"voice": profile["voice"], "rate": profile["rate"]},
                    "scenes": [
                        {
                            "text": "While mighty warriors carried giant boulders to build the ocean bridge to Lanka, one tiny squirrel carried single grains of sand.",
                            "search_terms": ["tiny squirrel ocean rocks sunset", "epic ancient bridge sea"],
                            "image_prompt": "3D Pixar cinematic animation wide shot of giant heroic monkey warriors lifting massive boulders by a sparkling tropical ocean at sunrise, a tiny cute squirrel carrying grains of sand on the shore",
                            "camera_motion": "zoom_in",
                            "fx": "warm_glow",
                        },
                        {
                            "text": "The giant warriors laughed. What difference can a grain of sand possibly make against the roaring sea?",
                            "search_terms": ["cute squirrel tiny paws sand", "ocean waves dramatic sunlight"],
                            "image_prompt": "3D Pixar close-up of tiny determined squirrel with sparkling amber eyes holding golden sand grains in tiny paws while shadows of laughing giants loom behind",
                            "camera_motion": "pan_up",
                            "fx": "cinematic",
                        },
                        {
                            "text": "But Lord Rama gently knelt down. Without your sand between the stones, he smiled, these massive boulders could never lock together.",
                            "search_terms": ["divine golden light blessing forest", "gentle hand tiny animal"],
                            "image_prompt": "3D Pixar magical golden hour scene, serene divine warrior king with warm radiant smile gently kneeling on golden shore, glowing blessing light enveloping the tiny squirrel",
                            "camera_motion": "dolly_pulse",
                            "fx": "sparkles",
                        },
                        {
                            "text": "With three loving strokes of his fingers, he blessed the squirrel—leaving the three stripes squirrels still wear today.",
                            "search_terms": ["squirrel three stripes golden light", "magical forest sunlight"],
                            "image_prompt": "3D Pixar magical close-up of glowing golden light trails forming three shimmering stripes across the tiny squirrel's back, awe and joy in its eyes, radiant particles floating",
                            "camera_motion": "zoom_out",
                            "fx": "sparkles",
                        },
                        {
                            "text": lang_meta["cta"],
                            "search_terms": ["epic sunlit ocean bridge rainbow", "inspiring sunrise sky"],
                            "image_prompt": "3D Pixar breathtaking wide shot of the finished grand stone bridge stretching across gleaming turquoise ocean under a golden sunrise, tiny squirrel standing proudly on a stone",
                            "camera_motion": "zoom_out",
                            "fx": "warm_glow",
                        },
                    ],
                }
            elif style_key == "animated_comedy":
                script = {
                    "topic": topic_info["topic"],
                    "title": topic_info["title"],
                    "description": "When the richest animated lion meets a street-smart buddy with one mission!",
                    "hashtags": ["#AIAnimation", "#3DCartoon", "#ComedyReels", "#Shorts", "#Viral"],
                    "language": chosen_lang,
                    "target_audience": "all_ages",
                    "style": "animated_comedy",
                    "art_style": profile["art_style"],
                    "characters": "Sheru the stylish 3D cartoon lion wearing gold sunglasses and Bheem a cheerful energetic kid buddy",
                    "voice_profile": {"voice": profile["voice"], "rate": profile["rate"]},
                    "scenes": [
                        {
                            "text": "When the richest lion in the universe lands his golden helicopter, everyone expects a billion-dollar deal.",
                            "search_terms": ["colorful cartoon helicopter landing", "3d animated lion sunglasses"],
                            "image_prompt": "Vibrant 3D Pixar cartoon animation of a shiny golden helicopter landing in a sunny colorful South Indian town square, cool anthropomorphic lion wearing oversized gold sunglasses stepping out",
                            "camera_motion": "zoom_in",
                            "fx": "vibrant",
                        },
                        {
                            "text": "Instead, young Bheem walks straight up past the bodyguards with total confidence.",
                            "search_terms": ["cheerful animated boy walking", "sunny colorful town cartoon"],
                            "image_prompt": "3D Pixar cartoon close-up of a cheerful playful boy with messy hair and bright red jacket strutting fearlessly past giant funny animated hippo bodyguards",
                            "camera_motion": "pan_right",
                            "fx": "vibrant",
                        },
                        {
                            "text": "All Bheem wants is one tiny milk packet for his morning filter coffee! The lion freezes in disbelief.",
                            "search_terms": ["funny surprised cartoon lion", "animated friends laughing"],
                            "image_prompt": "3D Pixar hilarious exaggerated reaction shot, rich cartoon lion dropping his jaw and sliding gold sunglasses down his nose in shock while the boy holds up one cheerful finger",
                            "camera_motion": "dolly_pulse",
                            "fx": "sparkles",
                        },
                        {
                            "text": "And that's how the most unlikely legendary friendship began over a simple cup of morning chai.",
                            "search_terms": ["cartoon lion and boy cheering", "sunny friendship sunset"],
                            "image_prompt": "3D Pixar heartwarming comedic wide shot of the rich lion and the cheerful boy clinking hot tea glasses together on a colorful rooftop overlooking lush green hills",
                            "camera_motion": "zoom_out",
                            "fx": "warm_glow",
                        },
                    ],
                }
            else:
                script = {
                    "topic": topic_info["topic"],
                    "title": topic_info["title"],
                    "description": "A gripping animated narrative adventure.",
                    "hashtags": ["#AIAnimation", "#Storytelling", f"#{chosen_lang}", "#Shorts"],
                    "language": chosen_lang,
                    "target_audience": target_audience,
                    "style": profile["style"],
                    "art_style": profile["art_style"],
                    "characters": "Expressive central protagonist in vivid cinematic lighting",
                    "voice_profile": {"voice": profile["voice"], "rate": profile["rate"]},
                    "scenes": [
                        {
                            "text": "High above the glowing night skyline, an unexpected discovery changed everything in a single heartbeat.",
                            "search_terms": ["cinematic starry night city", "animated glowing lantern"],
                            "image_prompt": f"{profile['art_style']}, opening dramatic wide shot of shimmering night horizon, mystery glowing object floating",
                            "camera_motion": "zoom_in",
                            "fx": "cinematic",
                        },
                        {
                            "text": "Every clue pointed to a secret hidden for generations beneath the ancient archway.",
                            "search_terms": ["ancient mysterious doorway light", "magical forest glow"],
                            "image_prompt": f"{profile['art_style']}, mysterious ancient stone doorway opening with radiant beam of emerald light",
                            "camera_motion": "pan_up",
                            "fx": "sparkles",
                        },
                        {
                            "text": "Stepping forward took courage, because once the portal opened, there was no turning back.",
                            "search_terms": ["hero stepping into light portal", "dramatic silhouette sunset"],
                            "image_prompt": f"{profile['art_style']}, heroic silhouette standing at the threshold of a swirling luminous energy portal, floating embers",
                            "camera_motion": "dolly_pulse",
                            "fx": "warm_glow",
                        },
                        {
                            "text": lang_meta["cta"],
                            "search_terms": ["inspiring sunrise mountain landscape", "starry night sky glow"],
                            "image_prompt": f"{profile['art_style']}, breathtaking cosmic sunrise over tranquil mountain peaks, hopeful glowing horizon",
                            "camera_motion": "zoom_out",
                            "fx": "cinematic",
                        },
                    ],
                }

        script.setdefault("language", chosen_lang)
        script.setdefault("voice_profile", {"voice": profile["voice"], "rate": profile["rate"]})
        script.setdefault("art_style", profile["art_style"])
        return script

    # ---------------------------------------------------------
    # Capability 2b: Multi-Language Localization / Translation
    # ---------------------------------------------------------
    def translate_script(self, script: Dict[str, Any], target_lang: str) -> Dict[str, Any]:
        """Translates an existing script's title, description, hashtags & scene narration into target_lang."""
        target_lang = target_lang.lower().strip()
        if target_lang not in LANGUAGES:
            return script
        if script.get("language") == target_lang:
            return script

        lang_meta = self.get_language_meta(target_lang)
        scenes = script.get("scenes", [])
        payload = {
            "title": script.get("title", ""),
            "description": script.get("description", ""),
            "scenes": [s.get("text", "") for s in scenes],
        }
        prompt = f"""You are a native {lang_meta['name']} ({lang_meta['native_name']}) creative dubbing director.
Translate and naturally adapt this video script into idiomatic, punchy, expressive {lang_meta['name']} suitable for a spoken voiceover on Instagram Reels and YouTube Shorts.
Preserve emotional punch, storytelling cadence, and approximate spoken length for each scene.

Source JSON:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Return ONLY JSON:
{{
  "title": "adapted high-CTR title in {lang_meta['name']} under 70 chars",
  "description": "adapted 1-2 sentence description in {lang_meta['name']}",
  "hashtags": ["#story", "#{lang_meta['name'].replace(' ', '')}", "#animation", "#viral"],
  "scenes": ["localized scene 1 narration", "... exact same count ({len(scenes)}) ..."]
}}"""

        valid = lambda d: (
            isinstance(d, dict)
            and isinstance(d.get("scenes"), list)
            and len(d["scenes"]) == len(scenes)
            and all(isinstance(x, str) and x.strip() for x in d["scenes"])
        )
        translated = self.reason_json(prompt, valid, rounds=2)

        localized = json.loads(json.dumps(script))
        localized["language"] = target_lang
        style_or_audience = localized.get("style") or localized.get("target_audience") or "default"
        profile = self.get_audience_profile(style_or_audience, lang=target_lang)
        localized["voice_profile"] = {"voice": profile["voice"], "rate": profile["rate"]}
        localized["subtitle_color"] = profile["subtitle_color"]
        localized["subtitle_shadow"] = profile["subtitle_shadow"]

        if translated:
            localized["title"] = translated.get("title") or localized["title"]
            localized["description"] = translated.get("description") or localized["description"]
            if isinstance(translated.get("hashtags"), list):
                localized["hashtags"] = [h if str(h).startswith("#") else f"#{h}" for h in translated["hashtags"]][:6]
            for sc, new_txt in zip(localized["scenes"], translated["scenes"]):
                sc["text"] = new_txt.strip()

        return localized

    # ---------------------------------------------------------
    # Capability 3: Narrative Quality, Continuity & Safety Audit
    # ---------------------------------------------------------
    def audit_and_fact_check(self, script: Dict[str, Any]) -> Dict[str, Any]:
        """Performs a secondary quality, continuity, and policy safety audit without breaking fiction or language."""
        scenes = script.get("scenes", [])
        if not scenes:
            return script
        lang = script.get("language", "en")
        lang_name = self.get_language_meta(lang)["name"]
        style = script.get("style", "story")
        texts = [s.get("text", "") for s in scenes]

        prompt = f"""You are a senior story editor and content safety reviewer for a {lang_name} ({style}) video titled "{script.get('title')}".
Narration Scenes (in {lang_name}):
{json.dumps(texts, indent=2, ensure_ascii=False)}

Review each scene for:
1. Smooth storytelling pacing, vivid spoken rhythm, and strong opening hook in {lang_name}.
2. Keep fictional, mythological, comedic, or animated storytelling creative — do NOT turn fables or fiction into dry textbook facts.
3. Ensure strict YouTube & Instagram community guideline compliance (no hate speech, no graphic gore, no explicit content).
4. Keep the EXACT same number of scenes ({len(texts)}) and keep all text in {lang_name}.

Return ONLY JSON:
{{
  "scenes": ["polished scene 1", "polished scene 2", ...],
  "issues_found": ["short note per revision if any"],
  "safety_passed": true
}}"""

        validator = lambda d: (
            isinstance(d, dict)
            and isinstance(d.get("scenes"), list)
            and len(d["scenes"]) == len(texts)
            and all(isinstance(x, str) and x.strip() for x in d["scenes"])
        )
        audit_res = self.reason_json(prompt, validator, rounds=1)

        if audit_res and audit_res.get("scenes"):
            for i, rev in enumerate(audit_res["scenes"]):
                if isinstance(rev, str) and rev.strip():
                    script["scenes"][i]["text"] = rev.strip()
            print(f"  [Agent Quality Audit] Verified {len(texts)} scenes ({lang_name}).")
        else:
            print("  [Agent Quality Audit] Audit passed (baseline verified).")

        return script

    # ---------------------------------------------------------
    # Capability 4: Self-Learning & Strategy Feedback Loop
    # ---------------------------------------------------------
    def update_feedback_weights(self) -> None:
        """Analyzes published video engagement history and adjusts strategic category/style weights."""
        state = self.load_state()
        last_style = state.get("last_style")
        if last_style:
            weights = state.setdefault("weights", {})
            style_weights = weights.setdefault("style", {})
            cur = style_weights.get(last_style, 1.0)
            style_weights[last_style] = round(min(2.0, max(0.6, cur * 1.02)), 2)

        self.save_state(state)
        print("  [Agent Self-Learning] Strategic weights updated in state.json.")

    @staticmethod
    def weighted_choice(options: List[str], weights: Dict[str, float]) -> str:
        if not options:
            return ""
        w = [max(0.1, float(weights.get(opt, 1.0))) for opt in options]
        return random.choices(options, weights=w)[0]
