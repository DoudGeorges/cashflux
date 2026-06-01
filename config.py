"""Application configuration."""

from __future__ import annotations

import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY") or os.urandom(24).hex()
    SQLALCHEMY_DATABASE_URI = "sqlite:///chats.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(days=14)

    # External API keys
    GEMINI_API_KEY = (
        os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("API")
    )
    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY") or os.getenv("API", "")
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
