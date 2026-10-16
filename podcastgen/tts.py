"""TTS stage: render a script's segments to per-speaker WAV files.

Handles the 2500-char REST limit by splitting long turns at sentence
boundaries, synthesizing each chunk, and concatenating the audio.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from . import audio
from .client import SarvamClient
from .config import TTS_CHUNK_CHARS, Config

_SENTENCE_END = re.compile(r"(?<=[।.!?…])\s+|\n+")


@dataclass
class RenderedSegment:
    index: int
    chapter_index: int
    chapter_title: str
    speaker_role: str
    speaker_id: str
    text: str
    path: str
    duration: float
    pause_after: float


def split_text(text: str, max_chars: int = TTS_CHUNK_CHARS) -> List[str]:
    """Split text into <=max_chars chunks, preferring sentence boundaries."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []

    sentences = _SENTENCE_END.split(text)
    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > max_chars:
            # Hard-wrap a monster sentence.
            for i in range(0, len(sentence), max_chars):
                piece = sentence[i : i + max_chars]
                if current:
                    chunks.append(current)
                    current = ""
                chunks.append(piece)
            continue
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def synthesize_long(
    client: SarvamClient,
    text: str,
    *,
    language_code: str,
    speaker: str,
    model: Optional[str] = None,
    pace: Optional[float] = None,
    temperature: Optional[float] = None,
    sample_rate: int = audio.SR_DEFAULT,
    codec: str = "wav",
) -> np.ndarray:
    """Synthesize arbitrary-length text and return one float32 waveform."""
    chunks = split_text(text)
    if not chunks:
        return np.zeros(0, dtype=np.float32)

    pieces: List[np.ndarray] = []
    for chunk in chunks:
        blob = client.tts(
            chunk,
            language_code=language_code,
            speaker=speaker,
            model=model,
            pace=pace,
            temperature=temperature,
            sample_rate=sample_rate,
            codec=codec,
        )
        samples, sr = audio.read_wav_bytes(blob)
        samples = audio.resample_linear(samples, sr, sample_rate)
        pieces.append(samples)
    return audio.concat(pieces)


def render_script(
    client: SarvamClient,
    script: Dict,
    cast: Dict[str, str],
    out_dir: str,
    config: Optional[Config] = None,
    *,
    progress=None,
) -> List[RenderedSegment]:
    """Render every segment of ``script`` to a WAV file under ``out_dir``.

    ``cast`` maps role name -> Bulbul speaker id.
    """
    cfg = config or client.cfg
    os.makedirs(out_dir, exist_ok=True)
    rendered: List[RenderedSegment] = []
    idx = 0

    for ch_i, chapter in enumerate(script.get("chapters", [])):
        ch_title = chapter.get("title", "")
        for seg in chapter.get("segments", []):
            role = seg.get("speaker", "Host")
            speaker_id = cast.get(role) or next(iter(cast.values()))
            pace = seg.get("pace", cfg.default_pace)
            waveform = synthesize_long(
                client,
                seg["text"],
                language_code=cfg.language,
                speaker=speaker_id,
                model=cfg.tts_model,
                pace=pace,
                temperature=cfg.temperature,
                sample_rate=cfg.sample_rate,
                codec="wav",  # keep WAV for lossless assembly
            )
            path = os.path.join(out_dir, f"seg_{idx:04d}.wav")
            audio.write_wav(path, waveform, cfg.sample_rate)
            duration = waveform.size / cfg.sample_rate if waveform.size else 0.0
            rendered.append(
                RenderedSegment(
                    index=idx,
                    chapter_index=ch_i,
                    chapter_title=ch_title,
                    speaker_role=role,
                    speaker_id=speaker_id,
                    text=seg["text"],
                    path=path,
                    duration=duration,
                    pause_after=float(seg.get("pause_after", cfg.turn_gap)),
                )
            )
            if progress:
                progress(rendered[-1])
            idx += 1

    return rendered
