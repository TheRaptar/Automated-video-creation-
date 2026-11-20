#!/usr/bin/env python3
"""
Multi-Character Voice Studio, Procedural Foley SFX, Ambient BGM & Audio Mixer.

Zero-cost, copyright-safe audio pipeline:
  - Voice Synthesis:
      1. Edge-TTS neural voices with per-character voice ID, pitch (+Hz/-Hz),
         and speaking rate across Hindi, Tamil, English, and 11+ languages.
      2. Optional offline local Piper TTS CLI (`OHF-Voice/piper1-gpl`) when
         installed and configured via PIPER_MODEL_PATH.
      3. Deterministic offline synthetic voice envelope when OFFLINE_TEST=1
         so tests exercise real audio mixing & lip-sync without network access.
  - Procedural Foley SFX (100% copyright-free FFmpeg DSP synthesis):
      whoosh, impact_boom, shock_hit, footsteps, laughter_chime, sparkle,
      thunder, door_open, engine_rev, suspense_riser.
  - Procedural Background Music Beds (100% copyright-free FFmpeg synthesis):
      epic_myth, comedy_bounce, horror_drone, anime_lofi, action_beat, heartwarming_pad.
  - Multi-Track Mixing:
      Concatenates multi-character dialogue turns with exact timestamps, mixes
      timed SFX cues, blends ducked BGM under narration, and masters output.
  - Audio Amplitude Envelope Extractor:
      Extracts per-frame normalized RMS mouth-openness values [0.0..1.0] from
      any MP3/WAV track for genuine audio-synchronized 2D lip-sync animation.
"""

from __future__ import annotations

import asyncio
import math
import os
import shutil
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    from character_manager import CharacterBible, CharacterProfile
except ImportError:
    CharacterBible = None
    CharacterProfile = None


@dataclass
class DialogueTurn:
    speaker: str
    text: str
    emotion: str = "neutral"
    start_sec: float = 0.0
    end_sec: float = 0.0
    audio_path: Optional[Path] = None


def probe_audio_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    try:
        return max(0.15, float(r.stdout.strip()))
    except Exception:
        return 0.5


def _run_ffmpeg(cmd: Sequence[str], timeout: int = 120) -> bool:
    r = subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout)
    return r.returncode == 0


async def _edge_tts_async(text: str, out_path: Path, voice: str, rate: str, pitch: str) -> None:
    import edge_tts
    comm = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
    await comm.save(str(out_path))


def _synthesize_piper_cli(text: str, out_wav: Path, model_path: str) -> bool:
    """Optional offline local neural TTS via Piper (OHF-Voice/piper1-gpl)."""
    piper_bin = shutil.which("piper")
    if not (piper_bin and model_path and Path(model_path).exists()):
        return False
    try:
        r = subprocess.run(
            [piper_bin, "--model", model_path, "--output_file", str(out_wav)],
            input=text, text=True, capture_output=True, timeout=60,
        )
        return r.returncode == 0 and out_wav.exists() and out_wav.stat().st_size > 200
    except Exception:
        return False


def _synthesize_offline_speech_envelope(text: str, out_path: Path, base_freq: float = 190.0) -> float:
    """Generates a syllable-modulated offline tone track so lip-sync & audio mixing are genuinely testable."""
    words = max(2, len((text or "").split()))
    dur = max(1.2, min(14.0, words * 0.36))
    # Modulated formant-like wave mimicking speech cadence (syllable bursts + pauses)
    expr = (
        f"0.18*sin(2*PI*{base_freq:.1f}*t)"
        f"+0.08*sin(2*PI*{base_freq * 1.5:.1f}*t)"
        f"*max(0,sin(2*PI*3.4*t))"
    )
    ok = _run_ffmpeg([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"aevalsrc='{expr}':s=44100:d={dur:.2f}",
        "-af", "lowpass=f=1400,afade=t=in:st=0:d=0.05,afade=t=out:st=" + f"{max(0.1, dur - 0.08):.2f}:d=0.08",
        "-c:a", "libmp3lame", "-q:a", "6", str(out_path),
    ])
    if not ok:
        _run_ffmpeg([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", f"{dur:.2f}", "-c:a", "libmp3lame", "-q:a", "8", str(out_path),
        ])
    return probe_audio_duration(out_path)


def synthesize_voice_line(
    text: str,
    out_path: Path,
    voice: str = "en-US-GuyNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz",
    offline: bool = False,
    piper_model: str = "",
) -> float:
    """Synthesizes a single character voice line via Piper (if configured), Edge-TTS, or offline test envelope."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    clean_text = (text or "").strip() or "..."

    if offline:
        freq = 250.0 if ("+" in pitch and not pitch.startswith("+0")) else (140.0 if "-" in pitch else 190.0)
        return _synthesize_offline_speech_envelope(clean_text, out_path, base_freq=freq)

    # 1. Optional local Piper TTS (offline neural, GPL-3.0)
    pm = piper_model or os.environ.get("PIPER_MODEL_PATH", "")
    if pm and os.environ.get("TTS_ENGINE", "edge").lower() == "piper":
        wav_tmp = out_path.with_suffix(".piper.wav")
        if _synthesize_piper_cli(clean_text, wav_tmp, pm):
            _run_ffmpeg(["ffmpeg", "-y", "-i", str(wav_tmp), "-c:a", "libmp3lame", "-q:a", "4", str(out_path)])
            wav_tmp.unlink(missing_ok=True)
            if out_path.exists() and out_path.stat().st_size > 200:
                return probe_audio_duration(out_path)

    # 2. Primary free cloud neural TTS: Edge-TTS with per-character voice + pitch + rate
    for attempt in range(3):
        try:
            asyncio.run(_edge_tts_async(clean_text, out_path, voice=voice, rate=rate, pitch=pitch))
            if out_path.exists() and out_path.stat().st_size > 200:
                return probe_audio_duration(out_path)
        except Exception as e:
            if attempt == 2:
                print(f"  [AudioStudio] Edge-TTS failed ({voice}): {type(e).__name__}: {e}")
    return _synthesize_offline_speech_envelope(clean_text, out_path)


# ============================================================================
# Procedural Copyright-Free Foley SFX & Genre BGM Synthesis (FFmpeg DSP)
# ============================================================================

def synthesize_sfx(sfx_name: str, out_wav: Path) -> Optional[Path]:
    """Generates clean, copyright-free procedural sound effects using FFmpeg DSP."""
    name = (sfx_name or "").lower().strip()
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    recipes: Dict[str, Tuple[str, str, float]] = {
        "impact_boom": (
            "aevalsrc='0.75*sin(2*PI*(95*exp(-3.5*t)+28)*t)*exp(-2.8*t)':s=44100:d=0.95",
            "lowpass=f=240,acompressor=threshold=-12dB:ratio=4",
            0.95,
        ),
        "shock_hit": (
            "aevalsrc='0.65*sin(2*PI*(180*exp(-4*t)+42)*t)*exp(-2.2*t)+0.25*sin(2*PI*520*t)*exp(-6*t)':s=44100:d=1.1",
            "lowpass=f=900,aecho=0.8:0.7:60:0.4",
            1.1,
        ),
        "whoosh": (
            "anoisesrc=color=pink:amplitude=0.45:d=0.75:r=44100",
            "bandpass=f=700:width_type=h:w=500,afade=t=in:st=0:d=0.28,afade=t=out:st=0.35:d=0.40",
            0.75,
        ),
        "footsteps": (
            "aevalsrc='0.55*sin(2*PI*85*t)*exp(-25*mod(t,0.38))':s=44100:d=1.55",
            "lowpass=f=320",
            1.55,
        ),
        "sparkle": (
            "aevalsrc='0.35*(sin(2*PI*1046.5*t)+0.7*sin(2*PI*1318.5*t)+0.5*sin(2*PI*1568*t))*exp(-3.2*t)':s=44100:d=0.9",
            "aecho=0.7:0.6:55:0.35",
            0.9,
        ),
        "laughter_chime": (
            "aevalsrc='0.35*sin(2*PI*(520+160*sin(2*PI*7*t))*t)*exp(-2.2*t)':s=44100:d=0.95",
            "highpass=f=280,lowpass=f=2200",
            0.95,
        ),
        "thunder": (
            "anoisesrc=color=brown:amplitude=0.7:d=1.8:r=44100",
            "lowpass=f=180,afade=t=in:st=0:d=0.15,afade=t=out:st=0.8:d=1.0",
            1.8,
        ),
        "door_open": (
            "aevalsrc='0.4*sin(2*PI*(210+120*t)*t)*exp(-2.5*t)':s=44100:d=0.8",
            "bandpass=f=420:width_type=h:w=300",
            0.8,
        ),
        "engine_rev": (
            "aevalsrc='0.42*(sin(2*PI*(65+95*t)*t)+0.4*sin(2*PI*(130+190*t)*t))*exp(-0.9*t)':s=44100:d=1.2",
            "lowpass=f=500,afade=t=out:st=0.85:d=0.35",
            1.2,
        ),
        "suspense_riser": (
            "aevalsrc='0.32*sin(2*PI*(110+260*t*t)*t)*(t/1.6)':s=44100:d=1.6",
            "lowpass=f=1200,aecho=0.8:0.7:80:0.4",
            1.6,
        ),
    }

    if name not in recipes:
        name = "whoosh"
    src_expr, af, dur = recipes[name]
    ok = _run_ffmpeg([
        "ffmpeg", "-y", "-f", "lavfi", "-i", src_expr,
        "-t", f"{dur:.2f}", "-af", af,
        "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(out_wav),
    ])
    return out_wav if (ok and out_wav.exists() and out_wav.stat().st_size > 200) else None


def synthesize_bgm_bed(mood: str, duration: float, out_wav: Path) -> Optional[Path]:
    """Generates a gentle, loopable, 100% copyright-free ambient/beat background music bed."""
    dur = max(1.5, float(duration))
    m = (mood or "epic_myth").lower().strip()
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    # Chord & pulse synthesis via FFmpeg aevalsrc (completely original, zero copyright risk)
    beds: Dict[str, str] = {
        "epic_myth": (
            "0.12*sin(2*PI*146.83*t)+0.09*sin(2*PI*220.0*t)+0.07*sin(2*PI*293.66*t)"
            "+0.05*sin(2*PI*329.63*t)*(0.5+0.5*sin(2*PI*0.35*t))"
        ),
        "comedy_bounce": (
            "0.11*sin(2*PI*261.63*t)*(0.5+0.5*sin(2*PI*2.2*t))"
            "+0.08*sin(2*PI*329.63*t)*(0.5+0.5*sin(2*PI*4.4*t))"
            "+0.07*sin(2*PI*392.0*t)"
        ),
        "horror_drone": (
            "0.14*sin(2*PI*65.41*t)+0.11*sin(2*PI*69.30*t)"
            "+0.06*sin(2*PI*130.81*t)*(0.5+0.5*sin(2*PI*0.25*t))"
        ),
        "anime_lofi": (
            "0.10*sin(2*PI*220.0*t)+0.08*sin(2*PI*261.63*t)+0.07*sin(2*PI*329.63*t)"
            "+0.06*sin(2*PI*392.0*t)*(0.5+0.5*sin(2*PI*0.6*t))"
        ),
        "action_beat": (
            "0.16*sin(2*PI*(90*exp(-12*mod(t,0.5))+45)*t)*exp(-8*mod(t,0.5))"
            "+0.09*sin(2*PI*110.0*t)+0.07*sin(2*PI*164.81*t)"
        ),
        "heartwarming_pad": (
            "0.10*sin(2*PI*196.0*t)+0.08*sin(2*PI*246.94*t)+0.07*sin(2*PI*293.66*t)"
            "+0.05*sin(2*PI*392.0*t)*(0.5+0.5*sin(2*PI*0.4*t))"
        ),
    }
    expr = beds.get(m, beds["epic_myth"])
    fade_out_st = max(0.2, dur - 0.6)
    af = f"lowpass=f=1800,aecho=0.7:0.6:90:0.3,afade=t=in:st=0:d=0.45,afade=t=out:st={fade_out_st:.2f}:d=0.55"
    ok = _run_ffmpeg([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"aevalsrc='{expr}':s=44100:d={dur:.2f}",
        "-t", f"{dur:.2f}", "-af", af,
        "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(out_wav),
    ])
    return out_wav if (ok and out_wav.exists() and out_wav.stat().st_size > 200) else None


def map_style_to_bgm_mood(style: str) -> str:
    s = (style or "").lower()
    if any(k in s for k in ("horror", "thriller", "mystery")):
        return "horror_drone"
    if any(k in s for k in ("comedy", "cartoon", "funny")):
        return "comedy_bounce"
    if any(k in s for k in ("action", "adventure", "scifi")):
        return "action_beat"
    if "anime" in s:
        return "anime_lofi"
    if any(k in s for k in ("child", "fable", "emotion", "romance")):
        return "heartwarming_pad"
    return "epic_myth"


def build_scene_dialogue_and_mix(
    dialogue_lines: Sequence[Dict[str, Any]],
    bible: Optional[Any],
    work_dir: Path,
    scene_idx: int,
    out_audio: Path,
    lang: str = "en",
    style: str = "animated_myth",
    sfx_cues: Optional[Sequence[str]] = None,
    enable_bgm: bool = True,
    offline: bool = False,
) -> Tuple[float, List[DialogueTurn]]:
    """
    Synthesizes multi-character dialogue turns sequentially with character-specific
    voices, overlays timed copyright-free SFX & ducked BGM, and returns:
      (total_duration_sec, list_of_timed_DialogueTurns)
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    turns: List[DialogueTurn] = []
    part_files: List[Path] = []
    cursor = 0.0
    gap_sec = 0.16

    for j, item in enumerate(dialogue_lines):
        speaker = str(item.get("speaker") or "Narrator").strip()
        text = str(item.get("text") or "").strip()
        emotion = str(item.get("emotion") or "neutral").strip().lower()
        if not text:
            continue

        voice, pitch, rate = "en-US-GuyNeural", "+0Hz", "+0%"
        if bible is not None:
            prof = bible.get(speaker)
            if prof is not None:
                voice, pitch, rate = prof.voice_id, prof.voice_pitch, prof.voice_rate
            else:
                from character_manager import assign_character_voice
                voice, pitch, rate = assign_character_voice("narrator", lang=lang)

        turn_mp3 = work_dir / f"s{scene_idx}_t{j}.mp3"
        dur = synthesize_voice_line(text, turn_mp3, voice=voice, rate=rate, pitch=pitch, offline=offline)
        # Pad tiny natural breathing pause between character turns
        turn_wav = work_dir / f"s{scene_idx}_t{j}.wav"
        _run_ffmpeg([
            "ffmpeg", "-y", "-i", str(turn_mp3),
            "-af", f"apad=pad_dur={gap_sec:.2f}",
            "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(turn_wav),
        ])
        actual_dur = probe_audio_duration(turn_wav)
        turns.append(DialogueTurn(
            speaker=speaker, text=text, emotion=emotion,
            start_sec=cursor, end_sec=cursor + dur, audio_path=turn_mp3,
        ))
        part_files.append(turn_wav)
        cursor += actual_dur

    if not part_files:
        fallback = work_dir / f"s{scene_idx}_fallback.mp3"
        dur = _synthesize_offline_speech_envelope("Scene narration", fallback)
        shutil.copyfile(fallback, out_audio)
        return dur, turns

    # Concatenate character dialogue turns cleanly into one voice stem
    voice_stem = work_dir / f"s{scene_idx}_voice_stem.wav"
    if len(part_files) == 1:
        shutil.copyfile(part_files[0], voice_stem)
    else:
        lst = work_dir / f"s{scene_idx}_voice_list.txt"
        lst.write_text("".join(f"file '{p.name}'\n" for p in part_files), encoding="utf-8")
        _run_ffmpeg([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
            "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(voice_stem),
        ])

    total_dur = probe_audio_duration(voice_stem)

    # Optional SFX + BGM multi-track mix
    extra_inputs: List[Tuple[Path, float, float]] = []  # (path, delay_ms, volume)
    if enable_bgm:
        bgm_wav = synthesize_bgm_bed(map_style_to_bgm_mood(style), total_dur + 0.3, work_dir / f"s{scene_idx}_bgm.wav")
        if bgm_wav:
            extra_inputs.append((bgm_wav, 0.0, 0.24))

    for k, sfx_name in enumerate((sfx_cues or [])[:2]):
        sfx_wav = synthesize_sfx(sfx_name, work_dir / f"s{scene_idx}_sfx_{k}.wav")
        if sfx_wav:
            delay_ms = 50.0 if k == 0 else max(250.0, (total_dur * 0.55) * 1000.0)
            extra_inputs.append((sfx_wav, delay_ms, 0.42))

    if not extra_inputs:
        _run_ffmpeg([
            "ffmpeg", "-y", "-i", str(voice_stem),
            "-af", f"highpass=f=75,acompressor=threshold=-18dB:ratio=2.4:attack=15:release=180:makeup=2,atrim=0:{total_dur:.3f}",
            "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-q:a", "3", str(out_audio),
        ])
        return probe_audio_duration(out_audio), turns

    cmd = ["ffmpeg", "-y", "-i", str(voice_stem)]
    fc_parts = [
        "[0:a]highpass=f=75,acompressor=threshold=-18dB:ratio=2.4:attack=15:release=180:makeup=2,volume=1.05[v0]"
    ]
    mix_labels = ["[v0]"]
    for idx_in, (epath, delay_ms, vol) in enumerate(extra_inputs, start=1):
        cmd.extend(["-i", str(epath)])
        d_int = int(max(0, round(delay_ms)))
        fc_parts.append(f"[{idx_in}:a]adelay={d_int}|{d_int},volume={vol:.2f}[e{idx_in}]")
        mix_labels.append(f"[e{idx_in}]")

    fc_parts.append(
        f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=first:dropout_transition=0,"
        f"alimiter=limit=0.95,atrim=0:{total_dur:.3f}[outa]"
    )
    cmd.extend([
        "-filter_complex", ";".join(fc_parts),
        "-map", "[outa]",
        "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-q:a", "3",
        str(out_audio),
    ])
    ok = _run_ffmpeg(cmd)
    if not ok or not out_audio.exists():
        _run_ffmpeg(["ffmpeg", "-y", "-i", str(voice_stem), "-c:a", "libmp3lame", "-q:a", "4", str(out_audio)])
    return probe_audio_duration(out_audio), turns


def extract_rms_lip_envelope(audio_path: Path, fps: int = 15, duration: Optional[float] = None) -> List[float]:
    """
    Extracts normalized per-frame RMS audio energy [0.0 .. 1.0] from an audio file
    to drive genuine audio-synchronized mouth movement (lip-sync) on 2D puppets.
    """
    sr = 8000
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(audio_path),
        "-ac", "1", "-ar", str(sr), "-f", "s16le", "-",
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=60)
    raw = r.stdout
    total_samples = len(raw) // 2
    if total_samples < 10:
        n_frames = max(2, int(math.ceil((duration or 2.0) * fps)))
        return [0.0] * n_frames

    samples = struct.unpack(f"<{total_samples}h", raw[: total_samples * 2])
    hop = max(1, sr // max(1, fps))
    raw_rms: List[float] = []
    for start in range(0, total_samples, hop):
        chunk = samples[start : start + hop]
        if not chunk:
            break
        mean_sq = sum(s * s for s in chunk) / float(len(chunk))
        raw_rms.append(math.sqrt(mean_sq))

    peak = max(raw_rms) if raw_rms else 1.0
    if peak < 1e-6:
        return [0.0] * len(raw_rms)

    # Smooth & normalize with noise gate so silent gaps close the mouth cleanly
    norm = [min(1.0, max(0.0, (v / peak - 0.08) / 0.85)) for v in raw_rms]
    smoothed: List[float] = []
    prev = 0.0
    for val in norm:
        prev = 0.65 * val + 0.35 * prev
        smoothed.append(round(prev, 3))

    if duration is not None:
        target_n = max(2, int(math.ceil(duration * fps)))
        if len(smoothed) < target_n:
            smoothed.extend([0.0] * (target_n - len(smoothed)))
        else:
            smoothed = smoothed[:target_n]
    return smoothed
