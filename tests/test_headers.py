from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app, security_headers

SETTINGS = Settings(
    gemini_api_key="", gemini_model="m", llm_timeout_seconds=1.0, openaq_api_key=""
)


def test_framing_is_blocked_by_default():
    headers = security_headers("'none'")
    assert headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]


def test_hosting_allowlist_replaces_the_block(monkeypatch):
    monkeypatch.setenv("FRAME_ANCESTORS", "https://huggingface.co https://*.hf.space")
    with TestClient(create_app(SETTINGS)) as client:
        response = client.get("/healthz")
    policy = response.headers["content-security-policy"]
    assert "frame-ancestors https://huggingface.co https://*.hf.space" in policy
    assert "x-frame-options" not in response.headers
