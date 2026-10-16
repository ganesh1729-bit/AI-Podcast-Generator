"""Command-line interface for the AI Podcast Generator.

Examples
--------
    export SARVAM_API_KEY=...            # or put it in .env

    # Full episode from a topic
    python -m podcastgen generate --topic "The future of UPI in India" \
        --lang en-IN --minutes 8 --out episode.wav

    # From a document + background music
    python -m podcastgen generate --from-file notes.md --music bed.wav --out ep.mp3

    # Just the script (no audio, no TTS cost)
    python -m podcastgen generate --topic "ISRO's Gaganyaan" --script-only

    # Render a script you edited by hand
    python -m podcastgen from-script script.json --out episode.wav

    # Voices for a language
    python -m podcastgen voices --lang ta-IN
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from . import voices
from .config import SUPPORTED_LANGUAGES, Config
from .pipeline import PodcastGenerator
from .scriptwriter import parse_json


def _read_text_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md", ".markdown", ".rst"):
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    if ext == ".pdf":
        try:
            import fitz  # PyMuPDF
        except ImportError:
            sys.exit("Reading PDFs needs PyMuPDF: pip install pymupdf")
        doc = fitz.open(path)
        return "\n".join(page.get_text() for page in doc)
    if ext == ".docx":
        try:
            import docx
        except ImportError:
            sys.exit("Reading .docx needs python-docx: pip install python-docx")
        return "\n".join(p.text for p in docx.Document(path).paragraphs)
    sys.exit(f"Unsupported document type: {ext} (use .txt/.md/.pdf/.docx)")


def _build_config(args) -> Config:
    overrides = dict(
        language=args.lang,
        target_minutes=args.minutes,
        num_speakers=args.speakers,
        tts_model=args.tts_model,
        chat_model=args.chat_model,
        music_gain=args.music_gain,
        turn_gap=args.turn_gap,
        temperature=args.temperature,
        sample_rate=args.sample_rate,
    )
    if args.api_key:
        os.environ["SARVAM_API_KEY"] = args.api_key
    return Config.from_env(**overrides)


def cmd_generate(args) -> int:
    cfg = _build_config(args)
    gen = PodcastGenerator(cfg)

    sources: Optional[List[str]] = None
    topic = args.topic
    if args.from_file:
        doc = _read_text_file(args.from_file)
        sources = [doc]
        if not topic:
            topic = args.title or os.path.splitext(os.path.basename(args.from_file))[0]
    if not topic:
        sys.exit("Provide --topic and/or --from-file.")

    roles = args.roles.split(",") if args.roles else None

    result = gen.generate(
        topic,
        sources=sources,
        out_path=args.out,
        music_path=args.music,
        roles=roles,
        script_only=args.script_only,
        keep_assets=not args.clean,
    )
    if args.script_only:
        print(f"\nScript written to: {os.path.join(result.assets_dir, 'script.json')}")
    else:
        print(f"\nEpisode:  {result.out_path}")
        print(f"Metadata: {result.metadata_path}")
        print(f"Assets:   {result.assets_dir}")
    return 0


def cmd_from_script(args) -> int:
    cfg = _build_config(args)
    gen = PodcastGenerator(cfg)
    with open(args.script, "r", encoding="utf-8") as fh:
        script = parse_json(fh.read())
    cast = json.loads(args.cast) if args.cast else None
    result = gen.from_script(script, out_path=args.out, music_path=args.music, cast=cast)
    print(f"\nEpisode:  {result.out_path}")
    print(f"Metadata: {result.metadata_path}")
    return 0


def cmd_voices(args) -> int:
    lang = args.lang
    print(f"Recommended Bulbul v3 voices for {lang} ({SUPPORTED_LANGUAGES.get(lang, '?')}):")
    print(f"  male:   {', '.join(voices.recommend(lang, 'male'))}")
    print(f"  female: {', '.join(voices.recommend(lang, 'female'))}")
    print("\nFull v3 catalog:")
    print(f"  female: {', '.join(voices.V3_FEMALE)}")
    print(f"  male:   {', '.join(voices.V3_MALE)}")
    print("\nCast example (2 hosts):", voices.assign_cast(lang, 2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="podcastgen",
        description="Generate complete AI podcast episodes with the Sarvam API.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp):
        sp.add_argument("--api-key", help="Sarvam API key (prefer SARVAM_API_KEY env / .env)")
        sp.add_argument("--lang", default="en-IN", choices=sorted(SUPPORTED_LANGUAGES),
                        help="Episode language (BCP-47). Default en-IN.")
        sp.add_argument("--out", help="Output audio path (.wav always; .mp3 needs ffmpeg)")
        sp.add_argument("--music", help="Background music WAV path")
        sp.add_argument("--music-gain", type=float, default=0.12, help="Music level 0..1")
        sp.add_argument("--turn-gap", type=float, default=0.35, help="Silence between turns (s)")
        sp.add_argument("--temperature", type=float, default=0.6, help="TTS expressiveness")
        sp.add_argument("--sample-rate", type=int, default=24000, help="Output sample rate")
        sp.add_argument("--tts-model", default="bulbul:v3")
        sp.add_argument("--chat-model", default="sarvam-105b")

    g = sub.add_parser("generate", help="Full pipeline from a topic or document")
    g.add_argument("--topic", help="Episode topic / prompt")
    g.add_argument("--from-file", help="Document to base the episode on (.txt/.md/.pdf/.docx)")
    g.add_argument("--title", help="Title hint")
    g.add_argument("--minutes", type=float, default=8.0, help="Target length in minutes")
    g.add_argument("--speakers", type=int, default=2, help="Number of speakers")
    g.add_argument("--roles", help="Comma-separated role names, e.g. 'Host,Co-host'")
    g.add_argument("--script-only", action="store_true", help="Write script, skip TTS/audio")
    g.add_argument("--clean", action="store_true", help="Delete per-segment WAVs after build")
    add_common(g)
    g.set_defaults(func=cmd_generate)

    s = sub.add_parser("from-script", help="Render a hand-edited script JSON to audio")
    s.add_argument("script", help="Path to script JSON")
    s.add_argument("--cast", help='JSON mapping role->speaker id, e.g. {"Host":"priya"}')
    add_common(s)
    s.set_defaults(func=cmd_from_script)

    v = sub.add_parser("voices", help="Show available/recommended voices")
    v.add_argument("--lang", default="en-IN", choices=sorted(SUPPORTED_LANGUAGES))
    v.set_defaults(func=cmd_voices)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
