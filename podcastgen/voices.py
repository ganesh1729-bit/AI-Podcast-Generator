"""Bulbul voice catalog and language-aware casting.

Speaker names are lowercase and case-sensitive. ``bulbul:v3`` uses short
names (``shubh``, ``priya`` …); ``bulbul:v4-flash`` uses persona ids
(``shubh_enhi_ads``, ``simran_en_customer`` …). v3 short names are NOT valid
on v4-flash.
"""

from __future__ import annotations

from typing import Dict, List

# ---------------------------------------------------------------------------
# bulbul:v3 named speakers, split by perceived gender (per Sarvam docs).
# ---------------------------------------------------------------------------
V3_FEMALE = [
    "ritu", "priya", "neha", "pooja", "simran", "kavya", "ishita", "shreya",
    "roopa", "tanya", "shruti", "suhani", "kavitha", "rupali",
]
V3_MALE = [
    "shubh", "aditya", "rahul", "rohan", "amit", "dev", "ratan", "varun",
    "manan", "sumit", "kabir", "aayan", "ashutosh", "advait", "anand",
    "tarun", "sunny", "mani", "gokul", "vijay", "mohit", "rehan", "soham",
]
V3_ALL = V3_FEMALE + V3_MALE

# ---------------------------------------------------------------------------
# Recommended speakers per language (from Sarvam's guide). These are good
# first picks; anything in V3_ALL is technically valid.
# ---------------------------------------------------------------------------
RECOMMENDED: Dict[str, Dict[str, List[str]]] = {
    "en-IN": {"male": ["ratan", "shubh"], "female": ["ishita", "priya"]},
    "hi-IN": {"male": ["shubh", "ashutosh"], "female": ["priya", "suhani"]},
    "te-IN": {"male": ["shubh", "ratan"], "female": ["neha", "priya"]},
    "kn-IN": {"male": ["shubh", "ratan"], "female": ["neha", "ishita"]},
    "bn-IN": {"male": ["rehan"], "female": ["roopa", "suhani"]},
    "ta-IN": {"male": ["ratan", "rohan"], "female": ["ishita", "ritu"]},
    "od-IN": {"male": ["shubh"], "female": ["ritu", "pooja"]},
    "ml-IN": {"male": ["shubh"], "female": ["pooja"]},
    "mr-IN": {"male": ["ratan"], "female": ["priya", "ritu"]},
    "pa-IN": {"male": ["mani"], "female": ["roopa", "suhani"]},
    "gu-IN": {"male": ["ratan"], "female": ["priya", "ritu"]},
}


def is_valid_v3_speaker(name: str) -> bool:
    return name in V3_ALL


def recommend(language: str, gender: str = "female") -> List[str]:
    """Recommended v3 speaker ids for a language/gender, with a safe fallback."""
    entry = RECOMMENDED.get(language, {})
    picks = entry.get(gender, [])
    if picks:
        return picks
    return V3_FEMALE if gender == "female" else V3_MALE


def assign_cast(language: str, num_speakers: int, roles: List[str] | None = None) -> Dict[str, str]:
    """Map podcast roles to concrete Bulbul v3 speaker ids for a language.

    Alternates genders so a two-host show sounds like a real conversation,
    and picks language-appropriate voices.
    """
    if roles is None:
        roles = default_roles(num_speakers)

    cast: Dict[str, str] = {}
    male_pool = recommend(language, "male")
    female_pool = recommend(language, "female")

    for i, role in enumerate(roles):
        # Alternate starting gender; narrator/host get a clear lead voice.
        want_female = (i % 2 == 0) if role.lower() not in ("narrator",) else True
        pool = female_pool if want_female else male_pool
        other = male_pool if want_female else female_pool
        pick = _first_unused(pool, cast) or _first_unused(other, cast) or pool[0]
        cast[role] = pick
    return cast


def _first_unused(pool: List[str], cast: Dict[str, str]) -> str | None:
    used = set(cast.values())
    for name in pool:
        if name not in used:
            return name
    return None


def default_roles(num_speakers: int) -> List[str]:
    if num_speakers <= 1:
        return ["Host"]
    if num_speakers == 2:
        return ["Host", "Co-host"]
    roles = ["Host", "Co-host"]
    for i in range(2, num_speakers):
        roles.append(f"Guest {i - 1}")
    return roles
