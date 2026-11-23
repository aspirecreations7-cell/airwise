import os

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
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_FALLBACK_MODELS", raising=False)
    settings = get_settings()
    assert settings.gemini_model == "gemini-3.5-flash"
    assert "gemini-3.1-flash-lite" in settings.gemini_fallback_models
    assert os.environ.get("GEMINI_FALLBACK_MODELS") is None
