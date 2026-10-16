"""Thin, dependency-light client for the Sarvam REST API.

Wraps the three endpoints this project needs:
  * POST /v1/chat/completions  — script writing & research (Bearer auth)
  * POST /text-to-speech       — Bulbul synthesis (api-subscription-key auth)
  * POST /translate            — optional translation helper

Includes bounded retries with exponential backoff on 429/5xx and a typed
``SarvamError`` for clean error handling upstream.
"""

from __future__ import annotations

import base64
import json
import random
import time
from typing import Any, Dict, List, Optional

import requests

from .config import (
    CHAT_ENDPOINT,
    STT_ENDPOINT,
    TRANSLATE_ENDPOINT,
    TTS_ENDPOINT,
    Config,
)


class SarvamError(RuntimeError):
    """Raised for any non-recoverable API failure."""

    def __init__(self, message: str, status: int | None = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


class SarvamClient:
    def __init__(self, config: Optional[Config] = None):
        self.cfg = config or Config.from_env()
        self.cfg.require_key()
        self._session = requests.Session()

    # ------------------------------------------------------------------ utils
    def _headers_chat(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/json",
        }

    def _headers_subscription(self) -> Dict[str, str]:
        return {
            "api-subscription-key": self.cfg.api_key,
            "Content-Type": "application/json",
        }

    def _post(self, path: str, payload: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        url = self.cfg.base_url + path
        last_err: Exception | None = None
        for attempt in range(self.cfg.max_retries):
            try:
                resp = self._session.post(
                    url, json=payload, headers=headers, timeout=self.cfg.timeout
                )
            except requests.RequestException as exc:  # network hiccup
                last_err = exc
            else:
                if resp.status_code < 400:
                    return resp.json()
                # Retry only on rate-limit / server errors.
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_err = SarvamError(
                        f"HTTP {resp.status_code} from {path}", resp.status_code, _safe_json(resp)
                    )
                else:
                    raise SarvamError(
                        f"HTTP {resp.status_code} from {path}", resp.status_code, _safe_json(resp)
                    )
            # backoff
            if attempt < self.cfg.max_retries - 1:
                time.sleep(min(2 ** attempt + random.random(), 20))
        raise SarvamError(f"Request to {path} failed after retries: {last_err}")

    # ------------------------------------------------------------------- chat
    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> str:
        """Return the assistant text for a chat conversation."""
        payload: Dict[str, Any] = {
            "model": model or self.cfg.chat_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = self._post(CHAT_ENDPOINT, payload, self._headers_chat())
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise SarvamError(f"Unexpected chat response shape: {data}") from exc

    # -------------------------------------------------------------------- tts
    def tts(
        self,
        text: str,
        *,
        language_code: Optional[str] = None,
        speaker: Optional[str] = None,
        model: Optional[str] = None,
        pace: Optional[float] = None,
        temperature: Optional[float] = None,
        sample_rate: Optional[int] = None,
        codec: Optional[str] = None,
    ) -> bytes:
        """Synthesize ``text`` and return raw audio bytes (decoded from base64).

        ``text`` must be <= 2500 chars for the REST endpoint; use
        :func:`podcastgen.tts.synthesize_long` for longer text.
        """
        payload: Dict[str, Any] = {
            "text": text,
            "language_code": language_code or self.cfg.language,
            "model": model or self.cfg.tts_model,
        }
        if speaker:
            payload["speaker"] = speaker
        if pace is not None:
            payload["pace"] = pace
        if temperature is not None:
            payload["temperature"] = temperature
        payload["speech_sample_rate"] = sample_rate or self.cfg.sample_rate
        payload["output_audio_codec"] = codec or self.cfg.audio_codec

        data = self._post(TTS_ENDPOINT, payload, self._headers_subscription())
        audios = data.get("audios")
        if not audios:
            raise SarvamError(f"No audio returned: {data}")
        return base64.b64decode(audios[0])

    # -------------------------------------------------------------- translate
    def translate(
        self,
        text: str,
        target_language_code: str,
        *,
        source_language_code: str = "auto",
        speaker_gender: str = "Female",
    ) -> str:
        payload = {
            "input": text,
            "source_language_code": source_language_code,
            "target_language_code": target_language_code,
            "speaker_gender": speaker_gender,
            "mode": "formal",
            "model": "mayura:v1",
        }
        data = self._post(TRANSLATE_ENDPOINT, payload, self._headers_subscription())
        return data.get("translated_text", "")

    # -------------------------------------------------------------------- stt
    def stt(self, audio_bytes: bytes, filename: str = "audio.wav", language_code: str = "unknown") -> str:
        """Transcribe audio (multipart upload). Optional helper."""
        url = self.cfg.base_url + STT_ENDPOINT
        files = {"file": (filename, audio_bytes)}
        data = {"model": "saarika:v2.5", "language_code": language_code}
        resp = self._session.post(
            url, files=files, data=data,
            headers={"api-subscription-key": self.cfg.api_key},
            timeout=self.cfg.timeout,
        )
        if resp.status_code >= 400:
            raise SarvamError(f"STT HTTP {resp.status_code}", resp.status_code, _safe_json(resp))
        return resp.json().get("transcript", "")


def _safe_json(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError):
        return resp.text[:500]
