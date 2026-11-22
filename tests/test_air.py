import httpx
import pytest
import respx

from app.schemas import Location
from app.services import air, aqi
from tests.openaq_helpers import (
    BTM_LATEST,
    BTM_SENSORS,
    FRESH,
    NOW,
    location_item,
    mock_locations,
    mock_station,
)

CITY = Location(name="Bengaluru", latitude=12.9716, longitude=77.5946)
OPEN_METEO = {
    "utc_offset_seconds": 19800,
    "current": {"time": "2026-11-21T10:30", "us_aqi": 99, "pm2_5": 37.8, "pm10": 40.7},
}


@pytest.fixture(autouse=True)
def fresh_caches():
    air.clear_cache()
    aqi.clear_cache()
    yield
    air.clear_cache()
    aqi.clear_cache()


@respx.mock
async def test_prefers_openaq_when_a_fresh_station_exists():
    mock_locations(location_item(5548, "BTM Layout", 12.9135, 77.5951, FRESH))
    mock_station(5548, BTM_SENSORS, BTM_LATEST)
    async with httpx.AsyncClient() as client:
        reading = await air.get_reading(client, CITY, "key", utc_now=NOW)
    assert reading.source.startswith("OpenAQ")
    assert reading.us_aqi == 137


@respx.mock
async def test_falls_back_to_open_meteo_when_no_station():
    mock_locations()
    respx.get(aqi.AIR_URL).mock(return_value=httpx.Response(200, json=OPEN_METEO))
    async with httpx.AsyncClient() as client:
        reading = await air.get_reading(client, CITY, "key", utc_now=NOW)
    assert reading.source.startswith("Open-Meteo")
    assert reading.us_aqi == 99
    assert reading.observed_at == "2026-11-21T10:30+05:30"


@respx.mock
async def test_falls_back_when_key_is_missing():
    respx.get(aqi.AIR_URL).mock(return_value=httpx.Response(200, json=OPEN_METEO))
    async with httpx.AsyncClient() as client:
        reading = await air.get_reading(client, CITY, "", utc_now=NOW)
    assert reading.source.startswith("Open-Meteo")


@respx.mock
async def test_falls_back_when_openaq_errors():
    mock_locations(status=500)
    respx.get(aqi.AIR_URL).mock(return_value=httpx.Response(200, json=OPEN_METEO))
    async with httpx.AsyncClient() as client:
        reading = await air.get_reading(client, CITY, "key", utc_now=NOW)
    assert reading.source.startswith("Open-Meteo")


@respx.mock
async def test_second_call_is_served_from_cache():
    mock_locations()
    route = respx.get(aqi.AIR_URL).mock(return_value=httpx.Response(200, json=OPEN_METEO))
    async with httpx.AsyncClient() as client:
        await air.get_reading(client, CITY, "key", utc_now=NOW, mono=lambda: 0.0)
        await air.get_reading(client, CITY, "key", utc_now=NOW, mono=lambda: 0.0)
    assert route.call_count == 1
