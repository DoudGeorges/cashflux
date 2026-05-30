"""ElevenLabs TTS — converts text to an MP3 file path."""
import os
import uuid
from elevenlabs import ElevenLabs, VoiceSettings

OUTPUT_DIR = "./voice/output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    return _client


def narrate(text, voice_id=None):
    vid = voice_id or os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    audio = _get_client().text_to_speech.convert(
        voice_id=vid,
        text=text,
        model_id="eleven_multilingual_v2",
        voice_settings=VoiceSettings(stability=0.5, similarity_boost=0.75),
    )
    path = os.path.join(OUTPUT_DIR, f"{uuid.uuid4().hex}.mp3")
    with open(path, "wb") as f:
        for chunk in audio:
            f.write(chunk)
    return path


def build_approval_brief(employee_name, department, amount, purpose, budget_remaining, prior_events, recommendation):
    return (
        f"{employee_name} from {department} is requesting ${amount:,.2f} for {purpose}. "
        f"Their department has ${budget_remaining:,.2f} remaining this quarter. "
        f"They have had {prior_events} similar expenses this year. "
        f"AI recommendation: {recommendation}."
    )
