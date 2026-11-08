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
