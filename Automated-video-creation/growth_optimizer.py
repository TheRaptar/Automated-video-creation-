#!/usr/bin/env python3
"""
Growth, Retention, Audience Routing, Peak-Frame Cover & Platform-Native SEO Engine.

Designed to maximize YouTube (Shorts & Long-form) and Instagram Reels views, watch time,
likes, comments, saves, and shares while preserving all 7 daily slots, all 7 rotating
languages, and multi-genre variety.
"""

from __future__ import annotations

import math
import os
import random
import re
import subprocess
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 1. Timezone-Aligned 7-Slot Language & Regional Trend Routing
#    Maps each of the 7 existing daily UTC cron windows to the language whose
#    native audience is actively scrolling at peak hours (with India IST &
#    Global English US/India overlap prioritized on key slots).
# ---------------------------------------------------------------------------
SLOT_ROUTING: List[Dict[str, Any]] = [
    {
        "slot": 1,
        "hours": (0, 1, 2),
        "lang": "es",
        "peak_label": "LatAm / US Hispanic Evening (7-8 PM CST/EST)",
        "geos": ["MX", "ES", "US"],
    },
    {
        "slot": 2,
        "hours": (3, 4, 5, 6),
        "lang": "ja",
        "peak_label": "Japan Lunch Peak (1:30 PM JST)",
        "geos": ["JP"],
    },
    {
        "slot": 3,
        "hours": (7, 8, 9),
        "lang": "en",
        "peak_label": "India Lunch (1:30 PM IST) + UK/Europe Morning",
        "geos": ["IN", "US", "GB"],
    },
    {
        "slot": 4,
        "hours": (10, 11, 12, 13),
        "lang": "ta",
        "peak_label": "India After-Work / Tamil Nadu Evening (5:00 PM IST)",
        "geos": ["IN"],
    },
    {
        "slot": 5,
        "hours": (14, 15, 16),
        "lang": "hi",
        "peak_label": "India Hindi Prime Evening (8:30 PM IST)",
        "geos": ["IN"],
    },
    {
        "slot": 6,
        "hours": (17, 18, 19, 20),
        "lang": "fr",
        "peak_label": "France / Europe Prime Evening (7:30 PM CET)",
        "geos": ["FR"],
    },
    {
        "slot": 7,
        "hours": (21, 22, 23),
        "lang": "pt",
        "peak_label": "Brazil Prime Evening (7:00 PM BRT) + US East Evening",
        "geos": ["BR", "US"],
    },
]

LANG_GEO_MAP: Dict[str, List[str]] = {
    "en": ["IN", "US", "GB"],
    "ta": ["IN"],
    "hi": ["IN"],
    "es": ["MX", "ES", "US"],
    "fr": ["FR"],
    "pt": ["BR", "US"],
    "ja": ["JP"],
    "de": ["DE"],
    "ko": ["KR"],
    "ar": ["AE", "SA"],
    "id": ["ID"],
}

SUPPORTED_ROTATION_LANGS = ["en", "ta", "hi", "es", "fr", "pt", "ja"]


def get_slot_info(utc_hour: Optional[int] = None) -> Dict[str, Any]:
    """Returns the prime-time slot routing entry for a given UTC hour (0-23)."""
    hour = datetime.now(timezone.utc).hour if utc_hour is None else int(utc_hour) % 24
    for entry in SLOT_ROUTING:
        if hour in entry["hours"]:
            return dict(entry)
    return dict(SLOT_ROUTING[2])


def resolve_slot_language(
    lang_spec: Optional[str] = None,
    state: Optional[Dict[str, Any]] = None,
    utc_hour: Optional[int] = None,
    supported_langs: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Timezone-aware language resolver that preserves all 7 languages while aligning
    each daily cron slot to its audience's local peak viewing window.

    - Explicit language (e.g., 'ta', 'en') -> returned directly.
    - Comma-separated pool (e.g., 'en,ta,hi') -> round-robins across that pool.
    - 'auto' -> picks the prime-time language for the current UTC slot. If invoked
      twice in the exact same UTC hour (e.g., manual back-to-back test), advances
      to the next language in the 7-language pool so consecutive runs still vary.
    """
    valid_set = set(supported_langs.keys()) if supported_langs else set(LANG_GEO_MAP.keys())
    raw = (lang_spec or os.environ.get("TARGET_LANGUAGE", "en")).strip().lower()
    if not raw:
        return "en"
    if raw == "auto":
        slot = get_slot_info(utc_hour=utc_hour)
        chosen = slot["lang"]
        if isinstance(state, dict):
            now_key = (
                f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-s{slot['slot']}"
                if utc_hour is None
                else f"explicit-h{int(utc_hour) % 24}"
            )
            if utc_hour is None and state.get("last_lang_slot") == now_key:
                idx = (SUPPORTED_ROTATION_LANGS.index(chosen) + int(state.get("lang_index", 0)) + 1) % len(SUPPORTED_ROTATION_LANGS)
                chosen = SUPPORTED_ROTATION_LANGS[idx]
            state["last_lang_slot"] = now_key
            state["lang_index"] = (SUPPORTED_ROTATION_LANGS.index(chosen) + 1) % len(SUPPORTED_ROTATION_LANGS)
        return chosen if chosen in valid_set else "en"
    if "," in raw:
        pool = [c.strip() for c in raw.split(",") if c.strip() in valid_set] or ["en"]
        idx = int((state or {}).get("lang_index", 0))
        chosen = pool[idx % len(pool)]
        if isinstance(state, dict):
            state["lang_index"] = (idx + 1) % len(pool)
        return chosen
    return raw if raw in valid_set else "en"


def geos_for_language(lang: str) -> List[str]:
    """Returns region-matched Google Trends / News geo codes for a target language."""
    return list(LANG_GEO_MAP.get((lang or "en").strip().lower(), ["IN", "US", "GB"]))


# ---------------------------------------------------------------------------
# 2. Retention Hook Archetypes & Exploration-Exploitation Bandit Selector
# ---------------------------------------------------------------------------
HOOK_ARCHETYPES: Dict[str, Dict[str, str]] = {
    "contradiction": {
        "label": "Contradiction / Pattern Interrupt",
        "instruction": "Open with a surprising contradiction that flips a common belief in under 9 words.",
    },
    "secret_reveal": {
        "label": "Hidden Secret / Untold Detail",
        "instruction": "Open by revealing a little-known secret or hidden detail nobody notices in under 9 words.",
    },
    "what_if": {
        "label": "High-Stakes What-If",
        "instruction": "Open with a vivid high-stakes 'What if...' visual dilemma in under 9 words.",
    },
    "countdown_twist": {
        "label": "Urgent Stakes / Twist Tease",
        "instruction": "Open at the exact moment of peak tension with a twist teased for the ending in under 9 words.",
    },
    "relatable_dilemma": {
        "label": "Relatable Choice / Moral Test",
        "instruction": "Open by placing the viewer directly inside a funny or tense choice in under 9 words.",
    },
}


def duration_bucket_for(seconds: float) -> str:
    """Categorizes rendered video duration for bandit performance tracking."""
    s = float(seconds or 0.0)
    if s <= 0:
        return "short_30_45"
    if s < 28:
        return "ultra_short_under_28"
    if s <= 45:
        return "short_28_45"
    if s <= 75:
        return "short_46_75"
    return "long_form"


def select_bandit_choice(
    options: List[str],
    weights: Optional[Dict[str, float]] = None,
    explore_rate: float = 0.25,
    rng: Optional[random.Random] = None,
) -> str:
    """
    75/25 Exploration-Exploitation selector:
    - With probability `explore_rate` (default 25%), samples uniformly to keep multi-genre
      variety fresh and discover new breakout patterns.
    - Otherwise (75%), samples proportionally to learned engagement weights.
    """
    if not options:
        return ""
    r = rng or random
    if len(options) == 1:
        return options[0]
    w_map = weights or {}
    if not w_map or r.random() < max(0.0, min(1.0, explore_rate)):
        return r.choice(options)
    w_vals = [max(0.2, float(w_map.get(opt, 1.0))) for opt in options]
    return r.choices(options, weights=w_vals, k=1)[0]


def pick_hook_archetype(state: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, str]]:
    """Selects a retention hook archetype using learned hook_type bandit weights."""
    hook_weights = ((state or {}).get("weights") or {}).get("hook_type") or {}
    last_hook = (state or {}).get("last_hook_type")
    candidates = [k for k in HOOK_ARCHETYPES if k != last_hook] or list(HOOK_ARCHETYPES)
    key = select_bandit_choice(candidates, hook_weights, explore_rate=0.25)
    return key, HOOK_ARCHETYPES[key]


# ---------------------------------------------------------------------------
# 3. Multi-Genre Micro-Series Registry & Localized Debate CTAs
#    Organizes broad variety into recognizable series + correct YouTube categories
#    + localized comment-triggering CTAs (driving comments, saves & shares).
# ---------------------------------------------------------------------------
GENRE_SERIES_MAP: Dict[str, Dict[str, Any]] = {
    "animated_myth": {
        "series_name": "Mythic Legends 3D",
        "series_tag": "#MythicLegends3D",
        "yt_category_id": "1",   # Film & Animation
        "niche_tags": ["#3DAnimation", "#MythologyStories", "#AnimatedFables"],
        "bgm_genre": "fantasy",
        "hook_sfx": "sparkle",
    },
    "animated_comedy": {
        "series_name": "Toon Buddy Chaos",
        "series_tag": "#ToonBuddyChaos",
        "yt_category_id": "1",   # Film & Animation
        "niche_tags": ["#3DCartoon", "#AnimatedComedy", "#FunnyAnimation"],
        "bgm_genre": "comedy",
        "hook_sfx": "whoosh",
    },
    "animated_anime": {
        "series_name": "Anime Folklore Chronicles",
        "series_tag": "#AnimeChronicles",
        "yt_category_id": "1",   # Film & Animation
        "niche_tags": ["#AnimeShorts", "#AnimeStory", "#FantasyAnime"],
        "bgm_genre": "action",
        "hook_sfx": "whoosh",
    },
    "horror": {
        "series_name": "Midnight Spine-Chillers",
        "series_tag": "#MidnightChillers",
        "yt_category_id": "24",  # Entertainment
        "niche_tags": ["#HorrorStories", "#ScaryShorts", "#CreepyTales"],
        "bgm_genre": "horror",
        "hook_sfx": "shock_hit",
    },
    "thriller": {
        "series_name": "60-Second Mind Twists",
        "series_tag": "#MindTwists",
        "yt_category_id": "24",
        "niche_tags": ["#ThrillerShorts", "#PlotTwist", "#MysteryStory"],
        "bgm_genre": "horror",
        "hook_sfx": "shock_hit",
    },
    "mystery": {
        "series_name": "Unsolved Enigma Files",
        "series_tag": "#EnigmaFiles",
        "yt_category_id": "24",
        "niche_tags": ["#MysteryShorts", "#PlotTwist", "#StoryTime"],
        "bgm_genre": "horror",
        "hook_sfx": "whoosh",
    },
    "fable": {
        "series_name": "Wonder Bedtime Tales",
        "series_tag": "#WonderTales",
        "yt_category_id": "1",
        "niche_tags": ["#MoralStories", "#KidsAnimation", "#BedtimeStories"],
        "bgm_genre": "kids",
        "hook_sfx": "sparkle",
    },
    "scifi": {
        "series_name": "Future Paradox Shorts",
        "series_tag": "#FutureParadox",
        "yt_category_id": "28",  # Science & Technology
        "niche_tags": ["#SciFiShorts", "#TimeParadox", "#SpaceMystery"],
        "bgm_genre": "scifi",
        "hook_sfx": "whoosh",
    },
    "legend": {
        "series_name": "Forgotten Epics",
        "series_tag": "#ForgottenEpics",
        "yt_category_id": "27",  # Education
        "niche_tags": ["#AncientHistory", "#EpicLegends", "#HistoryStories"],
        "bgm_genre": "fantasy",
        "hook_sfx": "impact_boom",
    },
    "fitness_glamour": {
        "series_name": "Daily Glow Routine",
        "series_tag": "#DailyGlowRoutine",
        "yt_category_id": "26",  # Howto & Style
        "niche_tags": ["#MorningRoutine", "#FitnessMotivation", "#AestheticLifestyle"],
        "bgm_genre": "comedy",
        "hook_sfx": "whoosh",
    },
    "fact": {
        "series_name": "Mind-Blowing Reality",
        "series_tag": "#MindBlowingFacts",
        "yt_category_id": "28",
        "niche_tags": ["#ScienceFacts", "#DidYouKnow", "#ExplainItFast"],
        "bgm_genre": "scifi",
        "hook_sfx": "shock_hit",
    },
    "story": {
        "series_name": "Micro-Cinema Stories",
        "series_tag": "#MicroCinema",
        "yt_category_id": "1",
        "niche_tags": ["#AnimatedStory", "#ShortStory", "#VisualStorytelling"],
        "bgm_genre": "fantasy",
        "hook_sfx": "whoosh",
    },
}

LOCALIZED_DEBATE_CTAS: Dict[str, List[str]] = {
    "en": [
        "Did you see that ending coming? Comment YES or NO — save this for later!",
        "What would you have done in this moment? Drop your answer below!",
        "Rate this twist from 1 to 10 in the comments and send it to a friend!",
    ],
    "ta": [
        "இந்த திருப்பத்தை நீங்கள் எதிர்பார்த்தீர்களா? கமெண்டில் சொல்லுங்கள் & நண்பர்களுக்கு பகிருங்கள்!",
        "நீங்கள் இந்த இடத்தில் இருந்தால் என்ன செய்வீர்கள்? கீழே கமெண்ட் செய்யுங்கள்!",
    ],
    "hi": [
        "क्या आपने इस अंत की उम्मीद की थी? कमेंट में हाँ या ना लिखें और दोस्तों को भेजें!",
        "इस जगह आप होते तो क्या करते? नीचे कमेंट में बताएं और वीडियो सेव करें!",
    ],
    "es": [
        "¿Te esperabas este final? Comenta SÍ o NO y compártelo con un amigo.",
        "¿Qué habrías hecho tú en su lugar? Déjalo en los comentarios y guarda este video.",
    ],
    "fr": [
        "Aviez-vous deviné cette fin ? Dites OUI ou NON en commentaire et enregistrez la vidéo !",
        "Qu'auriez-vous fait à sa place ? Répondez en commentaire !",
    ],
    "pt": [
        "Você esperava esse final? Comente SIM ou NÃO e envie para um amigo!",
        "O que você faria nessa situação? Responda nos comentários e salve o vídeo!",
    ],
    "ja": [
        "この結末、予想できましたか？コメントで教えて＆保存してね！",
        "あなたならどうしますか？コメント欄で教えてください！",
    ],
}

SPAM_TAGS = {
    "viral", "reels", "reel", "fyp", "foryou", "foryoupage", "trending",
    "explore", "explorepage", "instagood", "video", "shorts", "short",
    "aianimation", "ai", "bot",
}


def get_series_profile(style: str = "", category: str = "") -> Dict[str, Any]:
    """Returns consistent series branding, YouTube category ID, and audio mood."""
    key = (style or "").strip().lower()
    if key in GENRE_SERIES_MAP:
        return dict(GENRE_SERIES_MAP[key])
    cat_l = (category or "").lower()
    if any(k in cat_l for k in ("space", "science", "tech", "record", "fact")):
        return dict(GENRE_SERIES_MAP["fact"])
    if any(k in cat_l for k in ("horror", "ghost", "creepy")):
        return dict(GENRE_SERIES_MAP["horror"])
    if any(k in cat_l for k in ("comedy", "cartoon", "funny")):
        return dict(GENRE_SERIES_MAP["animated_comedy"])
    if any(k in cat_l for k in ("myth", "epic", "legend")):
        return dict(GENRE_SERIES_MAP["animated_myth"])
    if any(k in cat_l for k in ("kid", "fable", "bedtime", "children")):
        return dict(GENRE_SERIES_MAP["fable"])
    if any(k in cat_l for k in ("fitness", "routine", "glamour")):
        return dict(GENRE_SERIES_MAP["fitness_glamour"])
    return dict(GENRE_SERIES_MAP["story"])


def localized_engagement_cta(lang: str = "en", topic: str = "") -> str:
    """Returns a comment/save/share-driving debate prompt in the target language."""
    pool = LOCALIZED_DEBATE_CTAS.get((lang or "en").lower(), LOCALIZED_DEBATE_CTAS["en"])
    idx = sum(ord(c) for c in (topic or "story")) % len(pool)
    return pool[idx]


# ---------------------------------------------------------------------------
# 4. Platform-Native SEO & Hashtag Packager (YouTube vs. Instagram)
# ---------------------------------------------------------------------------
def _to_hashtag(raw: str) -> str:
    cleaned = re.sub(r"[^\w\u0080-\uffff]", "", str(raw or "").strip().lstrip("#"))
    return f"#{cleaned}" if len(cleaned) >= 2 else ""


def _topic_keywords_to_tags(topic: str, title: str, limit: int = 3) -> List[str]:
    """Extracts clean, topic-specific CamelCase hashtags from topic & title."""
    stop = {
        "the", "and", "for", "that", "with", "this", "from", "into", "about",
        "what", "when", "where", "who", "why", "how", "your", "their", "they",
        "was", "were", "are", "you", "our", "not", "but", "all", "one", "two",
    }
    words = re.findall(r"[A-Za-z0-9]{3,}", f"{topic} {title}")
    kept = [w for w in words if w.lower() not in stop]
    out: List[str] = []
    if len(kept) >= 2:
        pair = f"#{kept[0].capitalize()}{kept[1].capitalize()}"
        if pair[1:].lower() not in SPAM_TAGS:
            out.append(pair)
    for w in kept:
        tag = f"#{w.capitalize()}"
        if tag[1:].lower() not in SPAM_TAGS and tag.lower() not in {x.lower() for x in out}:
            out.append(tag)
        if len(out) >= limit:
            break
    return out


def clean_niche_hashtags(
    raw_tags: List[str],
    topic: str,
    title: str,
    style: str,
    category: str,
    lang: str,
    max_tags: int = 5,
) -> List[str]:
    """
    Builds 3-5 focused niche hashtags aligned with modern Instagram & YouTube SEO:
    - Strips generic low-signal spam tags (#viral, #reels, #fyp, #Shorts).
    - Combines: 1 series tag + 1-2 topic-specific tags + 1 genre tag + 1 language tag.
    """
    series = get_series_profile(style, category)
    lang_tag_map = {
        "en": "#EnglishStories",
        "ta": "#TamilStories",
        "hi": "#HindiStories",
        "es": "#HistoriasCortas",
        "fr": "#HistoiresCourtes",
        "pt": "#HistoriasCurtas",
        "ja": "#ショートアニメ",
    }
    candidates: List[str] = []
    # 1. Topic-specific tags first (highest search relevance)
    candidates.extend(_topic_keywords_to_tags(topic, title, limit=2))
    # 2. Clean raw script hashtags (filtering out spam)
    for rt in (raw_tags or []):
        ht = _to_hashtag(rt)
        if ht and ht[1:].lower() not in SPAM_TAGS:
            candidates.append(ht)
    # 3. Genre & series tags
    candidates.extend(series["niche_tags"][:2])
    candidates.append(series["series_tag"])
    if lang in lang_tag_map:
        candidates.append(lang_tag_map[lang])

    deduped: List[str] = []
    seen = set()
    for c in candidates:
        low = c.lower()
        if low not in seen and c[1:].lower() not in SPAM_TAGS:
            seen.add(low)
            deduped.append(c)
        if len(deduped) >= max_tags:
            break
    return deduped


def extract_thumbnail_hook_words(title: str, hook_text: str = "") -> str:
    """
    Produces a bold 3-4 word curiosity phrase for thumbnails instead of duplicating
    the full video title (higher mobile CTR).
    """
    source = (hook_text or title or "WATCH THIS").strip()
    clean = re.sub(r"[^\w\s!?\-\u0080-\uffff]", "", source).strip()
    words = clean.split()
    if len(words) <= 4:
        return " ".join(words).upper() if clean.isascii() else " ".join(words)
    # Prefer the punchiest 4 words (ending on a strong word or punctuation)
    short = " ".join(words[:4]).rstrip(",.:;")
    return short.upper() if short.isascii() else short


def build_platform_seo(
    script: Dict[str, Any],
    fmt: str = "short",
    chapters: Optional[List[Tuple[float, str]]] = None,
    thumb_offset_ms: int = 1800,
    hook_type: str = "contradiction",
) -> Dict[str, Any]:
    """
    Generates distinct, platform-optimized SEO packages for YouTube and Instagram:
    - Removes generic bot watermarks and low-signal #viral/#reels spam.
    - Adds search-indexed descriptions, localized debate CTAs, dynamic YouTube
      categoryId, playlist names, and Instagram 4-5 niche hashtag sets.
    """
    lang = str(script.get("language") or "en").lower()
    style = str(script.get("style") or "story")
    category = str(script.get("category") or "")
    topic = str(script.get("topic") or "").strip()
    raw_title = str(script.get("title") or topic or "Untitled Story").strip()
    # Strip trailing #Shorts/#viral from raw title so we format cleanly per platform
    clean_title = re.sub(r"\s*#(shorts|viral|reels|fyp)\b", "", raw_title, flags=re.I).strip()
    base_desc = str(script.get("description") or "").strip()
    scenes = script.get("scenes") or []
    hook_line = str(scenes[0].get("text", "") if scenes else "").strip()
    series = get_series_profile(style, category)
    cta = str(script.get("engagement_cta") or "").strip() or localized_engagement_cta(lang, topic)

    niche_tags = clean_niche_hashtags(
        script.get("hashtags") or [],
        topic=topic,
        title=clean_title,
        style=style,
        category=category,
        lang=lang,
        max_tags=5,
    )

    is_short = fmt in ("short", "story", "animated")

    # --- YouTube SEO Package ---
    if is_short:
        yt_title = (clean_title[:58].rstrip() + " #Shorts").strip()
        yt_footer_tags = " ".join(["#Shorts"] + niche_tags[:2])
    else:
        yt_title = clean_title[:95].strip()
        yt_footer_tags = " ".join(niche_tags[:3])

    yt_desc_parts = []
    if base_desc:
        yt_desc_parts.append(base_desc)
    elif hook_line:
        yt_desc_parts.append(hook_line)
    if topic and topic.lower() not in (base_desc or "").lower():
        yt_desc_parts.append(f"{series['series_name']} — {topic}.")
    yt_desc_parts.append(cta)
    if fmt == "long" and chapters and len(chapters) >= 3 and chapters[0][0] == 0:
        chap_lines = []
        for t, h in chapters:
            m, s = divmod(int(t), 60)
            chap_lines.append(f"{m:02d}:{s:02d} {h}")
        yt_desc_parts.append("Chapters:\n" + "\n".join(chap_lines))
    yt_desc_parts.append(yt_footer_tags)
    yt_description = "\n\n".join(p for p in yt_desc_parts if p).strip()[:4900]

    # Long-tail YouTube API tags (10-15 topic + series + style keywords, no #viral spam)
    raw_yt_tags = [
        topic,
        series["series_name"],
        f"{series['series_name']} {lang}",
        *(t.lstrip("#") for t in niche_tags),
        *(w for w in re.findall(r"[A-Za-z0-9]{4,}", clean_title)[:4]),
        style.replace("_", " "),
        "Shorts" if is_short else "Full Story",
    ]
    yt_tags: List[str] = []
    seen_yt = set()
    for tg in raw_yt_tags:
        s_tg = str(tg or "").strip()
        if len(s_tg) >= 2 and s_tg.lower() not in seen_yt and s_tg.lower() not in SPAM_TAGS - {"shorts"}:
            seen_yt.add(s_tg.lower())
            yt_tags.append(s_tg)
        if len(yt_tags) >= 15:
            break

    lang_display = {
        "en": "English", "ta": "Tamil", "hi": "Hindi", "es": "Spanish",
        "fr": "French", "pt": "Portuguese", "ja": "Japanese",
    }.get(lang, lang.upper())
    playlist_name = f"{series['series_name']} ({lang_display})"

    # --- Instagram Reels SEO Package ---
    # Above-the-fold hook line + searchable mini context + save/share debate CTA + 4-5 focused hashtags
    ig_hook = clean_title
    ig_body = base_desc or hook_line
    ig_tags_line = " ".join(niche_tags[:5])
    ig_caption_parts = [ig_hook]
    if ig_body and ig_body.lower() != ig_hook.lower():
        ig_caption_parts.append(ig_body)
    ig_caption_parts.append(cta)
    if ig_tags_line:
        ig_caption_parts.append(ig_tags_line)
    ig_caption = "\n\n".join(ig_caption_parts).strip()[:2200]

    return {
        "series_name": series["series_name"],
        "hook_type": hook_type,
        "thumbnail_hook": extract_thumbnail_hook_words(clean_title, hook_line),
        "youtube_seo": {
            "title": yt_title,
            "description": yt_description,
            "tags": yt_tags,
            "category_id": series["yt_category_id"],
            "playlist_name": playlist_name,
            "first_comment": cta,
        },
        "instagram_seo": {
            "caption": ig_caption,
            "hashtags": niche_tags[:5],
            "thumb_offset_ms": max(0, int(thumb_offset_ms)),
            "first_comment": cta,
        },
    }


# ---------------------------------------------------------------------------
# 5. Safe-Zone Power-Word Subtitle Helpers
# ---------------------------------------------------------------------------
POWER_WORDS = {
    "never", "secret", "truth", "impossible", "shocking", "finally", "hidden",
    "warning", "million", "billion", "deadly", "forever", "suddenly", "nobody",
    "everyone", "destroyed", "saved", "ancient", "cursed", "golden", "first",
    "last", "only", "real", "fake", "stop", "wait", "watch", "why", "how",
}


def get_safe_zone_margins(width: int, height: int) -> Dict[str, int]:
    """
    Returns ASS subtitle margins guaranteed to sit clear of YouTube Shorts and
    Instagram Reels right-side engagement rails and bottom caption overlays.
    """
    if height > width:  # Vertical 9:16 (e.g. 1080x1920)
        return {
            "margin_l": int(width * 0.06),
            "margin_r": int(width * 0.14),   # clears right-side Like/Comment/Share rail
            "margin_v": int(height * 0.27),  # clears bottom 25% handle/caption overlay
            "banner_v": int(height * 0.14),  # top-center hook banner below status bar
        }
    return {
        "margin_l": int(width * 0.06),
        "margin_r": int(width * 0.06),
        "margin_v": int(height * 0.11),
        "banner_v": int(height * 0.08),
    }


def format_power_word_ass(chunk: str, hl_bgr: str, lang: str = "en") -> str:
    """
    Highlights high-impact numbers and emotional/curiosity power words inline in ASS
    markup so viewer eyes lock onto key narrative beats.
    """
    safe = chunk.replace("{", "(").replace("}", ")").replace("\n", " ").strip()
    if not safe:
        return ""
    if lang not in ("en", "es", "fr", "pt", "de", "id"):
        return safe
    words = safe.split()
    out: List[str] = []
    highlighted_any = False
    for w in words:
        bare = re.sub(r"[^\w]", "", w).lower()
        is_num = any(ch.isdigit() for ch in bare)
        if (is_num or bare in POWER_WORDS) and not highlighted_any:
            out.append(r"{\c" + hl_bgr + r"}" + w.upper() + r"{\c&H00FFFFFF&}")
            highlighted_any = True
        else:
            out.append(w.upper())
    return " ".join(out)


# ---------------------------------------------------------------------------
# 6. Peak-Frame Cover Scorer (Instagram thumb_offset + YouTube Thumbnail)
# ---------------------------------------------------------------------------
def _probe_duration(video_path: Path) -> float:
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1", str(video_path),
            ],
            text=True,
            timeout=15,
        ).strip()
        return max(0.0, float(out))
    except Exception:
        return 0.0


def _score_image_visual_appeal(img_path: Path) -> float:
    """
    Scores a candidate video frame on visual appeal (brightness balance,
    contrast, saturation, and edge sharpness) to avoid dark fades or blurry frames.
    Uses Pillow when installed, or falls back to zero-dependency FFmpeg raw-frame
    luminance/contrast/edge analysis so it works identically in minimal CI runners.
    """
    try:
        from PIL import Image, ImageFilter, ImageStat
        with Image.open(img_path) as im:
            rgb = im.convert("RGB").resize((240, 240))
            gray = rgb.convert("L")
            hsv = rgb.convert("HSV")

            g_stat = ImageStat.Stat(gray)
            mean_luma = g_stat.mean[0]
            contrast = g_stat.stddev[0]

            luma_score = max(0.0, 1.0 - abs(mean_luma - 125.0) / 115.0)
            if mean_luma < 28 or mean_luma > 238:
                luma_score *= 0.15

            sat_mean = ImageStat.Stat(hsv).mean[1] / 255.0
            edges = gray.filter(ImageFilter.FIND_EDGES)
            sharpness = min(1.0, ImageStat.Stat(edges).stddev[0] / 48.0)
            contrast_score = min(1.0, contrast / 65.0)

            return round(luma_score * 0.35 + contrast_score * 0.25 + sat_mean * 0.20 + sharpness * 0.20, 4)
    except Exception:
        pass

    # Zero-dependency FFmpeg fallback: 96x96 RGB24 frame analysis
    try:
        w, h = 96, 96
        raw = subprocess.check_output(
            [
                "ffmpeg", "-v", "error", "-i", str(img_path),
                "-vf", f"scale={w}:{h}", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
            ],
            timeout=15,
        )
        expected = w * h * 3
        if len(raw) < expected:
            return 0.25
        n_pix = w * h
        lumas = [0.0] * n_pix
        sat_sum = 0.0
        for idx in range(n_pix):
            r = raw[idx * 3]
            g = raw[idx * 3 + 1]
            b = raw[idx * 3 + 2]
            lumas[idx] = 0.299 * r + 0.587 * g + 0.114 * b
            mx = max(r, g, b)
            mn = min(r, g, b)
            if mx > 0:
                sat_sum += (mx - mn) / mx
        mean_luma = sum(lumas) / n_pix
        var = sum((x - mean_luma) ** 2 for x in lumas) / n_pix
        contrast = math.sqrt(var)

        # Horizontal + vertical gradient energy as sharpness proxy
        edge_sum = 0.0
        edge_cnt = 0
        for y in range(h - 1):
            row = y * w
            next_row = (y + 1) * w
            for x in range(w - 1):
                c = lumas[row + x]
                edge_sum += abs(c - lumas[row + x + 1]) + abs(c - lumas[next_row + x])
                edge_cnt += 2
        edge_mean = edge_sum / max(1, edge_cnt)

        luma_score = max(0.0, 1.0 - abs(mean_luma - 125.0) / 115.0)
        if mean_luma < 28 or mean_luma > 238:
            luma_score *= 0.12
        contrast_score = min(1.0, contrast / 65.0)
        sat_score = sat_sum / n_pix
        sharp_score = min(1.0, edge_mean / 28.0)
        return round(luma_score * 0.35 + contrast_score * 0.25 + sat_score * 0.20 + sharp_score * 0.20, 4)
    except Exception:
        return 0.5


def select_peak_cover_frame(
    video_path: Path,
    work_dir: Path,
    samples: int = 5,
) -> Dict[str, Any]:
    """
    Samples candidate frames across 14%-76% of the video and picks the sharpest,
    best-lit visual peak frame for YouTube thumbnails and Instagram Reels `thumb_offset`.
    """
    dur = _probe_duration(video_path)
    if dur <= 0.4:
        return {"timestamp_sec": 0.0, "thumb_offset_ms": 0, "score": 0.0, "frame_path": None}

    work_dir.mkdir(parents=True, exist_ok=True)
    n = max(3, min(7, int(samples)))
    fractions = [0.14 + (0.62 * i / (n - 1)) for i in range(n)]

    best = {"timestamp_sec": round(dur * 0.25, 2), "thumb_offset_ms": int(dur * 250), "score": -1.0, "frame_path": None}
    for idx, frac in enumerate(fractions):
        ts = round(max(0.2, min(dur - 0.2, dur * frac)), 2)
        out_jpg = work_dir / f"cover_cand_{idx}.jpg"
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-ss", f"{ts:.2f}", "-i", str(video_path),
                    "-frames:v", "1", "-q:v", "4", str(out_jpg),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=True,
            )
            if out_jpg.exists() and out_jpg.stat().st_size > 1000:
                score = _score_image_visual_appeal(out_jpg)
                if score > best["score"]:
                    best = {
                        "timestamp_sec": ts,
                        "thumb_offset_ms": int(ts * 1000),
                        "score": score,
                        "frame_path": out_jpg,
                    }
        except Exception:
            continue
    return best


def render_ctr_thumbnail(
    video_path: Path,
    hook_text: str,
    font_path: str,
    out_path: Path,
    work_dir: Path,
    peak_info: Optional[Dict[str, Any]] = None,
) -> Path:
    """
    Renders a 1280x720 high-CTR YouTube thumbnail from the peak visual frame with
    bold 3-4 word curiosity text and a clean lower-third contrast scrim.
    """
    peak = peak_info or select_peak_cover_frame(video_path, work_dir)
    ts = float(peak.get("timestamp_sec") or 0.5)
    hook = extract_thumbnail_hook_words(hook_text)
    lines = textwrap.wrap(hook, width=14)[:2]
    tf = work_dir / "ctr_thumb.txt"
    tf.write_text("\n".join(lines), encoding="utf-8")

    def _esc(p: Path) -> str:
        return str(p.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

    vf = (
        "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
        "eq=contrast=1.12:saturation=1.28:brightness=-0.04,"
        "drawbox=x=0:y=ih*0.50:w=iw:h=ih*0.50:color=black@0.58:t=fill,"
        f"drawtext=fontfile='{_esc(Path(font_path))}':textfile='{_esc(tf)}':expansion=none"
        ":fontsize=96:fontcolor=#FFE600:borderw=8:bordercolor=black:line_spacing=14"
        ":x=(w-text_w)/2:y=h*0.58"
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", f"{ts:.2f}", "-i", str(video_path),
            "-frames:v", "1", "-vf", vf, "-q:v", "2", str(out_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
        check=True,
    )
    return out_path
