#!/usr/bin/env python3
"""
RAPTAR Open-Source Motion Graphics, Particle VFX & Compositing Engine.

Synthesizes headless, zero-cost production patterns inspired by the open-source
animation repositories referenced for RAPTAR:
  - Theatre.js (theatre-js/theatre):
      Declarative JSON keyframe sheets + cubic-bezier & spring easing solver.
  - SVG.js (svgdotjs/svg.js) & Friction (friction2d/friction):
      Programmatic multi-layer vector scene graph, timeline runner, and
      per-frame animated SVG rendering (including auto-rigging Gemini SVGs).
  - Effekseer (effekseer/Effekseer) & OpenVDB (AcademySoftwareFoundation/openvdb):
      Deterministic procedural particle emitters (embers, sakura petals, magic
      stars, cyber motes) and layered volumetric mist/atmosphere overlays.
  - Natron (NatronGitHub/Natron):
      Node-graph video compositing & grading compiler (Grade, Glow/Unsharp,
      Vignette, Grain, Alpha-Overlay Merge, xfade/acrossfade transitions, and
      broadcast audio mastering) targeting native FFmpeg filtergraphs.
  - Synfig Studio (synfig/synfig):
      Open `.sif` XML keyframe canvas exporter with optional headless `synfig`
      CLI render hook when installed locally or on a self-hosted runner.

Zero extra pip/apt dependencies required beyond Python 3 stdlib + FFmpeg
(with librsvg, libx264, and aac — already standard on Ubuntu 24.04 runners).
"""

from __future__ import annotations

import hashlib
import math
import os
import random
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union


# ============================================================================
# 1. Theatre.js & SVG.js-inspired Keyframe Timeline + Cubic-Bezier / Spring
# ============================================================================

def _cubic_bezier_axis(t: float, p1: float, p2: float) -> float:
    u = 1.0 - t
    return 3.0 * u * u * t * p1 + 3.0 * u * t * t * p2 + t * t * t


def _cubic_bezier_deriv(t: float, p1: float, p2: float) -> float:
    u = 1.0 - t
    return 3.0 * u * u * p1 + 6.0 * u * t * (p2 - p1) + 3.0 * t * t * (1.0 - p2)


def cubic_bezier(p1x: float, p1y: float, p2x: float, p2y: float) -> Callable[[float], float]:
    """Returns a CSS/Theatre.js-compatible cubic-bezier easing function on [0, 1]."""
    def _ease(x: float) -> float:
        if x <= 0.0:
            return 0.0
        if x >= 1.0:
            return 1.0
        # Newton-Raphson solver with bisection fallback
        t = x
        for _ in range(6):
            err = _cubic_bezier_axis(t, p1x, p2x) - x
            if abs(err) < 1e-6:
                break
            d = _cubic_bezier_deriv(t, p1x, p2x)
            if abs(d) < 1e-6:
                break
            t = max(0.0, min(1.0, t - err / d))
        else:
            lo, hi = 0.0, 1.0
            t = x
            for _ in range(12):
                val = _cubic_bezier_axis(t, p1x, p2x)
                if abs(val - x) < 1e-5:
                    break
                if val < x:
                    lo = t
                else:
                    hi = t
                t = 0.5 * (lo + hi)
        return _cubic_bezier_axis(t, p1y, p2y)

    return _ease


def spring_ease(t: float, damping: float = 6.5, freq: float = 2.6) -> float:
    """Underdamped spring curve inspired by Theatre.js & SVG.js Spring controllers."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return 1.0 - math.exp(-damping * t) * math.cos(freq * math.pi * t)


def bounce_ease(t: float) -> float:
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    if t < 1.0 / 2.75:
        return 7.5625 * t * t
    if t < 2.0 / 2.75:
        t -= 1.5 / 2.75
        return 7.5625 * t * t + 0.75
    if t < 2.5 / 2.75:
        t -= 2.25 / 2.75
        return 7.5625 * t * t + 0.9375
    t -= 2.625 / 2.75
    return 7.5625 * t * t + 0.984375


EASINGS: Dict[str, Callable[[float], float]] = {
    "linear": lambda t: max(0.0, min(1.0, t)),
    "ease_in": cubic_bezier(0.42, 0.0, 1.0, 1.0),
    "ease_out": cubic_bezier(0.0, 0.0, 0.58, 1.0),
    "ease_in_out": cubic_bezier(0.42, 0.0, 0.58, 1.0),
    "ease_out_cubic": cubic_bezier(0.33, 1.0, 0.68, 1.0),
    "ease_in_out_cubic": cubic_bezier(0.65, 0.0, 0.35, 1.0),
    "ease_out_back": cubic_bezier(0.34, 1.56, 0.64, 1.0),
    "ease_in_out_sine": lambda t: -(math.cos(math.pi * max(0.0, min(1.0, t))) - 1.0) / 2.0,
    "cinematic": cubic_bezier(0.22, 1.0, 0.36, 1.0),
    "spring": spring_ease,
    "bounce": bounce_ease,
}


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    c = hex_color.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _rgb_to_hex(r: float, g: float, b: float) -> str:
    ri = max(0, min(255, int(round(r))))
    gi = max(0, min(255, int(round(g))))
    bi = max(0, min(255, int(round(b))))
    return f"#{ri:02x}{gi:02x}{bi:02x}"


def lerp_value(a: Any, b: Any, u: float) -> Any:
    """Interpolates floats, numeric tuples/lists, or #RRGGBB hex colors."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) + (float(b) - float(a)) * u
    if isinstance(a, str) and isinstance(b, str) and a.startswith("#") and b.startswith("#"):
        ra, ga, ba = _hex_to_rgb(a)
        rb, gb, bb = _hex_to_rgb(b)
        return _rgb_to_hex(ra + (rb - ra) * u, ga + (gb - ga) * u, ba + (bb - ba) * u)
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)) and len(a) == len(b):
        return tuple(float(x) + (float(y) - float(x)) * u for x, y in zip(a, b))
    return b if u >= 0.5 else a


@dataclass
class Keyframe:
    time: float  # normalized [0.0 .. 1.0] or absolute seconds
    value: Any
    easing: str = "ease_in_out"


@dataclass
class KeyframeTrack:
    name: str
    keyframes: List[Keyframe] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.keyframes.sort(key=lambda k: k.time)

    def sample(self, t: float) -> Any:
        if not self.keyframes:
            return 0.0
        if t <= self.keyframes[0].time:
            return self.keyframes[0].value
        if t >= self.keyframes[-1].time:
            return self.keyframes[-1].value
        for i in range(len(self.keyframes) - 1):
            k0, k1 = self.keyframes[i], self.keyframes[i + 1]
            if k0.time <= t <= k1.time:
                span = max(1e-9, k1.time - k0.time)
                local_t = (t - k0.time) / span
                ease_fn = EASINGS.get(k0.easing, EASINGS["ease_in_out"])
                return lerp_value(k0.value, k1.value, ease_fn(local_t))
        return self.keyframes[-1].value


@dataclass
class MotionSheet:
    """Declarative animation sheet modeled after Theatre.js project sheets."""
    name: str
    duration: float
    tracks: Dict[str, KeyframeTrack] = field(default_factory=dict)

    def add_track(self, name: str, keyframes: Sequence[Tuple[float, Any, str]]) -> "MotionSheet":
        self.tracks[name] = KeyframeTrack(
            name=name,
            keyframes=[Keyframe(t, v, e) for (t, v, e) in keyframes],
        )
        return self

    def sample(self, norm_t: float) -> Dict[str, Any]:
        nt = max(0.0, min(1.0, norm_t))
        return {name: track.sample(nt) for name, track in self.tracks.items()}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sheet": self.name,
            "duration": round(self.duration, 3),
            "tracks": {
                k: [{"t": kf.time, "v": kf.value, "ease": kf.easing} for kf in tr.keyframes]
                for k, tr in self.tracks.items()
            },
        }


# ============================================================================
# 2. Effekseer & OpenVDB-inspired Procedural Particle & Volumetric VFX Engine
# ============================================================================

STYLE_PARTICLE_PRESET: Dict[str, str] = {
    "animated_myth": "sparks_embers",
    "legend": "sparks_embers",
    "animated_anime": "sakura_petals",
    "romance": "sakura_petals",
    "allure": "sakura_petals",
    "animated_comedy": "magic_stars",
    "fable": "magic_stars",
    "story": "magic_stars",
    "horror": "volumetric_mist",
    "thriller": "volumetric_mist",
    "mystery": "volumetric_mist",
    "scifi": "cyber_motes",
    "fact": "cyber_motes",
    "fitness_glamour": "magic_stars",
}


def pick_particle_preset(style: str, fx: str = "") -> str:
    s = (style or "").lower().strip()
    if s in STYLE_PARTICLE_PRESET:
        return STYLE_PARTICLE_PRESET[s]
    f = (fx or "").lower().strip()
    if "eerie" in f or "dark" in f:
        return "volumetric_mist"
    if "warm" in f or "gold" in f:
        return "sparks_embers"
    if "sparkle" in f or "vibrant" in f:
        return "magic_stars"
    return "sparks_embers"


@dataclass
class Particle:
    x0: float
    y0: float
    vx: float
    vy: float
    size: float
    phase: float
    life_offset: float
    life_span: float
    rot_speed: float
    color: str
    opacity: float
    sway_amp: float
    sway_freq: float


class ParticleEmitter:
    """Deterministic Effekseer-style particle & volumetric atmosphere generator."""

    def __init__(self, preset: str, width: int, height: int, seed: int = 42, count: Optional[int] = None) -> None:
        self.preset = preset
        self.w = width
        self.h = height
        self.rng = random.Random(seed)
        self.particles: List[Particle] = []
        self._init_particles(count)

    def _init_particles(self, count_override: Optional[int]) -> None:
        if self.preset == "sparks_embers":
            n = count_override or 32
            palette = ("#ffd166", "#ff9f1c", "#ff6b35", "#fff3b0")
            for _ in range(n):
                self.particles.append(Particle(
                    x0=self.rng.uniform(0.05 * self.w, 0.95 * self.w),
                    y0=self.rng.uniform(0.35 * self.h, 1.08 * self.h),
                    vx=self.rng.uniform(-18.0, 18.0),
                    vy=self.rng.uniform(-110.0, -42.0),
                    size=self.rng.uniform(2.5, 7.5),
                    phase=self.rng.uniform(0.0, math.tau),
                    life_offset=self.rng.uniform(0.0, 1.0),
                    life_span=self.rng.uniform(2.2, 4.5),
                    rot_speed=self.rng.uniform(-45.0, 45.0),
                    color=self.rng.choice(palette),
                    opacity=self.rng.uniform(0.45, 0.92),
                    sway_amp=self.rng.uniform(12.0, 36.0),
                    sway_freq=self.rng.uniform(1.2, 2.8),
                ))
        elif self.preset == "sakura_petals":
            n = count_override or 28
            palette = ("#ffb3c6", "#ffccd5", "#ff8fab", "#ffe5ec")
            for _ in range(n):
                self.particles.append(Particle(
                    x0=self.rng.uniform(-0.08 * self.w, 1.05 * self.w),
                    y0=self.rng.uniform(-0.10 * self.h, 0.85 * self.h),
                    vx=self.rng.uniform(24.0, 68.0),
                    vy=self.rng.uniform(36.0, 88.0),
                    size=self.rng.uniform(6.0, 14.0),
                    phase=self.rng.uniform(0.0, math.tau),
                    life_offset=self.rng.uniform(0.0, 1.0),
                    life_span=self.rng.uniform(3.2, 5.8),
                    rot_speed=self.rng.uniform(-140.0, 140.0),
                    color=self.rng.choice(palette),
                    opacity=self.rng.uniform(0.50, 0.88),
                    sway_amp=self.rng.uniform(20.0, 50.0),
                    sway_freq=self.rng.uniform(1.0, 2.2),
                ))
        elif self.preset == "volumetric_mist":
            # OpenVDB-inspired layered drifting volumetric fog/smoke wisps
            n = count_override or 14
            palette = ("#94a3b8", "#cbd5e1", "#64748b", "#a78bfa")
            for _ in range(n):
                self.particles.append(Particle(
                    x0=self.rng.uniform(-0.15 * self.w, 1.15 * self.w),
                    y0=self.rng.uniform(0.20 * self.h, 0.98 * self.h),
                    vx=self.rng.uniform(14.0, 42.0) * self.rng.choice((-1.0, 1.0)),
                    vy=self.rng.uniform(-14.0, 8.0),
                    size=self.rng.uniform(self.w * 0.14, self.w * 0.28),
                    phase=self.rng.uniform(0.0, math.tau),
                    life_offset=self.rng.uniform(0.0, 1.0),
                    life_span=self.rng.uniform(4.0, 7.0),
                    rot_speed=self.rng.uniform(-6.0, 6.0),
                    color=self.rng.choice(palette),
                    opacity=self.rng.uniform(0.08, 0.19),
                    sway_amp=self.rng.uniform(14.0, 32.0),
                    sway_freq=self.rng.uniform(0.5, 1.1),
                ))
        elif self.preset == "cyber_motes":
            n = count_override or 28
            palette = ("#38bdf8", "#00e5ff", "#a855f7", "#e0f2fe")
            for _ in range(n):
                self.particles.append(Particle(
                    x0=self.rng.uniform(0.04 * self.w, 0.96 * self.w),
                    y0=self.rng.uniform(0.08 * self.h, 0.95 * self.h),
                    vx=self.rng.uniform(-22.0, 22.0),
                    vy=self.rng.uniform(-48.0, -14.0),
                    size=self.rng.uniform(3.0, 8.5),
                    phase=self.rng.uniform(0.0, math.tau),
                    life_offset=self.rng.uniform(0.0, 1.0),
                    life_span=self.rng.uniform(2.5, 5.0),
                    rot_speed=self.rng.uniform(-60.0, 60.0),
                    color=self.rng.choice(palette),
                    opacity=self.rng.uniform(0.35, 0.82),
                    sway_amp=self.rng.uniform(8.0, 24.0),
                    sway_freq=self.rng.uniform(1.5, 3.0),
                ))
        else:  # magic_stars
            n = count_override or 26
            palette = ("#ffd166", "#ffffff", "#4cc9f0", "#f72585")
            for _ in range(n):
                self.particles.append(Particle(
                    x0=self.rng.uniform(0.06 * self.w, 0.94 * self.w),
                    y0=self.rng.uniform(0.10 * self.h, 0.92 * self.h),
                    vx=self.rng.uniform(-16.0, 16.0),
                    vy=self.rng.uniform(-35.0, -10.0),
                    size=self.rng.uniform(4.0, 10.5),
                    phase=self.rng.uniform(0.0, math.tau),
                    life_offset=self.rng.uniform(0.0, 1.0),
                    life_span=self.rng.uniform(2.2, 4.4),
                    rot_speed=self.rng.uniform(-90.0, 90.0),
                    color=self.rng.choice(palette),
                    opacity=self.rng.uniform(0.42, 0.90),
                    sway_amp=self.rng.uniform(10.0, 26.0),
                    sway_freq=self.rng.uniform(1.4, 2.8),
                ))

    def render_svg_group(self, t_sec: float) -> str:
        """Emits an SVG <g id="vfx-particles"> fragment evaluated at timestamp t_sec."""
        elems: List[str] = ['<g id="vfx-particles">']
        for p in self.particles:
            age_norm = ((t_sec / max(0.5, p.life_span)) + p.life_offset) % 1.0
            age_sec = age_norm * p.life_span
            # Smooth fade-in and fade-out envelope (Effekseer Alpha-Over-Life curve)
            envelope = math.sin(math.pi * age_norm) ** 0.7
            alpha = max(0.0, min(1.0, p.opacity * envelope))
            if alpha < 0.02:
                continue

            x = (p.x0 + p.vx * age_sec + math.sin(t_sec * p.sway_freq + p.phase) * p.sway_amp) % (self.w + 80) - 40
            y = p.y0 + p.vy * age_sec + math.cos(t_sec * p.sway_freq * 0.7 + p.phase) * (p.sway_amp * 0.35)
            # Wrap smoothly vertically
            y = (y + 80) % (self.h + 160) - 80

            scale_life = 0.65 + 0.55 * math.sin(math.pi * age_norm)
            sz = max(1.2, p.size * scale_life)
            rot = (p.rot_speed * t_sec + p.phase * 57.3) % 360.0

            if self.preset == "sakura_petals":
                elems.append(
                    f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{sz:.1f}" ry="{sz * 0.52:.1f}" '
                    f'fill="{p.color}" opacity="{alpha:.2f}" '
                    f'transform="rotate({rot:.1f} {x:.1f} {y:.1f})"/>'
                )
            elif self.preset == "volumetric_mist":
                elems.append(
                    f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{sz * 1.45:.1f}" ry="{sz * 0.58:.1f}" '
                    f'fill="{p.color}" opacity="{alpha:.2f}"/>'
                )
            elif self.preset == "magic_stars":
                # 4-point animated sparkle star
                r_out = sz * 1.25
                r_in = sz * 0.32
                pts = (
                    f"{x:.1f},{y - r_out:.1f} {x + r_in:.1f},{y - r_in:.1f} "
                    f"{x + r_out:.1f},{y:.1f} {x + r_in:.1f},{y + r_in:.1f} "
                    f"{x:.1f},{y + r_out:.1f} {x - r_in:.1f},{y + r_in:.1f} "
                    f"{x - r_out:.1f},{y:.1f} {x - r_in:.1f},{y - r_in:.1f}"
                )
                elems.append(
                    f'<polygon points="{pts}" fill="{p.color}" opacity="{alpha:.2f}" '
                    f'transform="rotate({rot:.1f} {x:.1f} {y:.1f})"/>'
                )
            elif self.preset == "cyber_motes":
                elems.append(
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{sz * 1.9:.1f}" fill="{p.color}" opacity="{alpha * 0.25:.2f}"/>'
                    f'<rect x="{x - sz * 0.6:.1f}" y="{y - sz * 0.6:.1f}" width="{sz * 1.2:.1f}" height="{sz * 1.2:.1f}" '
                    f'fill="{p.color}" opacity="{alpha:.2f}" transform="rotate({rot:.1f} {x:.1f} {y:.1f})"/>'
                )
            else:  # sparks_embers
                elems.append(
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{sz * 2.2:.1f}" fill="{p.color}" opacity="{alpha * 0.24:.2f}"/>'
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{sz:.1f}" fill="{p.color}" opacity="{alpha:.2f}"/>'
                )
        elems.append("</g>")
        return "".join(elems)


# ============================================================================
# 3. SVG.js / Friction-inspired Multi-Layer Animated Vector Scene Engine
# ============================================================================

STYLE_PALETTES: Dict[str, Dict[str, str]] = {
    "animated_myth": {
        "sky_top": "#170d33", "sky_mid": "#b5446e", "sky_bot": "#ff9e53",
        "orb": "#ffe082", "far_hill": "#3b235a", "mid_hill": "#251442",
        "near_hill": "#120924", "accent": "#ffd166", "cloud": "#ffd8be",
    },
    "animated_comedy": {
        "sky_top": "#0f4c81", "sky_mid": "#38bdf8", "sky_bot": "#fde68a",
        "orb": "#fffbeb", "far_hill": "#2a9d8f", "mid_hill": "#1d7a72",
        "near_hill": "#114b5f", "accent": "#ff9f1c", "cloud": "#ffffff",
    },
    "animated_anime": {
        "sky_top": "#0b132b", "sky_mid": "#5e2b97", "sky_bot": "#ff4d6d",
        "orb": "#ffe5ec", "far_hill": "#2d1b4e", "mid_hill": "#1c1538",
        "near_hill": "#0c0a1f", "accent": "#ffb3c6", "cloud": "#ffccd5",
    },
    "horror": {
        "sky_top": "#04040a", "sky_mid": "#1b1035", "sky_bot": "#4a1026",
        "orb": "#e63946", "far_hill": "#161124", "mid_hill": "#0d0917",
        "near_hill": "#05040a", "accent": "#e63946", "cloud": "#475569",
    },
    "fable": {
        "sky_top": "#1d2d50", "sky_mid": "#4cc9f0", "sky_bot": "#f7b267",
        "orb": "#fff3b0", "far_hill": "#3a506b", "mid_hill": "#2b3d54",
        "near_hill": "#1b263b", "accent": "#ffd166", "cloud": "#e0fbfc",
    },
    "scifi": {
        "sky_top": "#030712", "sky_mid": "#0f172a", "sky_bot": "#1d4ed8",
        "orb": "#38bdf8", "far_hill": "#1e293b", "mid_hill": "#0f172a",
        "near_hill": "#020617", "accent": "#00e5ff", "cloud": "#60a5fa",
    },
    "legend": {
        "sky_top": "#1f1209", "sky_mid": "#9a3412", "sky_bot": "#f59e0b",
        "orb": "#fef08a", "far_hill": "#451a03", "mid_hill": "#290f02",
        "near_hill": "#140801", "accent": "#fbbf24", "cloud": "#fed7aa",
    },
}


def build_scene_motion_sheet(duration: float, motion: str = "zoom_in") -> MotionSheet:
    """Creates a Theatre.js-style keyframe MotionSheet tailored to camera choreography."""
    sheet = MotionSheet(name=f"scene_{motion}", duration=duration)
    if motion == "zoom_out":
        sheet.add_track("cam_scale", [(0.0, 1.16, "cinematic"), (1.0, 1.0, "linear")])
        sheet.add_track("cam_x", [(0.0, -18.0, "ease_in_out_sine"), (1.0, 0.0, "linear")])
        sheet.add_track("cam_y", [(0.0, -10.0, "ease_in_out_sine"), (1.0, 0.0, "linear")])
    elif motion == "pan_right":
        sheet.add_track("cam_scale", [(0.0, 1.08, "ease_in_out"), (1.0, 1.12, "linear")])
        sheet.add_track("cam_x", [(0.0, -34.0, "cinematic"), (1.0, 34.0, "linear")])
        sheet.add_track("cam_y", [(0.0, 0.0, "ease_in_out_sine"), (0.5, -8.0, "ease_in_out_sine"), (1.0, 0.0, "linear")])
    elif motion == "pan_left":
        sheet.add_track("cam_scale", [(0.0, 1.08, "ease_in_out"), (1.0, 1.12, "linear")])
        sheet.add_track("cam_x", [(0.0, 34.0, "cinematic"), (1.0, -34.0, "linear")])
        sheet.add_track("cam_y", [(0.0, 0.0, "ease_in_out_sine"), (0.5, 8.0, "ease_in_out_sine"), (1.0, 0.0, "linear")])
    elif motion == "pan_up":
        sheet.add_track("cam_scale", [(0.0, 1.10, "ease_in_out"), (1.0, 1.15, "linear")])
        sheet.add_track("cam_x", [(0.0, 0.0, "ease_in_out_sine"), (1.0, 0.0, "linear")])
        sheet.add_track("cam_y", [(0.0, 28.0, "cinematic"), (1.0, -28.0, "linear")])
    elif motion == "dolly_pulse":
        sheet.add_track("cam_scale", [(0.0, 1.02, "spring"), (0.45, 1.14, "ease_in_out_sine"), (1.0, 1.05, "linear")])
        sheet.add_track("cam_x", [(0.0, -10.0, "ease_in_out_sine"), (0.5, 10.0, "ease_in_out_sine"), (1.0, -6.0, "linear")])
        sheet.add_track("cam_y", [(0.0, 6.0, "ease_in_out_sine"), (1.0, -6.0, "linear")])
    elif motion == "dramatic_shake":
        sheet.add_track("cam_scale", [(0.0, 1.06, "ease_out_back"), (0.35, 1.16, "ease_in_out"), (1.0, 1.12, "linear")])
        sheet.add_track("cam_x", [(0.0, -14.0, "linear"), (0.25, 14.0, "linear"), (0.5, -10.0, "linear"), (0.75, 10.0, "linear"), (1.0, 0.0, "linear")])
        sheet.add_track("cam_y", [(0.0, 8.0, "linear"), (0.33, -8.0, "linear"), (0.66, 6.0, "linear"), (1.0, 0.0, "linear")])
    else:  # zoom_in default
        sheet.add_track("cam_scale", [(0.0, 1.0, "cinematic"), (1.0, 1.16, "linear")])
        sheet.add_track("cam_x", [(0.0, 0.0, "ease_in_out_sine"), (1.0, 14.0, "linear")])
        sheet.add_track("cam_y", [(0.0, 0.0, "ease_in_out_sine"), (1.0, -12.0, "linear")])

    # Shared atmospheric motion tracks
    sheet.add_track("orb_pulse", [(0.0, 0.94, "ease_in_out_sine"), (0.5, 1.08, "ease_in_out_sine"), (1.0, 0.95, "linear")])
    sheet.add_track("cloud_drift", [(0.0, -45.0, "linear"), (1.0, 55.0, "linear")])
    sheet.add_track("hero_bob", [(0.0, 0.0, "ease_in_out_sine"), (0.33, -12.0, "ease_in_out_sine"), (0.66, 8.0, "ease_in_out_sine"), (1.0, 0.0, "linear")])
    sheet.add_track("parallax_far", [(0.0, -16.0, "cinematic"), (1.0, 16.0, "linear")])
    sheet.add_track("parallax_mid", [(0.0, -34.0, "cinematic"), (1.0, 34.0, "linear")])
    sheet.add_track("parallax_near", [(0.0, -58.0, "cinematic"), (1.0, 58.0, "linear")])
    return sheet


def _build_procedural_svg_frame(
    w: int,
    h: int,
    t_sec: float,
    norm_t: float,
    vals: Dict[str, Any],
    style: str,
    idx: int,
    emitter: Optional[ParticleEmitter] = None,
) -> str:
    """Builds a single animated 6-layer vector SVG frame with parallax & character motion."""
    pal = STYLE_PALETTES.get(style, STYLE_PALETTES["animated_myth"])
    cx = w * (0.36 + (idx % 3) * 0.14)
    cy = h * 0.30
    r_orb = min(w, h) * 0.155
    orb_s = float(vals.get("orb_pulse", 1.0))
    c_drift = float(vals.get("cloud_drift", 0.0))
    p_far = float(vals.get("parallax_far", 0.0))
    p_mid = float(vals.get("parallax_mid", 0.0))
    p_near = float(vals.get("parallax_near", 0.0))
    bob = float(vals.get("hero_bob", 0.0))
    cam_s = float(vals.get("cam_scale", 1.0))
    cam_x = float(vals.get("cam_x", 0.0))
    cam_y = float(vals.get("cam_y", 0.0))

    # Twinkling stars
    star_elems = []
    for k in range(26):
        sx = (k * 173 + idx * 91) % w
        sy = (k * 97 + idx * 53) % int(h * 0.52)
        twinkle = 0.25 + 0.65 * (0.5 + 0.5 * math.sin(t_sec * (2.0 + (k % 4) * 0.7) + k))
        sr = 1.4 + (k % 3) * 0.9
        star_elems.append(f'<circle cx="{sx}" cy="{sy}" r="{sr:.1f}" fill="#ffffff" opacity="{twinkle:.2f}"/>')

    # Light rays radiating from the celestial orb
    ray_rot = (t_sec * 8.0 + idx * 17.0) % 360.0
    rays = []
    for a in range(0, 360, 45):
        rad = math.radians(a)
        x2 = cx + math.cos(rad) * r_orb * 3.1
        y2 = cy + math.sin(rad) * r_orb * 3.1
        rays.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{pal["orb"]}" stroke-width="{max(2, w // 90)}" opacity="0.11"/>')

    # Drifting clouds
    clouds = (
        f'<g transform="translate({c_drift:.1f}, 0)" opacity="0.24">'
        f'<ellipse cx="{w * 0.22:.1f}" cy="{h * 0.24:.1f}" rx="{w * 0.22:.1f}" ry="{h * 0.032:.1f}" fill="{pal["cloud"]}"/>'
        f'<ellipse cx="{w * 0.76:.1f}" cy="{h * 0.36:.1f}" rx="{w * 0.26:.1f}" ry="{h * 0.036:.1f}" fill="{pal["cloud"]}"/>'
        f'<ellipse cx="{w * 0.45:.1f}" cy="{h * 0.44:.1f}" rx="{w * 0.20:.1f}" ry="{h * 0.025:.1f}" fill="{pal["cloud"]}"/>'
        f'</g>'
    )

    # Stylized animated foreground hero silhouette (orb guardian / floating lantern / expressive mascot)
    hx = w * 0.50 + p_mid * 0.45
    hy = h * 0.62 + bob
    hero_r = min(w, h) * 0.078
    blink_scale = 0.15 if (int(t_sec * 2.5) % 7 == 0 and (t_sec * 2.5) % 1.0 < 0.22) else 1.0
    hero = (
        f'<g transform="translate({hx:.1f}, {hy:.1f})">'
        f'<ellipse cx="0" cy="{hero_r * 1.65:.1f}" rx="{hero_r * 0.9:.1f}" ry="{hero_r * 0.22:.1f}" fill="#000000" opacity="0.28"/>'
        f'<circle cx="0" cy="0" r="{hero_r * 1.45:.1f}" fill="url(#orb)" opacity="0.35"/>'
        f'<path d="M {-hero_r * 0.75:.1f} {hero_r * 1.35:.1f} Q 0 {hero_r * 0.15:.1f} {hero_r * 0.75:.1f} {hero_r * 1.35:.1f} Z" fill="{pal["near_hill"]}" stroke="{pal["accent"]}" stroke-width="2.5"/>'
        f'<circle cx="0" cy="{-hero_r * 0.15:.1f}" r="{hero_r * 0.68:.1f}" fill="{pal["mid_hill"]}" stroke="{pal["accent"]}" stroke-width="2.5"/>'
        f'<ellipse cx="{-hero_r * 0.23:.1f}" cy="{-hero_r * 0.20:.1f}" rx="{hero_r * 0.12:.1f}" ry="{hero_r * 0.14 * blink_scale:.1f}" fill="{pal["orb"]}"/>'
        f'<ellipse cx="{hero_r * 0.23:.1f}" cy="{-hero_r * 0.20:.1f}" rx="{hero_r * 0.12:.1f}" ry="{hero_r * 0.14 * blink_scale:.1f}" fill="{pal["orb"]}"/>'
        f'</g>'
    )

    particles_svg = emitter.render_svg_group(t_sec) if emitter else ""

    # Camera transform around viewport center
    half_w, half_h = w * 0.5, h * 0.5
    cam_tf = (
        f"translate({half_w + cam_x:.1f} {half_h + cam_y:.1f}) "
        f"scale({cam_s:.4f}) "
        f"translate({-half_w:.1f} {-half_h:.1f})"
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<defs>'
        f'<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{pal["sky_top"]}"/>'
        f'<stop offset="58%" stop-color="{pal["sky_mid"]}"/>'
        f'<stop offset="100%" stop-color="{pal["sky_bot"]}"/>'
        f'</linearGradient>'
        f'<radialGradient id="orb" cx="50%" cy="50%" r="50%">'
        f'<stop offset="0%" stop-color="#ffffff" stop-opacity="0.95"/>'
        f'<stop offset="45%" stop-color="{pal["orb"]}" stop-opacity="0.80"/>'
        f'<stop offset="100%" stop-color="{pal["orb"]}" stop-opacity="0"/>'
        f'</radialGradient>'
        f'</defs>'
        f'<g transform="{cam_tf}">'
        f'<rect x="-80" y="-80" width="{w + 160}" height="{h + 160}" fill="url(#sky)"/>'
        f'{"".join(star_elems)}'
        f'<g transform="rotate({ray_rot:.1f} {cx:.1f} {cy:.1f})">{"".join(rays)}</g>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_orb * 2.1 * orb_s:.1f}" fill="url(#orb)"/>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_orb * orb_s:.1f}" fill="{pal["orb"]}" opacity="0.93"/>'
        f'{clouds}'
        f'<g transform="translate({p_far:.1f}, 0)">'
        f'<path d="M -120 {h * 0.66:.1f} Q {w * 0.28:.1f} {h * 0.54:.1f} {w * 0.58:.1f} {h * 0.63:.1f} '
        f'T {w + 140} {h * 0.59:.1f} L {w + 140} {h + 80} L -120 {h + 80} Z" fill="{pal["far_hill"]}" opacity="0.88"/>'
        f'</g>'
        f'<g transform="translate({p_mid:.1f}, 0)">'
        f'<path d="M -140 {h * 0.74:.1f} Q {w * 0.35:.1f} {h * 0.65:.1f} {w * 0.70:.1f} {h * 0.73:.1f} '
        f'T {w + 160} {h * 0.70:.1f} L {w + 160} {h + 80} L -140 {h + 80} Z" fill="{pal["mid_hill"]}" opacity="0.94"/>'
        f'</g>'
        f'{hero}'
        f'<g transform="translate({p_near:.1f}, 0)">'
        f'<path d="M -180 {h * 0.83:.1f} Q {w * 0.44:.1f} {h * 0.77:.1f} {w + 180} {h * 0.85:.1f} '
        f'L {w + 180} {h + 100} L -180 {h + 100} Z" fill="{pal["near_hill"]}" opacity="0.98"/>'
        f'</g>'
        f'</g>'
        f'{particles_svg}'
        f'</svg>'
    )


def animate_existing_svg(
    base_svg: str,
    w: int,
    h: int,
    t_sec: float,
    vals: Dict[str, Any],
    emitter: Optional[ParticleEmitter] = None,
) -> Optional[str]:
    """
    Auto-rigs an existing SVG (e.g. generated by Gemini) into depth-stratified
    animated layers using Theatre.js/SVG.js transforms + optional particles.
    Returns animated SVG string or None if XML parsing fails.
    """
    try:
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        root = ET.fromstring(base_svg)
    except Exception:
        return None

    # Normalize dimensions / viewBox
    vb = root.attrib.get("viewBox") or f"0 0 {w} {h}"
    vb_parts = [float(p) for p in re.findall(r"[-+]?\d*\.?\d+", vb)[:4]]
    vw = vb_parts[2] if len(vb_parts) == 4 and vb_parts[2] > 0 else float(w)
    vh = vb_parts[3] if len(vb_parts) == 4 and vb_parts[3] > 0 else float(h)
    root.attrib["width"] = str(w)
    root.attrib["height"] = str(h)
    root.attrib["viewBox"] = f"0 0 {vw:g} {vh:g}"

    # Partition drawable children into 3 depth buckets (background, midground, foreground)
    defs_nodes = []
    drawable_nodes = []
    for child in list(root):
        tag = child.tag.split("}")[-1].lower()
        if tag in ("defs", "style", "metadata", "title", "desc"):
            defs_nodes.append(child)
        else:
            drawable_nodes.append(child)
        root.remove(child)

    for d in defs_nodes:
        root.append(d)

    if not drawable_nodes:
        return None

    n = len(drawable_nodes)
    split1 = max(1, n // 3)
    split2 = max(split1 + 1, (2 * n) // 3) if n >= 3 else n

    cam_s = float(vals.get("cam_scale", 1.0))
    cam_x = float(vals.get("cam_x", 0.0)) * (vw / max(1.0, float(w)))
    cam_y = float(vals.get("cam_y", 0.0)) * (vh / max(1.0, float(h)))
    p_mid = float(vals.get("parallax_mid", 0.0)) * 0.45 * (vw / max(1.0, float(w)))
    p_near = float(vals.get("parallax_near", 0.0)) * 0.55 * (vw / max(1.0, float(w)))
    bob = float(vals.get("hero_bob", 0.0)) * 0.65 * (vh / max(1.0, float(h)))

    half_w, half_h = vw * 0.5, vh * 0.5
    cam_g = ET.SubElement(
        root,
        "{http://www.w3.org/2000/svg}g",
        {
            "id": "raptar-camera",
            "transform": (
                f"translate({half_w + cam_x:.2f} {half_h + cam_y:.2f}) "
                f"scale({cam_s:.4f}) "
                f"translate({-half_w:.2f} {-half_h:.2f})"
            ),
        },
    )

    bg_g = ET.SubElement(cam_g, "{http://www.w3.org/2000/svg}g", {"id": "layer-bg"})
    mid_g = ET.SubElement(
        cam_g,
        "{http://www.w3.org/2000/svg}g",
        {"id": "layer-mid", "transform": f"translate({p_mid:.2f}, 0)"},
    )
    fg_g = ET.SubElement(
        cam_g,
        "{http://www.w3.org/2000/svg}g",
        {"id": "layer-fg", "transform": f"translate({p_near:.2f}, {bob:.2f})"},
    )

    for idx_child, node in enumerate(drawable_nodes):
        if idx_child < split1:
            bg_g.append(node)
        elif idx_child < split2:
            mid_g.append(node)
        else:
            fg_g.append(node)

    svg_str = ET.tostring(root, encoding="unicode")
    if emitter is not None:
        # Scale emitter coordinates into the SVG's viewBox
        scaled_emitter = ParticleEmitter(emitter.preset, int(vw), int(vh), seed=99, count=len(emitter.particles))
        p_svg = scaled_emitter.render_svg_group(t_sec)
        svg_str = svg_str.replace("</svg>", f"{p_svg}</svg>")
    return svg_str


# ============================================================================
# 4. Natron-inspired Node-Graph Video Compositor, Grading & Transition Engine
# ============================================================================

NATRON_GRADE_PRESETS: Dict[str, str] = {
    "eerie_vignette": (
        "eq=contrast=1.14:saturation=0.78:brightness=-0.03,"
        "colorbalance=bs=0.06:gs=-0.02:rs=-0.02,"
        "vignette=angle=PI/3.6"
    ),
    "warm_glow": (
        "eq=contrast=1.08:saturation=1.24:brightness=0.02,"
        "colorbalance=rs=0.04:gs=0.02:rm=0.05:bm=-0.03,"
        "unsharp=5:5:0.45:5:5:0.0,vignette=angle=PI/5.2"
    ),
    "golden_glow": (
        "eq=contrast=1.08:saturation=1.25:brightness=0.02,"
        "colorbalance=rs=0.05:gs=0.03:rm=0.06:bm=-0.04,"
        "unsharp=5:5:0.45:5:5:0.0,vignette=angle=PI/5.2"
    ),
    "sparkles": (
        "eq=contrast=1.07:saturation=1.26:brightness=0.02,"
        "unsharp=5:5:0.5:5:5:0.0"
    ),
    "vibrant": (
        "eq=contrast=1.10:saturation=1.30:brightness=0.01,"
        "unsharp=5:5:0.45:5:5:0.0,vignette=angle=PI/6.0"
    ),
    "anime_neon": (
        "eq=contrast=1.12:saturation=1.32:brightness=0.01,"
        "colorbalance=bs=0.04:rm=0.03:bm=0.05,"
        "unsharp=5:5:0.55:5:5:0.0,vignette=angle=PI/5.5"
    ),
    "cinematic": (
        "eq=contrast=1.07:saturation=1.14,"
        "colorbalance=bs=0.03:rh=0.03:gh=0.01,"
        "unsharp=5:5:0.35:5:5:0.0,vignette=angle=PI/5.8"
    ),
}


def get_grade_filter(fx: str, style: str = "") -> str:
    """Returns a Natron-style FFmpeg color grading + optical polish chain."""
    key = (fx or "").strip().lower()
    if key in NATRON_GRADE_PRESETS:
        return NATRON_GRADE_PRESETS[key]
    st = (style or "").strip().lower()
    if st == "animated_anime":
        return NATRON_GRADE_PRESETS["anime_neon"]
    if st in ("horror", "thriller", "mystery"):
        return NATRON_GRADE_PRESETS["eerie_vignette"]
    if st in ("animated_myth", "legend"):
        return NATRON_GRADE_PRESETS["warm_glow"]
    return NATRON_GRADE_PRESETS["cinematic"]


@dataclass
class CompositorNode:
    kind: str
    params: Dict[str, Any] = field(default_factory=dict)

    def to_ffmpeg(self) -> str:
        if self.kind == "scale_crop":
            w, h = self.params["w"], self.params["h"]
            flags = self.params.get("flags", "bicubic")
            return f"scale={w}:{h}:force_original_aspect_ratio=increase:flags={flags},crop={w}:{h}"
        if self.kind == "grade":
            return get_grade_filter(self.params.get("fx", "cinematic"), self.params.get("style", ""))
        if self.kind == "fps":
            return f"fps={int(self.params.get('fps', 30))}"
        if self.kind == "sar":
            return "setsar=1"
        if self.kind == "fade_io":
            dur = float(self.params.get("duration", 4.0))
            fi = float(self.params.get("fade_in", 0.25))
            fo = float(self.params.get("fade_out", 0.25))
            parts = []
            if fi > 0:
                parts.append(f"fade=t=in:st=0:d={fi:.3f}")
            if fo > 0 and dur > fo + 0.1:
                parts.append(f"fade=t=out:st={max(0.0, dur - fo):.3f}:d={fo:.3f}")
            return ",".join(parts) if parts else "null"
        if self.kind == "raw":
            return str(self.params.get("filter", "null"))
        return "null"


class CompositorGraph:
    """Natron-inspired composable node graph compiling to an FFmpeg filter string."""

    def __init__(self) -> None:
        self.nodes: List[CompositorNode] = []

    def add(self, kind: str, **params: Any) -> "CompositorGraph":
        self.nodes.append(CompositorNode(kind=kind, params=params))
        return self

    def compile(self) -> str:
        parts = [n.to_ffmpeg() for n in self.nodes]
        clean = [p for p in parts if p and p != "null"]
        return ",".join(clean) or "null"


def build_audio_master_filter(total_dur: float) -> str:
    """Broadcast-grade voice mastering filterchain (highpass + dynamics + exact trim)."""
    return (
        f"highpass=f=75,"
        f"acompressor=threshold=-18dB:ratio=2.4:attack=15:release=180:makeup=2,"
        f"apad,atrim=0:{total_dur:.3f}"
    )


def _probe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    try:
        return max(0.1, float(r.stdout.strip()))
    except Exception:
        return 0.0


def _pick_transitions_for_style(style: str) -> List[str]:
    """Returns FFmpeg 4.4+ compatible xfade transitions matched to genre energy."""
    st = (style or "").lower()
    if st in ("horror", "thriller", "mystery"):
        return ["fadeblack", "fade", "radial", "fadeblack"]
    if st in ("animated_comedy", "fable"):
        return ["smoothleft", "circleopen", "smoothright", "smoothup"]
    if st == "animated_anime":
        return ["smoothleft", "radial", "smoothright", "fade"]
    if st in ("animated_myth", "legend"):
        return ["fade", "smoothup", "radial", "fadeblack"]
    return ["fade", "smoothleft", "smoothright", "fade"]


def render_animated_svg_scene(
    out_path: Path,
    width: int,
    height: int,
    duration: float,
    fps: int = 30,
    style: str = "animated_myth",
    idx: int = 0,
    motion: str = "zoom_in",
    fx: str = "cinematic",
    base_svg: Optional[str] = None,
    enable_particles: bool = True,
    svg_fps: int = 15,
    render_scale: float = 0.5,
) -> bool:
    """
    Renders a genuine multi-frame animated SVG vector scene into a CFR H.264 MP4.
    Uses Theatre.js keyframe curves + SVG.js multi-layer motion + Effekseer particles
    + Natron grading graph, compiled via FFmpeg librsvg.
    """
    duration = max(0.4, float(duration))
    svg_fps = max(8, min(fps, int(svg_fps)))
    scale = max(0.35, min(1.0, float(render_scale)))
    rw = max(256, int(round(width * scale / 2.0)) * 2)
    rh = max(256, int(round(height * scale / 2.0)) * 2)
    n_frames = max(2, int(math.ceil(duration * svg_fps)))

    sheet = build_scene_motion_sheet(duration, motion=motion)
    preset = pick_particle_preset(style, fx)
    seed = int(hashlib.md5(f"{style}:{idx}:{motion}".encode("utf-8")).hexdigest()[:8], 16)
    emitter = ParticleEmitter(preset, rw, rh, seed=seed) if enable_particles else None

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"raptar_svg_{idx}_"))
    try:
        use_base = bool(base_svg and "<svg" in base_svg.lower())
        for f_idx in range(n_frames):
            t_sec = f_idx / float(svg_fps)
            norm_t = min(1.0, t_sec / max(1e-6, duration))
            vals = sheet.sample(norm_t)
            svg_text = None
            if use_base and base_svg:
                svg_text = animate_existing_svg(base_svg, rw, rh, t_sec, vals, emitter=emitter)
                if svg_text is None:
                    use_base = False
            if not svg_text:
                svg_text = _build_procedural_svg_frame(
                    rw, rh, t_sec, norm_t, vals, style=style, idx=idx, emitter=emitter
                )
            (tmp_dir / f"frame_{f_idx:04d}.svg").write_text(svg_text, encoding="utf-8")

        graph = (
            CompositorGraph()
            .add("scale_crop", w=width, h=height, flags="bicubic")
            .add("grade", fx=fx, style=style)
            .add("fps", fps=fps)
            .add("sar")
        )
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(svg_fps),
            "-i", str(tmp_dir / "frame_%04d.svg"),
            "-t", f"{duration:.3f}",
            "-vf", graph.compile(),
            "-an",
            "-r", str(fps), "-vsync", "cfr", "-video_track_timescale", "90000",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            str(out_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 1000
    except Exception as e:
        print(f"  [MotionEngine] SVG sequence render fallback: {type(e).__name__}: {e}")
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def composite_particles_onto_video(
    src_video: Path,
    out_video: Path,
    width: int,
    height: int,
    duration: float,
    style: str = "animated_myth",
    fx: str = "cinematic",
    idx: int = 0,
    fps: int = 30,
    overlay_fps: int = 12,
) -> bool:
    """
    Composites a transparent Effekseer-style particle VFX layer onto an existing
    AI-generated or Ken Burns video clip using Natron-style alpha Merge.
    """
    duration = max(0.4, float(duration))
    rw = max(240, int(round(width * 0.5 / 2.0)) * 2)
    rh = max(240, int(round(height * 0.5 / 2.0)) * 2)
    n_frames = max(2, int(math.ceil(duration * overlay_fps)))
    preset = pick_particle_preset(style, fx)
    seed = int(hashlib.md5(f"ov:{style}:{idx}".encode("utf-8")).hexdigest()[:8], 16)
    # Slightly subtler particle count so real AI video artwork stays front-and-center
    emitter = ParticleEmitter(preset, rw, rh, seed=seed, count=18 if preset != "volumetric_mist" else 9)

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"raptar_vfx_{idx}_"))
    try:
        for f_idx in range(n_frames):
            t_sec = f_idx / float(overlay_fps)
            svg = (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{rw}" height="{rh}" viewBox="0 0 {rw} {rh}">'
                f'{emitter.render_svg_group(t_sec)}'
                f'</svg>'
            )
            (tmp_dir / f"p_{f_idx:04d}.svg").write_text(svg, encoding="utf-8")

        fc = (
            f"[1:v]format=rgba,scale={width}:{height}:flags=bilinear,fps={fps}[ov];"
            f"[0:v][ov]overlay=0:0:shortest=1,format=yuv420p[v]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", str(src_video),
            "-framerate", str(overlay_fps),
            "-i", str(tmp_dir / "p_%04d.svg"),
            "-filter_complex", fc,
            "-map", "[v]", "-an",
            "-t", f"{duration:.3f}",
            "-r", str(fps), "-vsync", "cfr", "-video_track_timescale", "90000",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
            str(out_video),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return res.returncode == 0 and out_video.exists() and out_video.stat().st_size > 1000
    except Exception as e:
        print(f"  [MotionEngine] Particle composite skipped: {type(e).__name__}: {e}")
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def join_scenes_with_transitions(
    scene_paths: Sequence[Path],
    out_path: Path,
    style: str = "animated_myth",
    fps: int = 30,
    transition_dur: float = 0.30,
) -> bool:
    """
    Joins multiple scene MP4s with Natron-style smooth FFmpeg xfade + acrossfade
    transitions. Automatically clamps transition duration for short clips and
    returns False on error so callers can fall back to lossless concat.
    """
    paths = [Path(p) for p in scene_paths if Path(p).exists()]
    if len(paths) < 2 or len(paths) > 16:
        return False

    durs = [_probe_duration(p) for p in paths]
    min_dur = min(durs)
    if min_dur < 0.7:
        return False
    td = max(0.15, min(float(transition_dur), min_dur * 0.30))

    transitions = _pick_transitions_for_style(style)
    cmd = ["ffmpeg", "-y"]
    for p in paths:
        cmd.extend(["-i", str(p)])

    v_filters: List[str] = []
    a_filters: List[str] = []

    # Normalize each input stream timebase/format cleanly before xfade
    for i in range(len(paths)):
        v_filters.append(f"[{i}:v]settb=AVTB,fps={fps},format=yuv420p[v{i}]")
        a_filters.append(f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo[a{i}]")

    cur_v = "[v0]"
    cur_a = "[a0]"
    running_dur = durs[0]

    for i in range(1, len(paths)):
        offset = max(0.05, running_dur - td)
        tr = transitions[(i - 1) % len(transitions)]
        next_v = f"[vx{i}]" if i < len(paths) - 1 else "[vout]"
        next_a = f"[ax{i}]" if i < len(paths) - 1 else "[aout]"
        v_filters.append(f"{cur_v}[v{i}]xfade=transition={tr}:duration={td:.3f}:offset={offset:.3f}{next_v}")
        a_filters.append(f"{cur_a}[a{i}]acrossfade=d={td:.3f}:c1=tri:c2=tri{next_a}")
        cur_v = next_v
        cur_a = next_a
        running_dur = offset + durs[i]

    fc = ";".join(v_filters + a_filters)
    cmd.extend([
        "-filter_complex", fc,
        "-map", "[vout]", "-map", "[aout]",
        "-r", str(fps), "-vsync", "cfr", "-video_track_timescale", "90000",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        str(out_path),
    ])
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 1000
    except Exception as e:
        print(f"  [MotionEngine] xfade transition fallback: {type(e).__name__}: {e}")
        return False


# ============================================================================
# 5. Synfig Studio (.sif) Keyframe Project Exporter & Optional CLI Hook
# ============================================================================

def _hex_to_synfig_rgb(hex_color: str) -> Tuple[float, float, float]:
    r, g, b = _hex_to_rgb(hex_color)
    return round(r / 255.0, 4), round(g / 255.0, 4), round(b / 255.0, 4)


def export_synfig_sif(
    sif_path: Path,
    width: int,
    height: int,
    duration: float,
    fps: int = 30,
    style: str = "animated_myth",
    title: str = "RAPTAR Scene",
) -> Path:
    """
    Exports a standards-compliant Synfig Studio `.sif` XML keyframe canvas
    (inspired by synfig/synfig) with animated waypoints so scenes can be rendered
    via `synfig` CLI or opened directly in Synfig Studio for further 2D polish.
    """
    pal = STYLE_PALETTES.get(style, STYLE_PALETTES["animated_myth"])
    r1, g1, b1 = _hex_to_synfig_rgb(pal["sky_top"])
    r2, g2, b2 = _hex_to_synfig_rgb(pal["sky_bot"])
    ro, go, bo = _hex_to_synfig_rgb(pal["orb"])

    aspect = width / max(1.0, float(height))
    vh = 4.5
    vw = round(vh * aspect, 4)
    end_frames = max(1, int(round(duration * fps)))
    safe_title = re.sub(r"[<>&\"']", "", title or "RAPTAR Scene")

    sif_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<canvas version="1.0" width="{width}" height="{height}" xres="2834.645752" yres="2834.645752" view-box="{-vw:.4f} {vh:.4f} {vw:.4f} {-vh:.4f}" antialias="1" fps="{fps:.3f}" begin-time="0f" end-time="{end_frames}f" bgcolor="0.0 0.0 0.0 1.0">
  <name>{safe_title}</name>
  <keyframe time="0f">Start</keyframe>
  <keyframe time="{end_frames // 2}f">Midpoint</keyframe>
  <keyframe time="{end_frames}f">End</keyframe>
  <layer type="linear_gradient" active="true" version="0.1" desc="SkyGradient">
    <param name="z_depth"><real value="0.0"/></param>
    <param name="amount"><real value="1.0"/></param>
    <param name="blend_method"><integer value="0"/></param>
    <param name="p1"><vector><x>0.0</x><y>{vh:.4f}</y></vector></param>
    <param name="p2"><vector><x>0.0</x><y>{-vh:.4f}</y></vector></param>
    <param name="gradient">
      <gradient>
        <color pos="0.0"><r>{r1}</r><g>{g1}</g><b>{b1}</b><a>1.0</a></color>
        <color pos="1.0"><r>{r2}</r><g>{g2}</g><b>{b2}</b><a>1.0</a></color>
      </gradient>
    </param>
  </layer>
  <layer type="circle" active="true" version="0.2" desc="AnimatedCelestialOrb">
    <param name="z_depth"><real value="0.0"/></param>
    <param name="amount"><real value="0.92"/></param>
    <param name="blend_method"><integer value="0"/></param>
    <param name="color"><color><r>{ro}</r><g>{go}</g><b>{bo}</b><a>1.0</a></color></param>
    <param name="radius">
      <animated type="real">
        <waypoint time="0f" before="clamped" after="clamped"><real value="0.72"/></waypoint>
        <waypoint time="{end_frames // 2}f" before="clamped" after="clamped"><real value="0.88"/></waypoint>
        <waypoint time="{end_frames}f" before="clamped" after="clamped"><real value="0.75"/></waypoint>
      </animated>
    </param>
    <param name="origin">
      <animated type="vector">
        <waypoint time="0f" before="clamped" after="clamped"><vector><x>-0.45</x><y>1.25</y></vector></waypoint>
        <waypoint time="{end_frames}f" before="clamped" after="clamped"><vector><x>0.45</x><y>1.55</y></vector></waypoint>
      </animated>
    </param>
  </layer>
</canvas>
"""
    sif_path = Path(sif_path)
    sif_path.parent.mkdir(parents=True, exist_ok=True)
    sif_path.write_text(sif_xml, encoding="utf-8")
    return sif_path


def render_via_synfig_cli(sif_path: Path, out_mp4: Path, width: int, height: int, fps: int = 30) -> bool:
    """
    Optional headless Synfig Studio CLI render backend.
    Executes only when `synfig` binary is installed on the host and enabled.
    """
    synfig_bin = shutil.which("synfig")
    if not synfig_bin:
        return False
    try:
        res = subprocess.run(
            [
                synfig_bin,
                "-t", "ffmpeg",
                "-w", str(width),
                "-h", str(height),
                "--fps", str(fps),
                "-o", str(out_mp4),
                str(sif_path),
            ],
            capture_output=True, text=True, timeout=180,
        )
        return res.returncode == 0 and out_mp4.exists() and out_mp4.stat().st_size > 1000
    except Exception:
        return False
