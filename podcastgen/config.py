"""Configuration: API endpoints, models, defaults, and env handling.

The API key is read from the environment (``SARVAM_API_KEY``) or a ``.env``
file. It is never hard-coded anywhere in this project.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Sarvam API surface (verified against docs.sarvam.ai)
# ---------------------------------------------------------------------------
BASE_URL = "https://api.sarvam.ai"
CHAT_ENDPOINT = "/v1/chat/completions"          # OpenAI-compatible; model: sarvam-105b
TTS_ENDPOINT = "/text-to-speech"                # base64 WAV/MP3 back
TTS_STREAM_ENDPOINT = "/text-to-speech/stream"  # raw binary stream
TRANSLATE_ENDPOINT = "/translate"
STT_ENDPOINT = "/speech-to-text"

# Auth: chat uses Bearer; TTS/translate/STT use the api-subscription-key header.
CHAT_MODEL = "sarvam-105b"                # 128K context, best for reasoning/agentic
CHAT_MODEL_CONVERSATIONAL = "sarvam-105b-conversations"  # 32K, low-latency

TTS_MODEL = "bulbul:v3"                   # stable default; 30+ voices, up to 2500 chars
TTS_MODEL_LATEST = "bulbul:v4-flash"      # latest; 200+ persona voices
TTS_MODEL_LEGACY = "bulbul:v2"            # legacy; pitch/loudness controls

# BCP-47 language codes Bulbul supports.
SUPPORTED_LANGUAGES = {
    "bn-IN": "Bengali",
    "en-IN": "English (India)",
    "gu-IN": "Gujarati",
    "hi-IN": "Hindi",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "mr-IN": "Marathi",
    "od-IN": "Odia",
    "pa-IN": "Punjabi",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
}

# Hard limit for a single REST TTS request.
TTS_MAX_CHARS = 2500
# Leave headroom for sentence-boundary splitting.
TTS_CHUNK_CHARS = 2200


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (no dependency on python-dotenv).

    Existing environment variables always win.
    """
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


@dataclass
class Config:
    """Runtime configuration for a generation run."""

    # Credentials — never logged, never written to disk by this library.
    api_key: str = ""
    base_url: str = BASE_URL

    # Models
    chat_model: str = CHAT_MODEL
    tts_model: str = TTS_MODEL

    # Language for this episode (voice + script). Multilingual: set per run.
    language: str = "en-IN"

    # TTS tuning
    sample_rate: int = 24000          # 8000/16000/22050/24000 (+32k/44.1k/48k on REST v3)
    audio_codec: str = "wav"          # wav|mp3|aac|opus|flac|linear16|mulaw|alaw
    default_pace: float = 1.0
    temperature: float = 0.6          # bulbul:v3 expressiveness (0.01–2.0)

    # Script / research shape
    target_minutes: float = 8.0
    num_speakers: int = 2
    tone: str = "conversational, curious, and warm"
    audience: str = "a general, smart audience"

    # Assembly
    turn_gap: float = 0.35            # silence between dialogue turns (seconds)
    chapter_gap: float = 0.9          # silence between chapters
    music_gain: float = 0.12          # background music level (0..1)
    duck_music: bool = True           # lower music while speech plays
    music_fade: float = 1.5           # music fade in/out seconds

    # HTTP behaviour
    timeout: int = 120
    max_retries: int = 4

    # Extra headers / misc
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, **overrides) -> "Config":
        """Build a Config from the environment, applying keyword overrides."""
        load_dotenv()
        cfg = cls(
            api_key=os.environ.get("SARVAM_API_KEY", ""),
            chat_model=os.environ.get("SARVAM_CHAT_MODEL", CHAT_MODEL),
            tts_model=os.environ.get("SARVAM_TTS_MODEL", TTS_MODEL),
        )
        for key, value in overrides.items():
            if value is not None and hasattr(cfg, key):
                setattr(cfg, key, value)
        return cfg

    def require_key(self) -> str:
        if not self.api_key:
            raise ValueError(
                "No Sarvam API key found. Set the SARVAM_API_KEY environment "
                "variable or create a .env file (see .env.example)."
            )
        return self.api_key
