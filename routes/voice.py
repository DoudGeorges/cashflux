"""Voice assistant routes."""

from __future__ import annotations

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    request,
    stream_with_context,
)

from core.auth import login_required

voice_bp = Blueprint("voice", __name__)


@voice_bp.route("/api/voice/ready")
@login_required
def api_voice_ready():
    """Warm the ElevenLabs client on first mic use."""
    from ai.tts import is_available

    if is_available():
        try:
            from ai.tts import warm_client

            warm_client()
        except Exception as exc:
            current_app.logger.warning("ElevenLabs warm-up failed: %s", exc)
    return jsonify({"elevenlabs": is_available()})


@voice_bp.route("/api/voice/tts", methods=["POST"])
@login_required
def api_voice_tts():
    from ai.voice import _strip_for_speech
    from ai.tts import is_available, stream_speech

    if not is_available():
        return jsonify({"error": "ElevenLabs not configured"}), 503

    data = request.get_json(silent=True) or {}
    text = _strip_for_speech(data.get("text") or "")
    if not text:
        return jsonify({"error": "No text to speak"}), 400

    def generate():
        try:
            yield from stream_speech(text)
        except Exception as exc:
            current_app.logger.warning("ElevenLabs TTS stream error: %s", exc)

    return Response(
        stream_with_context(generate()),
        mimetype="audio/mpeg",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
