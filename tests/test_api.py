from types import SimpleNamespace

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services import air, aqi
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
AIR = {
    "utc_offset_seconds": 19800,
    "current": {"time": "2026-11-21T10:30", "us_aqi": 99, "pm2_5": 37.8, "pm10": 40.7},
}
BODY = {
    "city": "Mysuru",
    "profile": {"has_children": True, "commute_mode": "car", "commute_km": 10},
    "language": "en",
}


@pytest.fixture(autouse=True)
def fresh_caches():
    air.clear_cache()
    aqi.clear_cache()
    yield
    air.clear_cache()
    aqi.clear_cache()


@pytest.fixture
def router():
    """A respx router that also blocks any request we forgot to mock."""
    with respx.mock(assert_all_called=False) as mock:
        yield mock


def mock_upstream(router, geo=None, air_status=200):
    geo_route = router.get(aqi.GEOCODE_URL).mock(
        return_value=httpx.Response(200, json=GEO if geo is None else geo)
    )
    air_route = router.get(aqi.AIR_URL).mock(
        return_value=httpx.Response(air_status, json=AIR)
    )
    return geo_route, air_route


def make_client(**kwargs):
    return TestClient(create_app(SETTINGS, **kwargs))


def test_health_and_security_headers():
    with make_client() as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_advice_by_city_uses_fallback_without_llm(router):
    mock_upstream(router)
    with make_client() as client:
        response = client.post("/api/advice", json=BODY)
    assert response.status_code == 200
    data = response.json()
    assert data["advice_source"] == "fallback"
    assert data["reading"]["source"].startswith("Open-Meteo")
    assert data["reading"]["observed_at"] == "2026-11-21T10:30+05:30"
    assert data["assessment"]["personal_tier"] == "unhealthy_for_sensitive_groups"
    assert "Mysuru" in data["advice"]["summary"]
    assert "not medical advice" in data["disclaimer"].lower()


def test_advice_uses_gemini_when_available(router):
    mock_upstream(router)
    models = FakeModels(result=SimpleNamespace(parsed=sample_advice(), text=""))
    with make_client(llm_client=fake_client(models)) as client:
        data = client.post("/api/advice", json=BODY).json()
    assert data["advice_source"] == "gemini"
    sent = models.calls[0]["contents"]
    assert "Open-Meteo" in sent
    assert "unhealthy_for_sensitive_groups" in sent


def test_coordinates_skip_geocoding(router):
    geo_route, _ = mock_upstream(router)
    body = {"latitude": 12.3, "longitude": 76.64, "profile": {}}
    with make_client() as client:
        data = client.post("/api/advice", json=body).json()
    assert geo_route.call_count == 0
    assert data["location"]["name"] == "Your location"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"city": "x"},
        {"city": "<script>alert(1)</script>"},
        {"latitude": 12.3},
        {"latitude": 51.5, "longitude": -0.12},
        {"city": "Mysuru", "profile": {"commute_mode": "rocket"}},
        {"city": "Mysuru", "profile": {"commute_km": 500}},
        {"city": "Mysuru", "extra": 1},
        {"city": "Mysuru", "language": "fr"},
    ],
)
def test_invalid_requests_are_rejected(body):
    with make_client() as client:
        assert client.post("/api/advice", json=body).status_code == 422


def test_unknown_city_returns_404(router):
    mock_upstream(router, geo={})
    with make_client() as client:
        response = client.post("/api/advice", json=BODY)
    assert response.status_code == 404
    assert "Could not find" in response.json()["detail"]


def test_air_service_failure_returns_503(router):
    mock_upstream(router, air_status=500)
    with make_client() as client:
        response = client.post("/api/advice", json=BODY)
    assert response.status_code == 503
    assert response.json()["detail"] == "Air quality service unavailable"


def test_rate_limit_returns_429(router):
    mock_upstream(router)
    with make_client(rate_limit=2) as client:
        codes = [client.post("/api/advice", json=BODY).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_daily_budget_forces_fallback(router):
    mock_upstream(router)
    models = FakeModels(result=SimpleNamespace(parsed=sample_advice(), text=""))
    with make_client(llm_client=fake_client(models), daily_llm_limit=1) as client:
        first = client.post("/api/advice", json=BODY).json()
        second = client.post("/api/advice", json=BODY).json()
    assert first["advice_source"] == "gemini"
    assert second["advice_source"] == "fallback"
    assert len(models.calls) == 1


def test_llm_failure_still_returns_advice(router):
    mock_upstream(router)
    models = FakeModels(error=RuntimeError("boom"))
    with make_client(llm_client=fake_client(models)) as client:
        response = client.post("/api/advice", json=BODY)
    assert response.status_code == 200
    assert response.json()["advice_source"] == "fallback"
