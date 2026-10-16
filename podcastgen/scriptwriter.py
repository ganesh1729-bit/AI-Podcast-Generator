"""Script stage: outline -> multi-speaker dialogue script (structured JSON).

The script is a list of chapters, each holding ordered *segments*. A segment is
one speaker turn:

    {"speaker": "Host", "text": "...", "pace": 1.0, "pause_after": 0.5}

The model is asked for JSON and we parse defensively (models sometimes wrap
JSON in prose or code fences).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from .client import SarvamClient

# Rough speaking rate used for budgeting. Bulbul at pace 1.0 ≈ this.
WORDS_PER_MINUTE = 150

SYSTEM = (
    "You are an award-winning podcast showrunner and dialogue writer. You write "
    "natural, unscripted-sounding conversation between co-hosts: short turns, "
    "real back-and-forth, the occasional interjection, no monologues unless the "
    "format calls for it. You always return strict, valid JSON."
)

LANGUAGE_RULES = {
    "hi-IN": "Write the dialogue in Hindi using Devanagari script.",
    "bn-IN": "Write the dialogue in Bengali using Bengali script.",
    "ta-IN": "Write the dialogue in Tamil using Tamil script.",
    "te-IN": "Write the dialogue in Telugu using Telugu script.",
    "kn-IN": "Write the dialogue in Kannada using Kannada script.",
    "ml-IN": "Write the dialogue in Malayalam using Malayalam script.",
    "mr-IN": "Write the dialogue in Marathi using Devanagari script.",
    "gu-IN": "Write the dialogue in Gujarati using Gujarati script.",
    "pa-IN": "Write the dialogue in Punjabi using Gurmukhi script.",
    "od-IN": "Write the dialogue in Odia using Odia script.",
    "en-IN": "Write the dialogue in natural Indian English.",
}


def language_instruction(language: str) -> str:
    base = LANGUAGE_RULES.get(language, f"Write the dialogue in the language with BCP-47 code {language}.")
    extra = ""
    if language != "en-IN":
        extra = (
            " If the hosts use English words or code-mix (Hinglish/Tanglish/etc.), "
            "keep the Indic words in their native script and only the English words "
            "in Latin script — romanised Indic text degrades the text-to-speech quality."
        )
    return base + extra


def word_budget(target_minutes: float) -> int:
    return int(target_minutes * WORDS_PER_MINUTE)


def make_outline(
    client: SarvamClient,
    brief: str,
    *,
    title_hint: str = "",
    language: str = "en-IN",
    target_minutes: float = 8.0,
    num_speakers: int = 2,
    tone: str = "conversational, curious, and warm",
    audience: str = "a general, smart audience",
) -> Dict[str, Any]:
    """Return an outline dict: title, logline, chapters[{title, goal, beats}]."""
    budget = word_budget(target_minutes)
    prompt = f"""Create an outline for a {target_minutes:.0f}-minute, {num_speakers}-speaker podcast episode.

TITLE HINT: {title_hint or "(come up with a good title)"}
AUDIENCE: {audience}
TONE: {tone}
APPROXIMATE WORD BUDGET: ~{budget} spoken words total.

Research brief to draw from:
<brief>
{brief}
</brief>

Return ONLY JSON with this exact shape:
{{
  "title": "episode title",
  "logline": "one sentence describing the episode",
  "chapters": [
    {{"title": "chapter title", "goal": "what this chapter achieves",
      "beats": ["beat 1", "beat 2", "beat 3"]}}
  ]
}}
Use 3–5 chapters (always include a short cold-open/intro and a closing takeaway)."""

    raw = client.chat(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        temperature=0.6,
        max_tokens=2048,
        json_mode=True,
    )
    data = parse_json(raw)
    data.setdefault("title", title_hint or "Untitled Episode")
    data.setdefault("logline", "")
    data.setdefault("chapters", [])
    return data


def write_script(
    client: SarvamClient,
    outline: Dict[str, Any],
    *,
    roles: List[str],
    language: str = "en-IN",
    tone: str = "conversational, curious, and warm",
    target_minutes: float = 8.0,
    brief: str = "",
) -> Dict[str, Any]:
    """Expand an outline into a full multi-speaker script (segments per chapter)."""
    budget = word_budget(target_minutes)
    role_list = ", ".join(roles)
    prompt = f"""Write the full dialogue script for this episode.

SPEAKERS (use these exact role names): {role_list}
TONE: {tone}
APPROXIMATE SPOKEN WORD BUDGET: ~{budget} words total across all speakers.
{language_instruction(language)}

OUTLINE:
{json.dumps(outline, ensure_ascii=False, indent=2)}

Guidelines:
- Alternate turns naturally. Most turns are 1–3 sentences; avoid long speeches.
- Include light conversational glue ("right", "exactly", "wait, really?") that suits the tone.
- Open with a strong hook and close with a clear takeaway.
- "pace" is a Bulbul speed multiplier in [0.5, 2.0]; use 1.0 mostly, 0.9 for slow/reverent moments.
- "pause_after" is silence in seconds after the turn (0.2–0.8 typical; 1.0+ for a beat).

Return ONLY JSON:
{{
  "title": "{outline.get('title', 'Episode')}",
  "logline": "{outline.get('logline', '')}",
  "chapters": [
    {{"title": "chapter title",
      "segments": [
        {{"speaker": "{roles[0]}", "text": "...", "pace": 1.0, "pause_after": 0.4}}
      ]}}
  ],
  "show_notes": "2–4 sentence episode description for listeners",
  "sources": ["optional source or reference", "..."]
}}"""

    raw = client.chat(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=8192,
        json_mode=True,
    )
    script = parse_json(raw)
    script = normalise_script(script, roles)
    return script


def normalise_script(script: Dict[str, Any], roles: List[str]) -> Dict[str, Any]:
    """Coerce a model-returned script into the canonical shape and validate."""
    script.setdefault("title", "Untitled Episode")
    script.setdefault("logline", "")
    script.setdefault("show_notes", "")
    script.setdefault("sources", [])
    chapters = script.get("chapters") or []
    clean_chapters: List[Dict[str, Any]] = []
    fallback = roles[0] if roles else "Host"

    for ch in chapters:
        segs = ch.get("segments") or ch.get("dialogue") or []
        clean_segs: List[Dict[str, Any]] = []
        for seg in segs:
            text = (seg.get("text") or seg.get("line") or "").strip()
            if not text:
                continue
            speaker = seg.get("speaker") or seg.get("role") or fallback
            clean_segs.append(
                {
                    "speaker": speaker,
                    "text": text,
                    "pace": _clamp_float(seg.get("pace", 1.0), 0.5, 2.0),
                    "pause_after": _clamp_float(seg.get("pause_after", 0.35), 0.0, 3.0),
                }
            )
        if clean_segs:
            clean_chapters.append({"title": ch.get("title", ""), "segments": clean_segs})

    script["chapters"] = clean_chapters
    return script


def script_word_count(script: Dict[str, Any]) -> int:
    total = 0
    for ch in script.get("chapters", []):
        for seg in ch.get("segments", []):
            total += len(seg.get("text", "").split())
    return total


def estimate_minutes(script: Dict[str, Any]) -> float:
    return round(script_word_count(script) / WORDS_PER_MINUTE, 1)


def to_transcript(script: Dict[str, Any]) -> str:
    """Render a script as a readable transcript (also used for show notes)."""
    lines: List[str] = []
    for ch in script.get("chapters", []):
        if ch.get("title"):
            lines.append(f"\n## {ch['title']}\n")
        for seg in ch.get("segments", []):
            lines.append(f"{seg['speaker']}: {seg['text']}")
    return "\n".join(lines).strip()


# --------------------------------------------------------------------------- #
# JSON parsing helper
# --------------------------------------------------------------------------- #
def parse_json(raw: str) -> Dict[str, Any]:
    """Best-effort extraction of a JSON object from a model response."""
    if isinstance(raw, dict):
        return raw
    text = raw.strip()
    # Strip ```json ... ``` fences.
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back to the first balanced {...}.
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    raise ValueError(f"Could not parse JSON from model response:\n{raw[:800]}")


def _clamp_float(value: Any, lo: float, hi: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = lo
    return max(lo, min(hi, v))
