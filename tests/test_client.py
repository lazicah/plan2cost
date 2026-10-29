import pytest

from plan2cost.kit import client


def test_profiles_read_their_own_settings(monkeypatch):
    monkeypatch.setenv("P2C_MODEL", "muse-spark-1.3")
    monkeypatch.setenv("P2C_OPEN_MODEL", "meta-models/muse-spark-open-1026")
    monkeypatch.delenv("P2C_PROFILE", raising=False)
    assert client.model_name() == "muse-spark-1.3"
    assert client.model_name("open") == "meta-models/muse-spark-open-1026"
    monkeypatch.setenv("P2C_PROFILE", "open")
    assert client.model_name() == "meta-models/muse-spark-open-1026"


def test_unknown_profile_is_refused(monkeypatch):
    monkeypatch.setenv("P2C_PROFILE", "other")
    with pytest.raises(ValueError):
        client.active_profile()
