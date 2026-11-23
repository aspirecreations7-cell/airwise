from app.config import get_settings


def test_model_chain_settings_are_parsed(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_MODEL", "primary")
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", " a , b ,,")
    settings = get_settings()
    assert settings.gemini_model == "primary"
    assert settings.gemini_fallback_models == ("a", "b")


def test_defaults_when_not_configured(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in (
        "GEMINI_MODEL",
        "GEMINI_FALLBACK_MODELS",
        "LLM_TIMEOUT_SECONDS",
        "LLM_MODEL_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = get_settings()
    assert settings.gemini_model == "gemini-3.1-flash-lite"
    assert "gemini-3.5-flash" in settings.gemini_fallback_models
    assert settings.llm_timeout_seconds == 30.0
    assert settings.llm_model_timeout_seconds == 12.0


def test_timeouts_can_be_configured(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("LLM_MODEL_TIMEOUT_SECONDS", "8")
    settings = get_settings()
    assert settings.llm_timeout_seconds == 45.0
    assert settings.llm_model_timeout_seconds == 8.0
