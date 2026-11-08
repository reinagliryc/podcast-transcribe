import json

import pytest

from podcast_transcribe.groq import find_api_key


def test_key_precedence(tmp_path, monkeypatch):
    (tmp_path / "keys.json").write_text(json.dumps({"groq": "from-llm"}))
    monkeypatch.setenv("LLM_USER_PATH", str(tmp_path))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert find_api_key() == "from-llm"
    monkeypatch.setenv("GROQ_API_KEY", "from-env")
    assert find_api_key() == "from-env"
    assert find_api_key("explicit") == "explicit"


def test_missing_key(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_USER_PATH", str(tmp_path))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="no Groq API key"):
        find_api_key()


@pytest.fixture
def clean_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_USER_PATH", str(tmp_path / "nollm"))
    for var in ("GROQ_API_KEY", "GROQ_API_KEY_FILE", "CREDENTIALS_DIRECTORY"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_key_file_sources(tmp_path, clean_env):
    (tmp_path / "groq.key").write_text("from-file\n")
    assert find_api_key(key_file=tmp_path / "groq.key") == "from-file"

    clean_env.setenv("GROQ_API_KEY_FILE", str(tmp_path / "groq.key"))
    assert find_api_key() == "from-file"
    clean_env.setenv("GROQ_API_KEY", "from-env")
    assert find_api_key() == "from-env", "GROQ_API_KEY beats GROQ_API_KEY_FILE"
    assert find_api_key(key_file=tmp_path / "groq.key") == "from-file", "CLI beats env"


def test_systemd_credentials(tmp_path, clean_env):
    creds = tmp_path / "creds"
    creds.mkdir()
    clean_env.setenv("CREDENTIALS_DIRECTORY", str(creds))
    with pytest.raises(RuntimeError, match="no Groq API key"):
        find_api_key()
    (creds / "groq").write_text("from-systemd")
    assert find_api_key() == "from-systemd"


def test_bad_key_file_is_an_error_not_a_fallback(tmp_path, clean_env):
    (tmp_path / "keys.json").write_text(json.dumps({"groq": "from-llm"}))
    clean_env.setenv("LLM_USER_PATH", str(tmp_path))
    with pytest.raises(RuntimeError, match="cannot read"):
        find_api_key(key_file=tmp_path / "missing")
    (tmp_path / "empty").write_text("\n")
    with pytest.raises(RuntimeError, match="empty"):
        find_api_key(key_file=tmp_path / "empty")
