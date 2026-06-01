"""ElevenLabs text-to-speech client for the Friday voice assistant."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Iterator

# Free-tier voice: Laura  clear and natural.
FALLBACK_VOICE_ID = "FGY2WhTYpPnrIDTdsKH5"

_available: bool | None = None


def is_available() -> bool:
    """Return True if an ElevenLabs API key is configured."""
    global _available
    if _available is None:
        _available = bool(os.getenv("ELEVENLABS_API_KEY"))
    return _available


def warm_client() -> None:
    """Pre-check availability so the first TTS request has no latency spike."""
    is_available()


def _stream_with_voice(text: str, voice_id: str) -> Iterator[bytes]:
    model_id = os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    payload = json.dumps(
        {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": 0.4,
                "similarity_boost": 0.75,
            },
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                yield chunk
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ElevenLabs HTTP {exc.code}: {body[:240]}") from exc


def stream_speech(text: str) -> Iterator[bytes]:
    """Stream MP3 bytes from ElevenLabs (flash model by default)."""
    cleaned = (text or "").strip()
    if not cleaned or not is_available():
        return

    voice_id = os.getenv("ELEVENLABS_VOICE_ID", FALLBACK_VOICE_ID)
    try:
        yield from _stream_with_voice(cleaned, voice_id)
    except RuntimeError as exc:
        # Fall back to the free-tier voice if the configured voice hits a 402.
        if voice_id != FALLBACK_VOICE_ID and "402" in str(exc):
            yield from _stream_with_voice(cleaned, FALLBACK_VOICE_ID)
        else:
            raise
