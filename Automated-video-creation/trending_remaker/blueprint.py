"""
Original Remake Blueprint Extractor.

Transforms a high-velocity `ViralSignal` into a 100% ORIGINAL creative blueprint
(fresh title angle, hook archetype, narrative pacing, visual stock keywords,
and recommended format) — never copying source scripts or copyrighted footage.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

import requests

from .scanner import ViralSignal

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "your", "into", "about",
    "what", "when", "where", "which", "while", "official", "video", "shorts", "reel",
    "full", "movie", "episode", "live", "watch", "new", "2025", "2026", "2027",
    "viral", "trending", "hd", "4k", "ft", "feat", "vs",
}


@dataclass
class RemakeBlueprint:
    source_signal_id: str
    source_title: str
    source_provider: str
    source_url: str
    source_viral_score: float
    hook_archetype: str
    original_topic: str
    original_title: str
    opening_hook_line: str
    recommended_format: str      # short | story | animated | long
    recommended_aspect: str      # 9:16 | 16:9 | 1:1
    style: str
    visual_keywords: List[str] = field(default_factory=list)
    seo_tags: List[str] = field(default_factory=list)
    angle_rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def detect_hook_archetype(title: str) -> str:
    low = (title or "").lower()
    if re.search(r"\b(\d+|top \d+|best \d+|ways|facts|secrets)\b", low):
        return "number_countdown"
    if any(k in low for k in ("why ", "how ", "explained", "science", "behind")):
        return "how_it_actually_works"
    if any(k in low for k in ("vs", "versus", "compared", "difference")):
        return "shocking_comparison"
    if any(k in low for k in ("never ", "stop ", "don't", "mistake", "lie", "truth")):
        return "contrarian_truth"
    if any(k in low for k in ("story", "happened", "survived", "journey", "day in")):
        return "story_twist"
    return "curiosity_gap"


def _extract_clean_subject(title: str) -> str:
    cleaned = re.sub(r"#\w+", "", title or "")
    cleaned = re.sub(r"[\[\(\{][^\]\)\}]{0,40}[\]\)\}]", "", cleaned)
    cleaned = re.sub(r"\s*[|•—–-]\s*.*$", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" :!?.,-")
    return cleaned[:85] or "Hidden World Breakthrough"


def _extract_visual_keywords(signal: ViralSignal, subject: str) -> List[str]:
    words = re.findall(r"[A-Za-z]{4,}", f"{subject} {' '.join(signal.tags[:6])} {signal.category}")
    uniq: List[str] = []
    for w in words:
        lw = w.lower()
        if lw in STOPWORDS or lw in uniq:
            continue
        uniq.append(lw)
        if len(uniq) >= 5:
            break
    if not uniq:
        return ["cinematic", "nature", "storytelling"]
    return uniq


def _llm_original_angle(
    signal: ViralSignal,
    subject: str,
    archetype: str,
    language: str,
    http_post: Optional[Callable[..., Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Optional Gemini/Groq angle generator; falls back deterministically if keys are absent."""
    gem_key = os.environ.get("GEMINI_API_KEY", "").strip()
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not (gem_key or groq_key):
        return None

    prompt = (
        "You are an original short-form video strategist. Given a trending topic signal, "
        "propose a 100% ORIGINAL educational/storytelling video angle (NEVER copy the source title verbatim). "
        f"Source topic hint: {subject}\n"
        f"Category: {signal.category}\n"
        f"Hook archetype: {archetype}\n"
        f"Language: {language}\n"
        "Return strict JSON ONLY with keys: "
        '{"original_topic": "...", "original_title": "...", "opening_hook_line": "...", '
        '"visual_keywords": ["k1", "k2", "k3"], "angle_rationale": "..."}'
    )
    poster = http_post or requests.post

    if gem_key:
        try:
            model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gem_key}"
            r = poster(
                url,
                json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}},
                timeout=20,
            )
            if getattr(r, "ok", False):
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(txt)
        except Exception:
            pass

    if groq_key:
        try:
            r = poster(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}"},
                json={
                    "model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                },
                timeout=20,
            )
            if getattr(r, "ok", False):
                return json.loads(r.json()["choices"][0]["message"]["content"])
        except Exception:
            pass
    return None


def build_remake_blueprint(
    signal: ViralSignal,
    fmt: str = "auto",
    aspect: str = "auto",
    language: str = "en",
    style: str = "story",
    offline: bool = False,
    http_post: Optional[Callable[..., Any]] = None,
) -> RemakeBlueprint:
    """Builds a 100% original creative remake blueprint from a ranked ViralSignal."""
    subject = _extract_clean_subject(signal.title)
    archetype = detect_hook_archetype(signal.title)
    vis_kw = _extract_visual_keywords(signal, subject)

    eff_fmt = fmt if fmt in ("short", "story", "animated", "long") else ("short" if signal.is_short_form else "story")
    eff_aspect = aspect if aspect in ("9:16", "16:9", "1:1") else ("16:9" if eff_fmt == "long" else "9:16")

    llm_data = None if offline else _llm_original_angle(signal, subject, archetype, language, http_post=http_post)

    if llm_data and llm_data.get("original_topic"):
        orig_topic = str(llm_data["original_topic"]).strip()[:110]
        orig_title = str(llm_data.get("original_title") or orig_topic).strip()[:90]
        hook_line = str(llm_data.get("opening_hook_line") or f"Here is the surprising story behind {subject}.").strip()
        if isinstance(llm_data.get("visual_keywords"), list) and llm_data["visual_keywords"]:
            vis_kw = [str(k).strip().lower() for k in llm_data["visual_keywords"] if str(k).strip()][:5]
        rationale = str(llm_data.get("angle_rationale") or f"Original {archetype} remake inspired by trending velocity.")
    else:
        templates = {
            "number_countdown": (
                f"3 Surprising Facts Behind {subject}",
                f"3 Surprising Facts About {subject} Most People Miss",
                f"Everyone is talking about {subject}—but almost nobody noticed these 3 hidden details.",
            ),
            "how_it_actually_works": (
                f"How {subject} Actually Works Explained Simply",
                f"The Real Mechanism Behind {subject}",
                f"Wait until you see what is actually happening behind {subject}.",
            ),
            "shocking_comparison": (
                f"The Untold Comparison Behind {subject}",
                f"{subject}: What Changes When You Look Closer",
                f"Most people see only the headline of {subject}—here is the real contrast.",
            ),
            "contrarian_truth": (
                f"What Everyone Gets Wrong About {subject}",
                f"The Overlooked Truth About {subject}",
                f"Stop scrolling—almost everyone misunderstood this one crucial detail about {subject}.",
            ),
            "story_twist": (
                f"The Untold Story Behind {subject}",
                f"How {subject} Changed Everything Overnight",
                f"Nobody expected how the story behind {subject} would unfold.",
            ),
            "curiosity_gap": (
                f"The Hidden Story Behind {subject}",
                f"Why {subject} Is Capturing Everyone's Attention",
                f"There is one fascinating reason why {subject} exploded everywhere this week.",
            ),
        }
        orig_topic, orig_title, hook_line = templates.get(archetype, templates["curiosity_gap"])
        rationale = f"Original {archetype} angle derived from {signal.source} velocity ({signal.views_per_hour:.0f} views/hr)."

    # Ensure we NEVER copy the source title verbatim
    if orig_title.strip().lower() == signal.title.strip().lower():
        orig_title = f"Explained: {orig_title}"[:90]

    seo_tags = list(dict.fromkeys(vis_kw + [t.lower() for t in signal.tags[:6]] + ["explained", "story"]))[:12]

    return RemakeBlueprint(
        source_signal_id=signal.signal_id,
        source_title=signal.title,
        source_provider=signal.source,
        source_url=signal.source_url,
        source_viral_score=signal.viral_score,
        hook_archetype=archetype,
        original_topic=orig_topic,
        original_title=orig_title,
        opening_hook_line=hook_line,
        recommended_format=eff_fmt,
        recommended_aspect=eff_aspect,
        style=style,
        visual_keywords=vis_kw,
        seo_tags=seo_tags,
        angle_rationale=rationale,
    )
