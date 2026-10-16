"""Research stage: turn a topic (+ optional source documents) into a brief.

This uses Sarvam's chat model (``sarvam-105b``) to produce a structured
research brief — angles, key facts, questions, and a suggested arc. It is
model-knowledge based; pass ``sources`` (your own documents/notes) to ground
it, since the model does not browse the web on its own.
"""

from __future__ import annotations

from typing import List, Optional

from .client import SarvamClient

SYSTEM = (
    "You are a meticulous podcast researcher. You produce tight, accurate, "
    "well-organised research briefs that a host can use to run a great "
    "conversation. You never invent statistics or quotes; when unsure you say "
    "so and flag it as 'verify'."
)


def research(
    client: SarvamClient,
    topic: str,
    *,
    language: str = "en-IN",
    audience: str = "a general, smart audience",
    tone: str = "conversational",
    sources: Optional[List[str]] = None,
    depth: str = "standard",
) -> str:
    """Return a markdown research brief for ``topic``.

    ``sources`` is an optional list of raw text blocks (e.g. the contents of a
    document the user supplied) that the brief must draw on.
    """
    src_block = ""
    if sources:
        joined = "\n\n---\n\n".join(s.strip() for s in sources if s and s.strip())
        if joined:
            src_block = (
                "\n\nBase your brief primarily on the following source material. "
                "Do not contradict it and do not add facts that aren't supported "
                "by it or by well-established general knowledge:\n\n"
                f"<sources>\n{joined[:24000]}\n</sources>"
            )

    prompt = f"""Research brief for a podcast episode.

TOPIC: {topic}
TARGET AUDIENCE: {audience}
TONE: {tone}
DEPTH: {depth}{src_block}

Produce a markdown brief with these sections:
1. **One-line hook** — a compelling framing of why this matters now.
2. **The 5 things a listener should walk away knowing** — crisp bullets.
3. **Key facts & figures** — each with a short note on confidence
   (high/medium) and, where relevant, "verify".
4. **Tensions & counterpoints** — the strongest opposing or complicating views,
   presented fairly.
5. **Great questions to ask** — 6–8 open, non-leading questions.
6. **Suggested arc** — a natural 3–4 act structure (hook → context → the meat →
   takeaway) with rough time allocation.

Keep it under ~900 words. Be concrete, not generic."""

    return client.chat(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=2048,
    )
