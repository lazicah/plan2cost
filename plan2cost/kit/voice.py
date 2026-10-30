"""Speech to text with Muse Voice Transcribe on the Meta Model API: one WAV recording in, the transcript out. It always uses the Meta Model API (the partner hosts of Muse Spark Open
do not serve it), whatever profile the rest of the run uses."""
import json

MODEL = "muse-voice-transcribe-1.0"
MAX_BYTES = 32 * 1024 * 1024  # the API's limit on a request body (a recording may also be at most 10 minutes)


def is_wav(data: bytes) -> bool:
    """Does this look like a WAV file (RIFF header with a WAVE tag)?"""
    return len(data) > 44 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def transcribe(wav: bytes, client=None) -> dict:
    """POST /asr/transcribe in push-to-talk mode, through the same client as the model calls. Returns the API's response: {"transcript": ..., "audioDurationMs": ..., "turns": [], "sessionId": ...}."""
    if not is_wav(wav):
        raise ValueError("the recording must be a WAV file")
    if len(wav) > MAX_BYTES:
        raise ValueError("the recording is too long (32 MB at most)")
    if client is None:
        from plan2cost.kit.client import get_client

        client = get_client("meta")
    settings = json.dumps({"model": MODEL, "audioEncoding": "WAV", "mode": "PUSH_TO_TALK"})
    try:
        return client.post("/asr/transcribe", cast_to=object, files=[("request", (None, settings, "application/json")), ("audio", ("recording.wav", wav, "audio/wav"))],
                           options={"headers": {"Accept": "application/json", "Content-Type": "multipart/form-data"}})  # the SDK then adds the boundary itself
    except Exception as e:  # a status error from the API carries its message; anything else is a connection problem
        raise RuntimeError(f"speech to text failed ({type(e).__name__}): {str(e)[:200]}") from None
