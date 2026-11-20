#!/usr/bin/env python3
"""
Character Bible, Visual Consistency Prompt Locking & Multi-Voice Casting Manager.

Maintains consistent character faces, body structures, outfits, color palettes,
deterministic generation seeds, reusable reference images, and character-specific
voices (male, female, child, deep/dramatic) across Hindi, Tamil, English, and all
supported RAPTAR languages.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Language-aware multi-character voice pools (Edge-TTS Neural voices — $0 cost)
# Format: role -> (edge_tts_voice, pitch, rate)
VOICE_CAST_REGISTRY: Dict[str, Dict[str, Tuple[str, str, str]]] = {
    "en": {
        "narrator": ("en-US-AndrewNeural", "+0Hz", "+2%"),
        "male_deep": ("en-US-GuyNeural", "-10Hz", "-4%"),
        "male_young": ("en-US-ChristopherNeural", "+4Hz", "+6%"),
        "female": ("en-US-AriaNeural", "+2Hz", "+2%"),
        "female_dramatic": ("en-US-JennyNeural", "-3Hz", "-2%"),
        "child": ("en-US-AnaNeural", "+10Hz", "+6%"),
        "elder": ("en-GB-RyanNeural", "-8Hz", "-8%"),
    },
    "hi": {
        "narrator": ("hi-IN-MadhurNeural", "+0Hz", "+0%"),
        "male_deep": ("hi-IN-MadhurNeural", "-12Hz", "-4%"),
        "male_young": ("hi-IN-MadhurNeural", "+6Hz", "+6%"),
        "female": ("hi-IN-SwaraNeural", "+0Hz", "+2%"),
        "female_dramatic": ("hi-IN-SwaraNeural", "-4Hz", "-2%"),
        "child": ("hi-IN-SwaraNeural", "+16Hz", "+8%"),
        "elder": ("hi-IN-MadhurNeural", "-14Hz", "-10%"),
    },
    "ta": {
        "narrator": ("ta-IN-ValluvarNeural", "+0Hz", "+0%"),
        "male_deep": ("ta-IN-ValluvarNeural", "-12Hz", "-4%"),
        "male_young": ("ta-IN-ValluvarNeural", "+6Hz", "+6%"),
        "female": ("ta-IN-PallaviNeural", "+0Hz", "+2%"),
        "female_dramatic": ("ta-IN-PallaviNeural", "-4Hz", "-2%"),
        "child": ("ta-IN-PallaviNeural", "+15Hz", "+8%"),
        "elder": ("ta-IN-ValluvarNeural", "-14Hz", "-10%"),
    },
    "es": {
        "narrator": ("es-ES-AlvaroNeural", "+0Hz", "+2%"),
        "male_deep": ("es-MX-JorgeNeural", "-10Hz", "-4%"),
        "male_young": ("es-ES-AlvaroNeural", "+5Hz", "+6%"),
        "female": ("es-ES-ElviraNeural", "+0Hz", "+2%"),
        "female_dramatic": ("es-MX-DaliaNeural", "-4Hz", "-2%"),
        "child": ("es-ES-ElviraNeural", "+14Hz", "+8%"),
        "elder": ("es-ES-AlvaroNeural", "-12Hz", "-8%"),
    },
    "ja": {
        "narrator": ("ja-JP-KeitaNeural", "+0Hz", "+0%"),
        "male_deep": ("ja-JP-KeitaNeural", "-10Hz", "-4%"),
        "male_young": ("ja-JP-KeitaNeural", "+6Hz", "+6%"),
        "female": ("ja-JP-NanamiNeural", "+0Hz", "+2%"),
        "female_dramatic": ("ja-JP-NanamiNeural", "-4Hz", "-2%"),
        "child": ("ja-JP-NanamiNeural", "+14Hz", "+8%"),
        "elder": ("ja-JP-KeitaNeural", "-12Hz", "-8%"),
    },
    "fr": {
        "narrator": ("fr-FR-HenriNeural", "+0Hz", "+0%"),
        "male_deep": ("fr-FR-HenriNeural", "-10Hz", "-4%"),
        "male_young": ("fr-FR-HenriNeural", "+6Hz", "+6%"),
        "female": ("fr-FR-DeniseNeural", "+0Hz", "+2%"),
        "female_dramatic": ("fr-FR-DeniseNeural", "-4Hz", "-2%"),
        "child": ("fr-FR-DeniseNeural", "+14Hz", "+8%"),
        "elder": ("fr-FR-HenriNeural", "-12Hz", "-8%"),
    },
    "ar": {
        "narrator": ("ar-SA-HamedNeural", "+0Hz", "+0%"),
        "male_deep": ("ar-SA-HamedNeural", "-10Hz", "-4%"),
        "male_young": ("ar-SA-HamedNeural", "+6Hz", "+6%"),
        "female": ("ar-SA-ZariyahNeural", "+0Hz", "+2%"),
        "female_dramatic": ("ar-SA-ZariyahNeural", "-4Hz", "-2%"),
        "child": ("ar-SA-ZariyahNeural", "+14Hz", "+8%"),
        "elder": ("ar-SA-HamedNeural", "-12Hz", "-8%"),
    },
}


@dataclass
class CharacterProfile:
    character_id: str
    name: str
    archetype: str = "human"           # lion | cub | squirrel | tiger | robot | human | child | elder | hero | anime_hero
    gender: str = "male"               # male | female | neutral
    age_group: str = "adult"           # child | young | adult | elder
    voice_role: str = "male_deep"      # narrator | male_deep | male_young | female | female_dramatic | child | elder
    appearance_lock: str = ""          # Immutable physical face/fur/body/proportions description
    outfit_lock: str = ""              # Immutable clothing & accessories description
    color_palette: Tuple[str, str, str] = ("#f8fafc", "#1e293b", "#fbbf24")
    personality: str = "expressive and memorable"
    voice_id: str = "en-US-GuyNeural"
    voice_pitch: str = "+0Hz"
    voice_rate: str = "+0%"
    seed: int = 1001
    reference_image: str = ""          # Optional path to cached character reference PNG

    def prompt_signature(self) -> str:
        """Compact immutable visual identity block injected into every shot featuring this character."""
        parts = [f"{self.name} ({self.archetype})"]
        if self.appearance_lock:
            parts.append(self.appearance_lock.strip().rstrip("."))
        if self.outfit_lock:
            parts.append(f"wearing {self.outfit_lock.strip().rstrip('.')}")
        return ", ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["color_palette"] = list(self.color_palette)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterProfile":
        pal = data.get("color_palette") or ["#f8fafc", "#1e293b", "#fbbf24"]
        if len(pal) < 3:
            pal = list(pal) + ["#fbbf24"] * (3 - len(pal))
        return cls(
            character_id=str(data.get("character_id") or "char_0"),
            name=str(data.get("name") or "Hero"),
            archetype=str(data.get("archetype") or "human"),
            gender=str(data.get("gender") or "male"),
            age_group=str(data.get("age_group") or "adult"),
            voice_role=str(data.get("voice_role") or "narrator"),
            appearance_lock=str(data.get("appearance_lock") or ""),
            outfit_lock=str(data.get("outfit_lock") or ""),
            color_palette=(str(pal[0]), str(pal[1]), str(pal[2])),
            personality=str(data.get("personality") or ""),
            voice_id=str(data.get("voice_id") or "en-US-GuyNeural"),
            voice_pitch=str(data.get("voice_pitch") or "+0Hz"),
            voice_rate=str(data.get("voice_rate") or "+0%"),
            seed=int(data.get("seed") or 1001),
            reference_image=str(data.get("reference_image") or ""),
        )


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "char").lower()).strip("_")
    return s or "char"


def assign_character_voice(
    role: str,
    lang: str = "en",
    gender: str = "male",
    age_group: str = "adult",
    slot_idx: int = 0,
) -> Tuple[str, str, str]:
    """Selects a distinct neural voice, pitch, and speaking rate for a character."""
    lang_code = (lang or "en").lower().strip()
    pool = VOICE_CAST_REGISTRY.get(lang_code, VOICE_CAST_REGISTRY["en"])

    r = (role or "").lower().strip()
    if r in pool:
        base_voice, base_pitch, base_rate = pool[r]
    elif age_group == "child":
        base_voice, base_pitch, base_rate = pool["child"]
    elif age_group == "elder":
        base_voice, base_pitch, base_rate = pool["elder"]
    elif gender == "female":
        base_voice, base_pitch, base_rate = pool["female"]
    else:
        base_voice, base_pitch, base_rate = pool["male_deep" if slot_idx % 2 == 0 else "male_young"]

    # Add subtle pitch offset if multiple characters share the same role so voices stay distinct
    if slot_idx >= 2:
        m = re.match(r"([+-]?\d+)Hz", base_pitch)
        hz = int(m.group(1)) if m else 0
        offset = ((slot_idx % 3) - 1) * 4
        base_pitch = f"{hz + offset:+d}Hz"

    return base_voice, base_pitch, base_rate


class CharacterBible:
    """Stores, persists, and enforces multi-character visual & vocal consistency across a story."""

    def __init__(self, project_dir: Optional[Path] = None, lang: str = "en") -> None:
        self.lang = (lang or "en").lower().strip()
        self.project_dir = Path(project_dir) if project_dir else None
        self.characters: Dict[str, CharacterProfile] = {}

    def register(
        self,
        name: str,
        archetype: str = "human",
        gender: str = "male",
        age_group: str = "adult",
        voice_role: str = "",
        appearance_lock: str = "",
        outfit_lock: str = "",
        color_palette: Optional[Tuple[str, str, str]] = None,
        personality: str = "",
    ) -> CharacterProfile:
        cid = _slug(name)
        slot_idx = len(self.characters)
        resolved_role = voice_role or (
            "child" if age_group == "child"
            else "elder" if age_group == "elder"
            else "female" if gender == "female"
            else "male_deep" if slot_idx == 0
            else "male_young"
        )
        voice_id, pitch, rate = assign_character_voice(
            resolved_role, lang=self.lang, gender=gender, age_group=age_group, slot_idx=slot_idx
        )
        seed = int(hashlib.md5(f"{cid}:{appearance_lock}:{outfit_lock}".encode("utf-8")).hexdigest()[:8], 16) % 999999 + 1

        default_palettes = {
            "lion": ("#f8fafc", "#e2e8f0", "#f59e0b"),
            "cub": ("#f8fafc", "#111827", "#fbbf24"),
            "tiger": ("#fb923c", "#1f2937", "#fef08a"),
            "squirrel": ("#b45309", "#fde68a", "#f59e0b"),
            "robot": ("#38bdf8", "#0f172a", "#00e5ff"),
            "anime_hero": ("#e0e7ff", "#312e81", "#ff4d6d"),
        }
        pal = color_palette or default_palettes.get(archetype, ("#fde68a", "#1e293b", "#38bdf8"))

        prof = CharacterProfile(
            character_id=cid,
            name=name,
            archetype=archetype,
            gender=gender,
            age_group=age_group,
            voice_role=resolved_role,
            appearance_lock=appearance_lock or f"distinctive {age_group} {archetype} with expressive face and consistent proportions",
            outfit_lock=outfit_lock or "clean stylized signature attire",
            color_palette=pal,
            personality=personality or "memorable and expressive",
            voice_id=voice_id,
            voice_pitch=pitch,
            voice_rate=rate,
            seed=seed,
        )
        self.characters[cid] = prof
        return prof

    def get(self, name_or_id: str) -> Optional[CharacterProfile]:
        cid = _slug(name_or_id)
        if cid in self.characters:
            return self.characters[cid]
        low = (name_or_id or "").strip().lower()
        for ch in self.characters.values():
            if ch.name.lower() == low:
                return ch
        return None

    def build_consistent_shot_prompt(
        self,
        art_style: str,
        scene_action: str,
        character_names: List[str],
        environment: str = "",
        camera_direction: str = "medium cinematic shot",
        aspect_ratio: str = "9:16",
    ) -> Tuple[str, int]:
        """
        Builds a character-locked visual prompt and deterministic seed for a shot.
        Guarantees identical face, outfit, colors, and proportions across all shots.
        """
        locks: List[str] = []
        seeds: List[int] = []
        for cname in character_names or []:
            prof = self.get(cname)
            if prof:
                locks.append(prof.prompt_signature())
                seeds.append(prof.seed)
        if not locks and self.characters:
            first = next(iter(self.characters.values()))
            locks.append(first.prompt_signature())
            seeds.append(first.seed)

        orient_label = {
            "9:16": "Vertical 9:16 portrait framing",
            "16:9": "Widescreen 16:9 cinematic framing",
            "1:1": "Square 1:1 balanced framing",
        }.get(aspect_ratio, "Cinematic framing")

        parts = [
            f"{art_style.strip().rstrip('.')}.",
            f"Consistent character sheet lock: {'; '.join(locks)}." if locks else "",
            f"Setting: {environment.strip().rstrip('.')}." if environment else "",
            f"Action: {scene_action.strip().rstrip('.')}.",
            f"Camera: {camera_direction.strip().rstrip('.')}, {orient_label}.",
            "Maintain exact same character faces, outfits, colors, and proportions across shots, no text, no watermark.",
        ]
        prompt = " ".join(p for p in parts if p)
        base_seed = seeds[0] if seeds else 424242
        return prompt, base_seed

    def save(self, path: Optional[Path] = None) -> Path:
        target = path or ((self.project_dir / "characters.json") if self.project_dir else Path("characters.json"))
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {"language": self.lang, "characters": [c.to_dict() for c in self.characters.values()]}
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: Path) -> "CharacterBible":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        bible = cls(project_dir=Path(path).parent, lang=data.get("language", "en"))
        for item in data.get("characters", []):
            prof = CharacterProfile.from_dict(item)
            bible.characters[prof.character_id] = prof
        return bible
