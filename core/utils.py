"""Shared utility functions used across multiple modules."""

from __future__ import annotations

import json
import os
import re
from typing import Any


def gemini_api_key() -> str | None:
    """Return the Gemini API key from environment variables.

    Prefer ``Config.GEMINI_API_KEY`` for new callers.
    """
    return (
        os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("API")
    )


def safe_json(text: str) -> Any:
    """Extract and parse a JSON object from LLM-generated text.

    Handles common issues like markdown fences and trailing commas.
    """
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return json.loads(text)
