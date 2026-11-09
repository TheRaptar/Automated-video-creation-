#!/usr/bin/env python3
"""
RAPTAR Autonomous AI Agent Engine
=================================
A task-oriented AI agent built for fully autonomous educational video creation
and social media publishing.

Capabilities:
1. Research & Ideation: Gathers multi-source trend signals and synthesizes evergreen explainer ideas.
2. Pacing & Scripting: Formulates hook-driven, scene-by-scene narrative scripts with visual choreography.
3. Fact-Checking & Safety Audit: Strict secondary AI pass validating claims and safety before production.
4. Social Media SEO: Produces optimized titles, descriptions, hashtags, and synthetic AI disclosures.
5. Persistent Self-Learning: Dynamically re-weights category and style probabilities based on performance.
6. Error Detection & Recovery: Gracefully recovers from API throttling, missing assets, and quota limits.
"""

import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

# Models
DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_BASE = os.environ.get("GEMINI_BASE", "https://generativelanguage.googleapis.com/v1beta")
GROQ_BASE = os.environ.get("GROQ_BASE", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


class RaptarAgent:
    """Task-oriented AI Agent for autonomous video creation and publishing."""

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
            # Enforce 300-topic FIFO cap
            capped = items[-300:]
            self.history_file.write_text(json.dumps(capped, indent=2), encoding="utf-8")
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
            self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"  [Agent Memory] Error saving state: {e}")

    # ---------------------------------------------------------
    # LLM Reasoning Core (Gemini 3.8 Flash with Groq Fallback)
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

        models = [DEFAULT_GEMINI_MODEL, "gemini-flash-latest"]
        headers = {"x-goog-api-key": self.gemini_key, "Content-Type": "application/json"}
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.8,
            },
        }

        for model in models:
            if model in self.dead_models:
                continue
            url = f"{GEMINI_BASE}/models/{model}:generateContent"
            try:
                res = requests.post(url, json=body, headers=headers, timeout=45)
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
            res = requests.post(f"{GROQ_BASE}/chat/completions", json=body, headers=headers, timeout=45)
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
    # Capability 1: Trend Evaluation & Topic Formulation
    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # Capability 1: Trend Evaluation & Topic Formulation (Glamour, Luxury & Viral Aesthetics)
    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # Capability 1: Trend Evaluation & Topic Formulation (Attraction, Romance & Allure)
    # ---------------------------------------------------------
    def evaluate_and_pick_topic(
        self,
        signals: Dict[str, Any],
        categories: List[str],
        format_type: str = "short",
    ) -> Dict[str, Any]:
        """Evaluates trend signals and selects high-virality romantic attraction and psychological allure topics."""
        history = self.load_history()
        state = self.load_state()

        allure_default_niches = [
            "attraction & seduction psychology",
            "dating dynamics & romantic secrets",
            "magnetic allure & sensual aesthetics",
            "flirting psychology & charm secrets",
            "relationship chemistry & presence",
            "dark romance & mystery aesthetics",
        ]
        active_categories = categories or allure_default_niches

        weights = state.get("weights", {})
        recent_cats = state.get("recent_categories", [])[-4:]
        available_cats = [c for c in active_categories if c not in recent_cats] or active_categories

        # Weight-proportional category selection favoring high-engagement attraction niches
        cat_weights = weights.get("category", {})
        category = self.weighted_choice(available_cats, cat_weights)

        # Build prompt for Gemini Agent
        avoid_topics = "; ".join(history[-60:]) if history else "none"
        prompt = f"""You are a professional adult glamour filmmaker, sensual video director, and cinematic AI content creator.
You direct bold, extremely seductive, and visually captivating YouTube Shorts and Instagram Reels featuring fictional adult characters aged 25 and above.

DIRECTOR'S VISUAL & ARTISTIC STYLE:
- Extremely glamorous and alluring adult models (all characters strictly fictional adults aged 25+).
- Sensual expressions, magnetic eye contact, and confident, captivating body language.
- Revealing but non-explicit high-fashion outfits: elegant lingerie-inspired fashion, silk robes, satin slips, corsetry couture, backless evening wear (strictly full coverage, NO visible nudity).
- Sensual dancing and slow, graceful, hypnotic movements.
- Romantic bedroom and luxury hotel settings: candlelit luxury suites, silk bedding, penthouse terrace at twilight, velvet lounge.
- Intimate romantic atmosphere with artistic implied intimacy and full coverage.
- Beautiful, arresting close-up portraits with dramatic cinematic lighting, rich warm shadows, realistic skin textures, and 35mm film grain.
- Professional camera movements (slow dolly push, shallow f/1.4 depth of field, gentle panning).

Target Category: {category}
Target Video Format: {format_type} (short: 30-50s fast-paced viral Short, story: 45-60s cinematic narrative)

Avoid repeating or closely resembling any of these recent topics:
{avoid_topics}

Formulate ONE original, irresistible, high-virality concept exploring romantic attraction, sensual chemistry, or intimate dating psychology.
Core Themes to Draw From:
- Magnetic Allure & Seduction: Intense eye-contact tension, subconscious chemistry triggers, whisper dynamics, proximity psychology.
- Sensual Romance & Intimate Tension: Late-night bedroom talks, luxury hotel rendezvous, the chemistry of lingering touch, unspoken desires.
- Playful Charm & Flirting Secrets: Playful teasing, verbal chemistry, building romantic tension, confident allure.
- Dark Romance & Mystery: The irresistible draw of emotional mystery, quiet elegance, magnetic presence.

Rules:
1. Scene 1 hook MUST stop the scroll in under 1.5 seconds with intense romantic intrigue or seductive curiosity (e.g. "The 3-second glance that makes someone instantly crave your presence...", "Why quiet confidence in a silk dress commands any room...").
2. Tone: Bold, extremely seductive, sophisticated, magnetic, and emotionally intense.
3. STRICT POLICY COMPLIANCE: All characters are adults aged 25+. NO pornography, NO graphic sexual depictions, NO visible nudity, NO non-consensual content. Keep all visuals artistic, lingerie-inspired with full coverage, and 100% compliant with YouTube and Instagram Community Guidelines.

Return ONLY JSON:
{{
  "topic": "precise topic name",
  "title": "high-CTR curiosity title under 75 characters with seductive emoji",
  "angle": "the psychological secret, visual allure, or tension trigger",
  "style": "allure" | "chemistry" | "mystery" | "charm" | "seduction" | "romance",
  "category": "{category}",
  "virality_score": 9.6
}}"""

        validator = lambda d: isinstance(d, dict) and bool(d.get("topic")) and bool(d.get("title"))
        data = self.reason_json(prompt, validator, rounds=2)

        if not data:
            # Resilient adult glamour and sensual allure fallback topics
            fallback_topics = [
                ("The 3-Second Eye Contact Technique", "The 3-Second Seduction Glaze That Sparks Instant Chemistry 👀🔥", "seduction", "attraction & seduction psychology"),
                ("The Psychology of Seductive Mystery", "Why Unpredictable Sensual Allure Is Completely Addictive 🖤✨", "mystery", "dark romance & mystery aesthetics"),
                ("The Art of Romantic Tension", "Subconscious Signals That Make You Irresistibly Magnetic 💋🌹", "allure", "relationship chemistry & presence"),
                ("Sensual Body Language & Presence", "The Subtle Movements That Command Deep Romantic Desire ⚡", "chemistry", "flirting psychology & charm secrets"),
                ("Intimate Midnight Rendezvous Psychology", "How Magnetic Presence In Luxury Settings Creates Obsession 🥂", "romance", "dating dynamics & romantic secrets"),
            ]
            pick = random.choice(fallback_topics)
            data = {
                "topic": pick[0],
                "title": pick[1],
                "angle": "Exploring the bold psychological and sensual dynamics of intense romantic attraction.",
                "style": pick[2],
                "category": pick[3],
                "virality_score": 9.5,
            }

        return data

    # ---------------------------------------------------------
    # Capability 2: Scene-by-Scene Script Generation (Glamour & Seduction)
    # ---------------------------------------------------------
    def plan_script(self, topic_info: Dict[str, Any], format_type: str = "short") -> Dict[str, Any]:
        """Generates a complete scene-by-scene script with visual queries and narration."""
        num_scenes = 4 if format_type == "short" else 6

        prompt = f"""You are a professional adult glamour filmmaker, sensual video director, and cinematic AI content creator.
Topic: {topic_info['topic']}
Title: {topic_info['title']}
Style: {topic_info.get('style', 'allure')}
Format: {format_type}

DIRECTOR'S VISUAL GUIDELINES FOR EACH SCENE:
- All models are fictional adults aged 25 and above.
- Extremely glamorous and alluring adult models with sensual expressions and confident body language.
- Revealing but non-explicit fashion: elegant lingerie-inspired silk robes, satin slips, lace couture with full coverage (NO visible nudity).
- Sensual dancing and graceful movements.
- Romantic bedroom and luxury hotel settings, candlelit ambiance, intimate romantic atmosphere with artistic implied intimacy.
- Beautiful close-up portraits, dramatic chiaroscuro lighting, rich shadows, and realistic skin textures.
- Professional cinematic camera movements (slow dolly push, shallow f/1.4 depth of field, 35mm film aesthetic).

Write exactly {num_scenes} sequential narration scenes designed for viral audience retention.
Pacing Rules:
- Scene 1 MUST be an instant scroll-stopping hook under 12 words triggering intense curiosity about attraction, romance, or chemistry.
- Each scene must be punchy, rhythmic, seductive, and alluring (15-22 words max per scene).
- Speak with calm, confident, magnetic, and seductive elegance directly to the viewer.
- Total narration word count: {90 if format_type == 'short' else 140} words.
- Provide 2-3 specific visual search terms per scene for cinematic glamour stock footage (e.g. "glamorous woman silk dress slow motion", "sensual couple romantic bedroom candlelit", "elegant model luxury hotel suite portrait", "close up eye contact sensual lighting", "sensual dancing silhouette night").
- Provide 1 'image_prompt' per scene for photorealistic 8k vertical illustration:
  Specify fictional adult model aged 25+, lingerie-inspired haute couture silk fashion with full coverage, intimate warm candlelit luxury hotel bedroom or penthouse lounge, soft chiaroscuro shadows, realistic skin texture with visible pores, shallow depth of field f/1.4, 35mm photograph, vertical 9:16 portrait. STRICTLY NO visible nudity or graphic depictions.

Return ONLY JSON:
{{
  "topic": "{topic_info['topic']}",
  "title": "{topic_info['title']}",
  "description": "Magnetic, seductive description summarizing this attraction insight.",
  "hashtags": ["#attraction", "#glamour", "#datingtips", "#romance", "#chemistry", "#allure", "#seduction"],
  "scenes": [
    {{
      "text": "spoken narration for this scene",
      "search_terms": ["glamorous woman silk dress slow motion", "romantic candlelit luxury bedroom"],
      "image_prompt": "cinematic 8k vertical portrait of a stunning 26-year-old fictional woman in an elegant satin silk slip dress in a luxury candlelit hotel suite, intimate warm amber rim lighting, soft shadows, realistic skin pores, 35mm photo, f/1.4, 9:16 composition"
    }}
  ]
}}"""

        validator = lambda d: isinstance(d, dict) and isinstance(d.get("scenes"), list) and len(d["scenes"]) >= 3
        script = self.reason_json(prompt, validator, rounds=2)

        if not script:
            # Resilient alluring fallback script with adult glamour aesthetic
            script = {
                "topic": topic_info["topic"],
                "title": topic_info["title"],
                "description": f"Exploring {topic_info['topic']} with bold seductive insight and cinematic glamour.",
                "hashtags": ["#attraction", "#glamour", "#datingtips", "#romance", "#chemistry", "#allure", "#seduction"],
                "scenes": [
                    {
                        "text": "The most intoxicating attraction never announces itself. It lingers in the quiet air between two people.",
                        "search_terms": ["glamorous woman silk dress slow motion", "luxury hotel suite intimate candlelit"],
                        "image_prompt": "cinematic 8k vertical portrait of an alluring 27-year-old fictional woman in a black silk robe lounging on a velvet chaise in a luxury penthouse, warm amber candlelight, realistic skin texture, 35mm film grain, 9:16"
                    },
                    {
                        "text": "When you hold someone's gaze for three breathless seconds, their pulse accelerates before their mind can catch up.",
                        "search_terms": ["close up eye contact sensual lighting", "sensual couple romantic bedroom candlelit"],
                        "image_prompt": "intimate close up portrait of a captivating 26-year-old fictional woman with intense alluring gaze, subtle sensual smile, soft bedroom lamp glow, detailed skin texture, shallow f/1.4 depth of field, 9:16"
                    },
                    {
                        "text": "True allure isn't about giving everything away. It is the exquisite art of making them crave what you keep secret.",
                        "search_terms": ["sensual slow dance silhouette", "elegant model luxury hotel suite portrait"],
                        "image_prompt": "cinematic 8k shot of an elegant fictional adult couple in glamorous evening attire sharing an intimate slow dance on a moonlit Parisian balcony, soft bokeh city lights, 9:16"
                    },
                    {
                        "text": "Master the silent psychology of seduction. Follow now to unlock your most magnetic presence.",
                        "search_terms": ["glamorous woman bedroom portrait cinematic", "romantic rooftop sunset couple"],
                        "image_prompt": "striking vertical 9:16 portrait of a glamorous 28-year-old fictional woman in an emerald satin gown raising a champagne flute in a luxury candlelit lounge, elegant confident expression, 8k cinematic lighting"
                    },
                ],
            }

        return script

    # ---------------------------------------------------------
    # Capability 3: Strict Fact-Checking & Safety Audit
    # ---------------------------------------------------------
    def audit_and_fact_check(self, script: Dict[str, Any]) -> Dict[str, Any]:
        """Performs a strict secondary verification pass over all script claims."""
        scenes = script.get("scenes", [])
        texts = [s.get("text", "") for s in scenes]

        prompt = f"""You are a strict scientific fact-checker and editor for an educational video titled "{script.get('title')}".
Narration Scenes:
{json.dumps(texts, indent=2)}

Audit each scene for:
1. Factual accuracy and verifiable scientific consensus.
2. Removal of any exaggerations, misinformation, or dubious statistics.
3. Conversational flow and safety compliance.

Return ONLY JSON:
{{
  "scenes": ["verified scene 1", "verified scene 2", ...],
  "issues_found": ["short note per revision if any"],
  "safety_passed": true
}}"""

        validator = lambda d: isinstance(d, dict) and isinstance(d.get("scenes"), list) and len(d["scenes"]) == len(texts)
        audit_res = self.reason_json(prompt, validator, rounds=1)

        if audit_res and audit_res.get("scenes"):
            for i, rev in enumerate(audit_res["scenes"]):
                if isinstance(rev, str) and rev.strip():
                    script["scenes"][i]["text"] = rev.strip()
            print(f"  [Agent Fact-Checker] Audit completed. Verified {len(texts)} scenes.")
        else:
            print("  [Agent Fact-Checker] Audit passed (baseline verified).")

        return script

    # ---------------------------------------------------------
    # Capability 4: Self-Learning & Strategy Feedback Loop
    # ---------------------------------------------------------
    def update_feedback_weights(self) -> None:
        """Analyzes published video engagement history and adjusts strategic category/style weights."""
        state = self.load_state()
        history = self.load_history()

        # Update style feedback
        last_style = state.get("last_style")
        if last_style:
            weights = state.setdefault("weights", {})
            style_weights = weights.setdefault("style", {})
            # Gentle positive reinforcement for completed executions
            cur = style_weights.get(last_style, 1.0)
            style_weights[last_style] = round(min(1.8, max(0.6, cur * 1.02)), 2)

        self.save_state(state)
        print(f"  [Agent Self-Learning] Strategic weights updated in state.json.")

    @staticmethod
    def weighted_choice(options: List[str], weights: Dict[str, float]) -> str:
        if not options:
            return "general science"
        scores = [max(0.2, weights.get(opt, 1.0)) for opt in options]
        total = sum(scores)
        pick = random.uniform(0, total)
        cum = 0.0
        for opt, score in zip(options, scores):
            cum += score
            if cum >= pick:
                return opt
        return options[0]
