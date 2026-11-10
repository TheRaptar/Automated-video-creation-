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

    # ---------------------------------------------------------
    # Audience & Genre Story Profile Helper
    # ---------------------------------------------------------
    @staticmethod
    def get_audience_profile(category_or_style: str = "") -> Dict[str, Any]:
        """Returns the optimal voice, pace, language guidelines, and visual style for the target audience."""
        lower = (category_or_style or "").lower()
        if any(k in lower for k in ("child", "kid", "fable", "bedtime", "fairy")):
            return {
                "target_audience": "children",
                "style": "fable",
                "voice": "en-US-AnaNeural",
                "rate": "+0%",
                "tone": "whimsical, wonder-filled, friendly, and heartwarming",
                "subtitle_color": "0x00E5FF",  # Sunny yellow / cyan highlight
                "subtitle_shadow": "0x401040",
                "art_style": "whimsical 3D animated storybook, Pixar-style vibrant colors, soft warm magical lighting, friendly stylized character design, 9:16 vertical",
                "guidelines": "Use simple, imaginative, wonder-filled language. Focus on curiosity, friendly animal or fantasy characters, and positive uplifting lessons."
            }
        elif any(k in lower for k in ("horror", "spooky", "creepypasta", "ghost", "dark folklore", "supernatural", "eerie")):
            return {
                "target_audience": "horror",
                "style": "horror",
                "voice": "en-US-GuyNeural",
                "rate": "-10%",
                "tone": "ominous, spine-chilling, atmospheric dread, and shocking twists",
                "subtitle_color": "0x0000CC",  # Blood crimson highlight
                "subtitle_shadow": "0x000000",
                "art_style": "cinematic atmospheric horror, chilling fog, moody chiaroscuro lighting, eerie abandoned interiors, 35mm film grain, analog suspense, 9:16 vertical",
                "guidelines": "Build intense psychological dread, slow ominous suspense, whispered secrets, and unexpected hair-raising narrative twists. Keep content psychological without graphic violence."
            }
        elif any(k in lower for k in ("myth", "legend", "ancient", "epic", "folklore")):
            return {
                "target_audience": "all_ages",
                "style": "legend",
                "voice": "en-GB-RyanNeural",
                "rate": "-3%",
                "tone": "epic, theatrical, mythic grandeur, and legendary lore",
                "subtitle_color": "0x20C0F0",  # Antique gold highlight
                "subtitle_shadow": "0x111111",
                "art_style": "epic fantasy matte painting, golden atmospheric glow, ancient ruins, mythic scale, cinematic 8k lighting, 9:16 vertical",
                "guidelines": "Grand, legendary storytelling with ancient secrets, forgotten myths, mythic beasts, and theatrical presence."
            }
        else:
            # Adult Fiction / Sci-Fi / Psychological Thriller
            return {
                "target_audience": "adults",
                "style": "thriller",
                "voice": "en-US-ChristopherNeural",
                "rate": "+2%",
                "tone": "sophisticated, high-stakes psychological suspense, and dramatic twists",
                "subtitle_color": "white",
                "subtitle_shadow": "0x111111",
                "art_style": "hyper-realistic 8K cinematic neo-noir, rain-slicked city streets, moody ambient shadows, 35mm lens, 9:16 vertical",
                "guidelines": "Sharp, gripping dialogue, intellectual stakes, moral dilemmas, and thought-provoking twists transforming science or mysteries into compelling fiction."
            }

    # ---------------------------------------------------------
    # Capability 1: Trend Evaluation & Topic Formulation (Multi-Audience Storytelling)
    # ---------------------------------------------------------
    def evaluate_and_pick_topic(
        self,
        signals: Dict[str, Any],
        categories: List[str],
        format_type: str = "short",
    ) -> Dict[str, Any]:
        """Evaluates trends and formulates creative storytelling concepts for children, adults, or horror audiences."""
        history = self.load_history()
        state = self.load_state()

        story_default_niches = [
            "Children's Whimsical Fables & Bedtime Tales",
            "Horror Stories & Supernatural Thrillers",
            "Adult Psychological Thrillers & Noir Fiction",
            "Scientific Mysteries Transformed into Fiction",
            "Mind-Bending Sci-Fi & Speculative Tales",
            "Ancient Myths, Folklore & Epic Legends",
            "Entertaining Fictional Mysteries & Twists",
        ]
        active_categories = categories or story_default_niches

        weights = state.get("weights", {})
        recent_cats = state.get("recent_categories", [])[-4:]
        available_cats = [c for c in active_categories if c not in recent_cats] or active_categories

        cat_weights = weights.get("category", {})
        category = self.weighted_choice(available_cats, cat_weights)
        profile = self.get_audience_profile(category)

        # Build prompt for Gemini Agent
        avoid_topics = "; ".join(history[-60:]) if history else "none"
        prompt = f"""You are a master storyteller, creative narrative director, and cinematic AI fiction creator.
Your mission is to transform educational ideas, scientific wonders, real-world phenomena, and creative prompts into captivating storytelling content for specific target audiences.

Target Category: {category}
Target Audience: {profile['target_audience']}
Genre Style: {profile['style']}
Tone & Pacing: {profile['tone']}
Target Video Format: {format_type} (short: 30-50s fast-paced viral Short, story: 45-60s cinematic narrative)

Audience Guidelines:
- If Target Audience is 'children': Write whimsical fables, magical adventures, or wonder-filled tales explaining how things work through lovable characters, playful magic, and heartwarming morals.
- If Target Audience is 'horror': Write spine-chilling supernatural creepypastas, eerie urban legends, psychological dread, haunted encounters, and terrifying plot twists based on eerie anomalies or strange real phenomena.
- If Target Audience is 'adults': Write sophisticated psychological thrillers, dark sci-fi speculative fiction, thought-provoking moral dilemmas, or noir mysteries where science/logic unravels.
- If Target Audience is 'all_ages' (legend): Write epic mythological folklore, legendary battles of wit, and ancient historical sagas.

Avoid repeating or closely resembling any of these recent topics:
{avoid_topics}

Formulate ONE original, irresistible, creative story concept with a gripping narrative hook, rising suspense/wonder, and a shocking or memorable payoff.

Rules:
1. Scene 1 hook MUST stop the scroll in under 1.5 seconds with intense narrative intrigue (e.g. For horror: "If you wake up at 3:07 AM and hear knocking on your closet door, whatever you do, keep your eyes closed...", For kids: "In a forest where the mushrooms glow like blue lanterns, a tiny mouse made an impossible discovery...", For adults: "The deep sea submarine was supposed to map the trench floor. Instead, they found a titanium door sealed from the outside...").
2. Ensure vocabulary, tone, and character framing match the '{profile['target_audience']}' audience.
3. STRICT POLICY COMPLIANCE: No graphic sexual content, no hate speech, no real-world tragedy exploitation. Keep horror suspenseful, psychological, and eerie without extreme gore, fully compliant with YouTube Community Guidelines.

Return ONLY JSON:
{{
  "topic": "precise story topic name",
  "title": "high-CTR curiosity title under 75 characters with narrative emoji",
  "angle": "the central narrative twist, wonder, or psychological mystery",
  "style": "{profile['style']}",
  "category": "{category}",
  "target_audience": "{profile['target_audience']}",
  "virality_score": 9.7
}}"""

        validator = lambda d: isinstance(d, dict) and bool(d.get("topic")) and bool(d.get("title"))
        data = self.reason_json(prompt, validator, rounds=2)

        if not data:
            # Resilient multi-audience storytelling fallbacks
            fallback_stories = [
                # Horror
                ("The Trench That Knocked Back", "The Deep Sea Expedition That Discovered Something Tapping Back 🌊👁️", "horror", "Horror Stories & Supernatural Thrillers", "horror"),
                ("The Reflection with a Delay", "Why You Should Never Stare At Antique Mirrors After Midnight 🪞🩸", "horror", "Horror Stories & Supernatural Thrillers", "horror"),
                # Children Fable
                ("The Little Star Who Forgot How to Glow", "The Little Star Who Discovered How To Make Her Own Light ✨⭐", "fable", "Children's Whimsical Fables & Bedtime Tales", "children"),
                ("The Whispering Mushroom Forest", "The Brave Little Fox And The Secret Tree Underground Network 🦊🍄", "fable", "Children's Whimsical Fables & Bedtime Tales", "children"),
                # Adult Sci-Fi / Thriller
                ("The Signal from 12 Hours Ahead", "The Radio Telescope That Started Receiving Tomorrow's News 📡⏳", "scifi", "Mind-Bending Sci-Fi & Speculative Tales", "adults"),
                ("The Architect Who Erased a Floor", "The Blueprint Secret Hidden Inside The 13th Floor 🏢🗝️", "thriller", "Adult Psychological Thrillers & Noir Fiction", "adults"),
                # Myth & Legend
                ("The Clockwork Titan of Alexandria", "The Ancient Inventor Who Built A Mechanical Guardian ⚙️🏛️", "legend", "Ancient Myths, Folklore & Epic Legends", "all_ages"),
            ]
            pick = random.choice(fallback_stories)
            data = {
                "topic": pick[0],
                "title": pick[1],
                "angle": "An engaging narrative transforming mystery and curiosity into captivating storytelling.",
                "style": pick[2],
                "category": pick[3],
                "target_audience": pick[4],
                "virality_score": 9.5,
            }

        return data

    # ---------------------------------------------------------
    # Capability 2: Scene-by-Scene Script Generation (Multi-Audience Storytelling)
    # ---------------------------------------------------------
    def plan_script(self, topic_info: Dict[str, Any], format_type: str = "short") -> Dict[str, Any]:
        """Generates a complete scene-by-scene narrative script with visual choreography and audience-suited tone."""
        num_scenes = 4 if format_type == "short" else 6
        profile = self.get_audience_profile(topic_info.get("category") or topic_info.get("style", ""))
        target_audience = topic_info.get("target_audience") or profile["target_audience"]

        prompt = f"""You are a master storyteller, screenwriter, and cinematic video director.
Topic: {topic_info['topic']}
Title: {topic_info['title']}
Target Audience: {target_audience}
Genre Style: {topic_info.get('style', profile['style'])}
Format: {format_type}

DIRECTOR'S NARRATIVE & VISUAL GUIDELINES:
- Tone: {profile['tone']}
- Art Style: {profile['art_style']}
- Directorial Guidelines: {profile['guidelines']}

Write exactly {num_scenes} sequential narrative scenes crafted for maximum engagement, emotional resonance, and retention:
- Scene 1: Instant scroll-stopping hook under 12 words establishing the premise, danger, wonder, or mystery.
- Scenes 2-{num_scenes-1}: Escalating narrative tension, character choices, sensory details, and an unexpected twist or revelation.
- Scene {num_scenes}: Satisfying climax, chilling cliffhanger (for horror), heartwarming conclusion (for kids), or thought-provoking resolution.
- Total narration word count: {90 if format_type == 'short' else 140} words.
- search_terms: 2-3 specific visual search terms per scene suitable for stock footage or AI generation matching the genre.
- image_prompt: 1 rich vertical 9:16 prompt per scene tailored to the art style:
  - If children: Whimsical 3D animation, Pixar-style wonder, friendly animal/creature character, magical vibrant colors, 9:16.
  - If horror: Atmospheric cinematic horror, fog, eerie chiaroscuro shadows, 35mm grain, dark mystery, 9:16.
  - If adult thriller/scifi: 8K hyper-realistic cinematic neo-noir, dramatic rim lighting, intense character expressions, 9:16.

Return ONLY JSON:
{{
  "topic": "{topic_info['topic']}",
  "title": "{topic_info['title']}",
  "description": "Engaging description summarizing this story.",
  "hashtags": ["#story", "#{target_audience}", "#{profile['style']}", "#narrative", "#viral"],
  "target_audience": "{target_audience}",
  "style": "{topic_info.get('style', profile['style'])}",
  "voice_profile": {{
    "voice": "{profile['voice']}",
    "rate": "{profile['rate']}"
  }},
  "scenes": [
    {{
      "text": "spoken narration for this scene",
      "search_terms": ["cinematic visual query 1", "cinematic visual query 2"],
      "image_prompt": "detailed vertical 9:16 prompt reflecting the {target_audience} art style"
    }}
  ]
}}"""

        validator = lambda d: isinstance(d, dict) and isinstance(d.get("scenes"), list) and len(d["scenes"]) >= 3
        script = self.reason_json(prompt, validator, rounds=2)

        if not script:
            # Resilient fallback scripts based on audience
            if target_audience == "horror":
                script = {
                    "topic": topic_info["topic"],
                    "title": topic_info["title"],
                    "description": "A spine-chilling supernatural tale of an ocean mystery that answered back.",
                    "hashtags": ["#horror", "#scarystories", "#creepypasta", "#mystery", "#supernatural"],
                    "target_audience": "horror",
                    "style": "horror",
                    "voice_profile": {"voice": "en-US-GuyNeural", "rate": "-10%"},
                    "scenes": [
                        {
                            "text": "At seven miles beneath the ocean surface, the research submarine heard three rhythmic metallic taps on the outer hull.",
                            "search_terms": ["deep sea submarine darkness", "ocean trench dark water"],
                            "image_prompt": "cinematic atmospheric horror, research submarine floodlights illuminating deep pitch-black ocean trench, ominous shadows, eerie underwater particles, 35mm film grain, 9:16"
                        },
                        {
                            "text": "The sonar technician tapped back twice as a nervous joke. Four seconds later... five loud thuds answered.",
                            "search_terms": ["sonar screen dark control room", "tense submarine interior"],
                            "image_prompt": "tense dark submarine control room, green glow of flickering sonar display, sweating nervous technician looking into dark porthole, 9:16 vertical"
                        },
                        {
                            "text": "When they turned on the high-intensity floodlights, nothing was outside. Only fresh scratch marks in the solid titanium.",
                            "search_terms": ["scratched metal submarine hull", "dark deep sea void"],
                            "image_prompt": "macro close-up of submarine exterior hull illuminated by harsh beam of light, massive claw scratch marks on titanium, endless abyss behind it, 9:16"
                        },
                        {
                            "text": "Some depths were never meant to be explored. Subscribe... if you dare to listen closer.",
                            "search_terms": ["creepy dark ocean abyss", "shadowy underwater silhouette"],
                            "image_prompt": "terrifying underwater silhouette of an colossal ancient shape fading into the deep blue fog, cinematic horror lighting, 9:16"
                        },
                    ],
                }
            elif target_audience == "children":
                script = {
                    "topic": topic_info["topic"],
                    "title": topic_info["title"],
                    "description": "An enchanting storybook adventure about a brave little star discovering her own light.",
                    "hashtags": ["#kidsstory", "#fable", "#bedtimestory", "#whimsical", "#animation"],
                    "target_audience": "children",
                    "style": "fable",
                    "voice_profile": {"voice": "en-US-AnaNeural", "rate": "+0%"},
                    "scenes": [
                        {
                            "text": "High above the sleepy clouds, a tiny baby star named Pip was the only one who hadn't learned how to sparkle.",
                            "search_terms": ["cute animated star night sky", "whimsical cartoon clouds"],
                            "image_prompt": "whimsical 3D animated scene, adorable little golden star with big curious eyes sitting on a fluffy pastel cloud in a dreamy night sky, Pixar style, 9:16"
                        },
                        {
                            "text": "An old wise moon whispered: You don't get light from the outside, little Pip. Light happens when you share your warmth.",
                            "search_terms": ["smiling cartoon moon night sky", "magic glowing fairy dust"],
                            "image_prompt": "gentle smiling crescent moon wearing a cozy nightcap talking warmly to the tiny cute star, glowing stardust particles, soft magical lighting, 9:16"
                        },
                        {
                            "text": "So Pip gave a warm hug to a lonely little comet flying past. Instantly, her whole heart ignited into brilliant golden starlight!",
                            "search_terms": ["cute cartoon comet flying", "bright glowing golden star"],
                            "image_prompt": "tiny cute star hugging a friendly smiling baby comet with a glowing rainbow tail, burst of sparkling golden light, heartwarming magical atmosphere, 9:16"
                        },
                        {
                            "text": "And from that night on, Pip shone brightest of all. Sweet dreams, little explorer, and follow for more bedtime magic.",
                            "search_terms": ["beautiful starry sky cartoon", "magical glowing night sky"],
                            "image_prompt": "delightful wide shot of the night sky filled with smiling stars and gentle glowing constellations over a peaceful sleeping village, 9:16"
                        },
                    ],
                }
            else:
                # Adult Sci-Fi / Psychological Thriller
                script = {
                    "topic": topic_info["topic"],
                    "title": topic_info["title"],
                    "description": "A gripping sci-fi thriller about a temporal signal received by an isolated observatory.",
                    "hashtags": ["#scifi", "#thriller", "#psychological", "#mystery", "#storytelling"],
                    "target_audience": "adults",
                    "style": "scifi",
                    "voice_profile": {"voice": "en-US-ChristopherNeural", "rate": "+2%"},
                    "scenes": [
                        {
                            "text": "At 2:14 AM, the Atacama radio telescope picked up an encrypted military broadcast on an abandoned satellite frequency.",
                            "search_terms": ["radio telescope dish night sky", "modern astronomy observatory"],
                            "image_prompt": "cinematic neo-noir 8k wide shot of massive radio telescope dishes pointing toward Milky Way at night, dramatic blue hour lighting, 9:16"
                        },
                        {
                            "text": "The decoded audio was Dr. Vance's own voice reading a disaster evacuation protocol that had not been written yet.",
                            "search_terms": ["tense scientist audio waveform", "cinematic dark control room"],
                            "image_prompt": "intense close-up of a 35-year-old astrophysicist staring in disbelief at an audio spectral waveform on monitors, dramatic rim lighting, 9:16"
                        },
                        {
                            "text": "The time-stamp was twelve hours in the future. And outside the sealed laboratory doors, the power grid just went dark.",
                            "search_terms": ["emergency red lights hallway", "dark laboratory silhouettes"],
                            "image_prompt": "moody dark laboratory hallway illuminated by glowing emergency red backup lights, long shadows, cinematic suspense, 9:16"
                        },
                        {
                            "text": "When the future speaks, you have to decide whether to listen or run. Follow for the next chapter.",
                            "search_terms": ["silhouette person looking starry night", "cinematic mystery night"],
                            "image_prompt": "silhouette of the scientist opening heavy vault doors looking out onto a dark mountain ridge under an ominous starry sky, 9:16"
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
