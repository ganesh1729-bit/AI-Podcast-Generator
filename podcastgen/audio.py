"""Audio assembly: WAV I/O, concatenation, gaps, background-music mixing,
simple side-chain ducking, and optional MP3 export.

Pure-Python (``wave``) + numpy — no ffmpeg required. If ``ffmpeg`` happens to
be on PATH, :func:`export` will additionally write MP3.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import wave
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

SR_DEFAULT = 24000


# --------------------------------------------------------------------------- #
# WAV I/O  (internally we work in float32 mono, range [-1, 1])
# --------------------------------------------------------------------------- #
def read_wav(path: str) -> Tuple[np.ndarray, int]:
    with open(path, "rb") as fh:
        return read_wav_bytes(fh.read())


def read_wav_bytes(data: bytes) -> Tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sr = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth == 2:
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sampwidth == 1:
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sampwidth == 4:
        samples = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sampwidth} bytes")

    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)
    return samples, sr


def write_wav(path: str, samples: np.ndarray, sr: int = SR_DEFAULT) -> None:
    samples = np.asarray(samples, dtype=np.float32)
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def to_wav_bytes(samples: np.ndarray, sr: int = SR_DEFAULT) -> bytes:
    buf = io.BytesIO()
    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Building blocks
# --------------------------------------------------------------------------- #
def silence(seconds: float, sr: int) -> np.ndarray:
    n = max(0, int(round(seconds * sr)))
    return np.zeros(n, dtype=np.float32)


def resample_linear(samples: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr or samples.size == 0:
        return samples.astype(np.float32)
    n_dst = int(round(samples.size * dst_sr / src_sr))
    if n_dst <= 0:
        return np.zeros(0, dtype=np.float32)
    x_src = np.linspace(0.0, 1.0, samples.size, endpoint=False)
    x_dst = np.linspace(0.0, 1.0, n_dst, endpoint=False)
    return np.interp(x_dst, x_src, samples).astype(np.float32)


def concat(parts: Sequence[np.ndarray]) -> np.ndarray:
    parts = [p for p in parts if p is not None and p.size]
    if not parts:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(parts).astype(np.float32)


def peak_normalise(samples: np.ndarray, target: float = 0.97) -> np.ndarray:
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak < 1e-6:
        return samples
    return (samples * (target / peak)).astype(np.float32)


# --------------------------------------------------------------------------- #
# Background music
# --------------------------------------------------------------------------- #
def prepare_music(
    music_path: str,
    sr: int,
    length_samples: int,
    *,
    gain: float = 0.12,
    fade: float = 1.5,
) -> np.ndarray:
    """Load a music file, resample, loop/trim to length, apply gain and fades."""
    music, m_sr = read_wav(music_path)
    music = resample_linear(music, m_sr, sr)
    if music.size == 0:
        return np.zeros(length_samples, dtype=np.float32)

    # Loop or trim to the narration length.
    if music.size < length_samples:
        reps = int(np.ceil(length_samples / music.size))
        music = np.tile(music, reps)
    music = music[:length_samples]

    fade_n = min(int(fade * sr), length_samples // 2)
    if fade_n > 0:
        ramp = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
        music[:fade_n] *= ramp
        music[-fade_n:] *= ramp[::-1]

    return (music * gain).astype(np.float32)


def _speech_envelope(voice: np.ndarray, sr: int, window_s: float = 0.25) -> np.ndarray:
    """Moving-average amplitude envelope used to duck music under speech."""
    win = max(1, int(window_s * sr))
    env = np.abs(voice)
    kernel = np.ones(win, dtype=np.float32) / win
    return np.convolve(env, kernel, mode="same")


def duck_music(music: np.ndarray, voice: np.ndarray, sr: int, duck_db: float = -11.0) -> np.ndarray:
    """Lower music gain while speech is present (simple side-chain)."""
    env = _speech_envelope(voice, sr)
    thresh = max(0.02, float(np.percentile(env, 60)) if env.size else 0.02)
    active = (env > thresh).astype(np.float32)
    # Smooth the gate so gain changes aren't abrupt.
    win = max(1, int(0.2 * sr))
    kernel = np.ones(win, dtype=np.float32) / win
    gate = np.convolve(active, kernel, mode="same")
    gate = np.clip(gate, 0.0, 1.0)
    duck_factor = 10.0 ** (duck_db / 20.0)  # e.g. -11 dB ≈ 0.28
    gain_curve = 1.0 - gate * (1.0 - duck_factor)
    return (music * gain_curve).astype(np.float32)


# --------------------------------------------------------------------------- #
# Episode assembly
# --------------------------------------------------------------------------- #
def build_episode(
    segments: Iterable[dict],
    *,
    sr: int = SR_DEFAULT,
    turn_gap: float = 0.35,
    chapter_gap: float = 0.9,
    music_path: Optional[str] = None,
    music_gain: float = 0.12,
    duck: bool = True,
    music_fade: float = 1.5,
    lead_in: float = 0.3,
    tail_out: float = 1.0,
) -> np.ndarray:
    """Stitch rendered segments into a single episode waveform.

    Each ``segments`` item: {"path": wav path, "pause_after": seconds,
    "chapter_index": int}. A ``chapter_gap`` is inserted whenever the chapter
    index changes; otherwise ``pause_after`` (falling back to ``turn_gap``).
    """
    parts: List[np.ndarray] = [silence(lead_in, sr)]
    prev_chapter: Optional[int] = None

    for seg in segments:
        path = seg["path"]
        samples, seg_sr = read_wav(path)
        samples = resample_linear(samples, seg_sr, sr)
        if prev_chapter is not None and seg.get("chapter_index") != prev_chapter:
            parts.append(silence(chapter_gap, sr))
        parts.append(samples)
        gap = seg.get("pause_after", turn_gap)
        if gap is None:
            gap = turn_gap
        parts.append(silence(float(gap), sr))
        prev_chapter = seg.get("chapter_index", prev_chapter)

    parts.append(silence(tail_out, sr))
    voice = concat(parts)

    if music_path and os.path.isfile(music_path):
        music = prepare_music(music_path, sr, voice.size, gain=music_gain, fade=music_fade)
        if duck:
            music = duck_music(music, voice, sr)
        mixed = voice + music
    else:
        mixed = voice

    return peak_normalise(mixed)


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def export(samples: np.ndarray, sr: int, out_path: str) -> str:
    """Write the episode. ``.wav`` always works; ``.mp3`` needs ffmpeg."""
    ext = os.path.splitext(out_path)[1].lower()
    if ext == ".mp3":
        if not ffmpeg_available():
            wav_path = os.path.splitext(out_path)[0] + ".wav"
            write_wav(wav_path, samples, sr)
            raise RuntimeError(
                "ffmpeg is not available, so MP3 export is disabled. "
                f"Wrote WAV instead: {wav_path}"
            )
        tmp = out_path + ".tmp.wav"
        write_wav(tmp, samples, sr)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp,
             "-codec:a", "libmp3lame", "-b:a", "192k", out_path],
            check=True,
        )
        os.remove(tmp)
        return out_path

    write_wav(out_path, samples, sr)
    return out_path
