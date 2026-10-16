"""Pipeline: orchestrate research -> outline -> script -> TTS -> assembly."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import audio, research as research_mod, scriptwriter as sw, tts as tts_mod, voices
from .client import SarvamClient
from .config import Config


@dataclass
class EpisodeResult:
    title: str
    out_path: str
    duration: float
    language: str
    cast: Dict[str, str]
    script: Dict[str, Any]
    research: str = ""
    transcript: str = ""
    segments: List[tts_mod.RenderedSegment] = field(default_factory=list)
    assets_dir: str = ""
    metadata_path: str = ""

    def summary(self) -> str:
        mins, secs = divmod(int(self.duration), 60)
        return (
            f"“{self.title}” — {mins}:{secs:02d}, {len(self.segments)} turns, "
            f"{self.language}, voices: {', '.join(f'{r}={v}' for r, v in self.cast.items())}"
        )


def slugify(text: str, max_len: int = 48) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:max_len] or "episode"


class PodcastGenerator:
    """High-level generator. Construct with a Config, then call :meth:`generate`."""

    def __init__(self, config: Optional[Config] = None, client: Optional[SarvamClient] = None):
        self.cfg = config or Config.from_env()
        self.client = client or SarvamClient(self.cfg)

    # ------------------------------------------------------------------ public
    def generate(
        self,
        topic: str,
        *,
        sources: Optional[List[str]] = None,
        out_path: Optional[str] = None,
        music_path: Optional[str] = None,
        roles: Optional[List[str]] = None,
        script_only: bool = False,
        keep_assets: bool = True,
        log=print,
    ) -> EpisodeResult:
        """Run the full pipeline for ``topic`` and return the result."""
        cfg = self.cfg
        if roles is None:
            roles = voices.default_roles(cfg.num_speakers)

        log(f"[1/6] Researching: {topic!r} ({cfg.language})")
        brief = research_mod.research(
            self.client,
            topic,
            language=cfg.language,
            audience=cfg.audience,
            tone=cfg.tone,
            sources=sources,
        )

        log("[2/6] Building outline")
        outline = sw.make_outline(
            self.client,
            brief,
            title_hint=topic,
            language=cfg.language,
            target_minutes=cfg.target_minutes,
            num_speakers=cfg.num_speakers,
            tone=cfg.tone,
            audience=cfg.audience,
        )

        log("[3/6] Writing multi-speaker script")
        script = sw.write_script(
            self.client,
            outline,
            roles=roles,
            language=cfg.language,
            tone=cfg.tone,
            target_minutes=cfg.target_minutes,
            brief=brief,
        )
        script["language"] = cfg.language

        cast = voices.assign_cast(cfg.language, len(roles), roles)
        title = script.get("title") or topic
        slug = slugify(title)

        if out_path is None:
            out_path = os.path.join(os.getcwd(), f"{slug}.wav")
        assets_dir = os.path.join(os.path.dirname(os.path.abspath(out_path)), f"{slug}_assets")
        os.makedirs(assets_dir, exist_ok=True)

        # Persist the script + brief immediately (useful even if TTS fails).
        self._write_json(os.path.join(assets_dir, "script.json"), script)
        self._write_json(os.path.join(assets_dir, "outline.json"), outline)
        with open(os.path.join(assets_dir, "research.md"), "w", encoding="utf-8") as fh:
            fh.write(brief)

        log(f"[4/6] Script ready: {sw.script_word_count(script)} words "
            f"(~{sw.estimate_minutes(script)} min). Cast: {cast}")

        if script_only:
            log("[5/6] --script-only: stopping before audio.")
            return EpisodeResult(
                title=title, out_path="", duration=0.0, language=cfg.language,
                cast=cast, script=script, research=brief,
                transcript=sw.to_transcript(script), assets_dir=assets_dir,
            )

        log(f"[5/6] Synthesising {sum(len(c.get('segments', [])) for c in script['chapters'])} turns")

        def _progress(seg: tts_mod.RenderedSegment) -> None:
            log(f"      · turn {seg.index + 1:>3} [{seg.speaker_role}→{seg.speaker_id}] "
                f"{seg.duration:4.1f}s")

        segments = tts_mod.render_script(
            self.client, script, cast, os.path.join(assets_dir, "segments"),
            self.cfg, progress=_progress,
        )

        log("[6/6] Assembling episode")
        waveform = audio.build_episode(
            [{"path": s.path, "pause_after": s.pause_after, "chapter_index": s.chapter_index}
             for s in segments],
            sr=cfg.sample_rate,
            turn_gap=cfg.turn_gap,
            chapter_gap=cfg.chapter_gap,
            music_path=music_path,
            music_gain=cfg.music_gain,
            duck=cfg.duck_music,
            music_fade=cfg.music_fade,
        )
        out_path = audio.export(waveform, cfg.sample_rate, out_path)
        duration = waveform.size / cfg.sample_rate

        result = EpisodeResult(
            title=title,
            out_path=out_path,
            duration=duration,
            language=cfg.language,
            cast=cast,
            script=script,
            research=brief,
            transcript=sw.to_transcript(script),
            segments=segments,
            assets_dir=assets_dir,
        )
        result.metadata_path = self._write_metadata(result, assets_dir)

        if not keep_assets:
            _rmtree(os.path.join(assets_dir, "segments"))
        log(f"Done → {out_path}  ({result.summary()})")
        return result

    def from_script(
        self,
        script: Dict[str, Any],
        *,
        out_path: Optional[str] = None,
        music_path: Optional[str] = None,
        cast: Optional[Dict[str, str]] = None,
        log=print,
    ) -> EpisodeResult:
        """Render an already-written script dict to audio (skips LLM stages)."""
        cfg = self.cfg
        script.setdefault("language", cfg.language)
        cfg.language = script.get("language", cfg.language)

        roles = []
        for ch in script.get("chapters", []):
            for seg in ch.get("segments", []):
                if seg.get("speaker") not in roles:
                    roles.append(seg["speaker"])
        if cast is None:
            cast = voices.assign_cast(cfg.language, len(roles), roles)

        title = script.get("title", "Episode")
        slug = slugify(title)
        if out_path is None:
            out_path = os.path.join(os.getcwd(), f"{slug}.wav")
        assets_dir = os.path.join(os.path.dirname(os.path.abspath(out_path)), f"{slug}_assets")
        os.makedirs(assets_dir, exist_ok=True)

        log(f"Rendering {sum(len(c.get('segments', [])) for c in script['chapters'])} turns")

        def _progress(seg):
            log(f"      · turn {seg.index + 1:>3} [{seg.speaker_role}→{seg.speaker_id}] {seg.duration:4.1f}s")

        segments = tts_mod.render_script(
            self.client, script, cast, os.path.join(assets_dir, "segments"), cfg, progress=_progress
        )
        waveform = audio.build_episode(
            [{"path": s.path, "pause_after": s.pause_after, "chapter_index": s.chapter_index}
             for s in segments],
            sr=cfg.sample_rate, turn_gap=cfg.turn_gap, chapter_gap=cfg.chapter_gap,
            music_path=music_path, music_gain=cfg.music_gain, duck=cfg.duck_music,
            music_fade=cfg.music_fade,
        )
        out_path = audio.export(waveform, cfg.sample_rate, out_path)
        result = EpisodeResult(
            title=title, out_path=out_path, duration=waveform.size / cfg.sample_rate,
            language=cfg.language, cast=cast, script=script,
            transcript=sw.to_transcript(script), segments=segments, assets_dir=assets_dir,
        )
        result.metadata_path = self._write_metadata(result, assets_dir)
        log(f"Done → {out_path}  ({result.summary()})")
        return result

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _write_json(path: str, obj: Any) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2)

    def _write_metadata(self, result: EpisodeResult, assets_dir: str) -> str:
        meta = {
            "title": result.title,
            "logline": result.script.get("logline", ""),
            "show_notes": result.script.get("show_notes", ""),
            "language": result.language,
            "duration_seconds": round(result.duration, 2),
            "duration_minutes": round(result.duration / 60, 2),
            "cast": result.cast,
            "chapters": [c.get("title", "") for c in result.script.get("chapters", [])],
            "sources": result.script.get("sources", []),
            "tts_model": self.cfg.tts_model,
            "chat_model": self.cfg.chat_model,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "audio_file": os.path.basename(result.out_path) if result.out_path else None,
        }
        path = os.path.join(assets_dir, "episode.json")
        self._write_json(path, meta)

        with open(os.path.join(assets_dir, "transcript.txt"), "w", encoding="utf-8") as fh:
            fh.write(result.transcript)
        with open(os.path.join(assets_dir, "show_notes.md"), "w", encoding="utf-8") as fh:
            fh.write(f"# {result.title}\n\n{result.script.get('show_notes', '')}\n")
        return path


def _rmtree(path: str) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)
