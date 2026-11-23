from types import SimpleNamespace

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services import air, aqi, planner
from tests.planner_helpers import AT_0730, hourly_payload
from tests.test_llm import FakeModels, fake_client, sample_advice

SETTINGS = Settings(
    gemini_api_key="", gemini_model="m", llm_timeout_seconds=1.0, openaq_api_key=""
)
GEO = {
    "results": [
        {
            "name": "Mysuru",
            "latitude": 12.29791,
            "longitude": 76.63925,
            "country": "India",
            "admin1": "Karnataka",
        }
    ]
}
CURRENT = {"time": "2026-11-23T07:30", "us_aqi": 99, "pm2_5": 37.8, "pm10": 40.7}
BODY = {"city": "Mysuru", "profile": {"has_children": True}, "language": "en"}


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    for module in (air, aqi, planner):
        module.clear_cache()
    monkeypatch.setattr(planner, "utc_now", lambda: AT_0730)
    yield
    for module in (air, aqi, planner):
        module.clear_cache()


@pytest.fixture
def router():
    with respx.mock(assert_all_called=False) as mock:
        yield mock


def mock_upstream(router, with_forecast=True):
    base = hourly_payload() if with_forecast else {"utc_offset_seconds": 19800}
    router.get(aqi.GEOCODE_URL).mock(return_value=httpx.Response(200, json=GEO))
    router.get(aqi.AIR_URL).mock(
        return_value=httpx.Response(200, json={**base, "current": CURRENT})
    )


def test_response_includes_the_day_plan(router):
    mock_upstream(router)
    with TestClient(create_app(SETTINGS)) as client:
        data = client.post("/api/advice", json=BODY).json()
    plan = data["day_plan"]
    assert plan["date"] == "2026-11-23"
    assert [p["period"] for p in plan["periods"]] == ["morning", "afternoon", "evening"]
    assert [p["period"] for p in plan["periods"] if p["cleanest"]] == ["afternoon"]
    assert plan["source"].startswith("Open-Meteo")


def test_gemini_receives_the_day_plan(router):
    mock_upstream(router)
    models = FakeModels(result=SimpleNamespace(parsed=sample_advice(), text=""))
    with TestClient(create_app(SETTINGS, llm_client=fake_client(models))) as client:
        client.post("/api/advice", json=BODY)
    assert "day_plan" in models.calls[0]["contents"]


def test_missing_forecast_does_not_break_advice(router):
    mock_upstream(router, with_forecast=False)
    with TestClient(create_app(SETTINGS)) as client:
        response = client.post("/api/advice", json=BODY)
    assert response.status_code == 200
    assert response.json()["day_plan"] is None
