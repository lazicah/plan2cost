import pytest

from plan2cost.facts.spoken_inputs import clean, read_spoken_inputs
from plan2cost.kit.voice import is_wav, transcribe

WAV = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 60


class FakeClient:
    def __init__(self):
        self.calls = []

    def post(self, path, **kw):
        self.calls.append((path, kw))
        return {"transcript": "three metres hip roof", "audioDurationMs": 2000, "turns": []}


def test_a_recording_is_sent_as_push_to_talk_wav_to_the_voice_model():
    c = FakeClient()
    out = transcribe(WAV, client=c)
    path, kw = c.calls[0]
    assert path == "/asr/transcribe" and out["transcript"] == "three metres hip roof"
    parts = dict(kw["files"])
    assert '"muse-voice-transcribe-1.0"' in parts["request"][1] and '"PUSH_TO_TALK"' in parts["request"][1] and parts["audio"][2] == "audio/wav"


def test_only_wav_recordings_of_a_sane_size_are_accepted():
    assert is_wav(WAV) and not is_wav(b"OggS" + b"\x00" * 100)
    with pytest.raises(ValueError):
        transcribe(b"not audio at all, and long enough to pass a length check......", client=FakeClient())


def test_spoken_values_are_kept_only_when_they_make_sense_for_the_form():
    assert clean({"storey_height_m": 3, "roof_type": "hip", "pitch_deg": 30, "overhang_m": 0.5, "finish_level": "premium"}) == {"storey_height_m": 3.0, "roof_type": "hip", "pitch_deg": 30.0, "overhang_m": 0.5, "finish_level": "premium"}
    assert clean({"storey_height_m": 30, "roof_type": "dome", "pitch_deg": 90, "overhang_m": 9, "finish_level": "luxury"}) == {}  # feet taken for metres, a roof we hold no data for, nonsense
    assert clean({"storey_height_m": None, "roof_type": None}) == {}


def test_nothing_said_means_no_model_call_and_nothing_filled(monkeypatch):
    import plan2cost.kit.client as client

    monkeypatch.setattr(client, "chat_json", lambda content: (_ for _ in ()).throw(AssertionError("no call expected")))
    assert read_spoken_inputs("   ") == {}
