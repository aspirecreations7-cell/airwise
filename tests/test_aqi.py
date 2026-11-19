import httpx
import pytest
import respx

from app.schemas import Location
from app.services import aqi
from app.services.aqi import CACHE_TTL_SECONDS, AirDataError, fetch_air_quality, geocode

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
    "current": {
        "time": "2026-11-19T15:30",
        "us_aqi": 99,
        "pm2_5": 37.8,
        "pm10": 40.7,
        "nitrogen_dioxide": 7.1,
        "ozone": 156.0,
    }
}
PLACE = Location(name="Mysuru", latitude=12.29791, longitude=76.63925)


@pytest.fixture(autouse=True)
def fresh_cache():
    aqi.clear_cache()
    yield
    aqi.clear_cache()


@respx.mock
async def test_geocode_returns_first_match():
    respx.get(aqi.GEOCODE_URL).mock(return_value=httpx.Response(200, json=GEO))
    async with httpx.AsyncClient() as client:
        place = await geocode(client, "Mysuru")
    assert place.name == "Mysuru"
    assert place.country == "India"


@respx.mock
async def test_geocode_maps_old_city_names():
    route = respx.get(aqi.GEOCODE_URL).mock(return_value=httpx.Response(200, json=GEO))
    async with httpx.AsyncClient() as client:
        await geocode(client, "Mysore")
    assert route.calls.last.request.url.params["name"] == "mysuru"


@respx.mock
async def test_geocode_unknown_city_raises():
    respx.get(aqi.GEOCODE_URL).mock(return_value=httpx.Response(200, json={}))
    async with httpx.AsyncClient() as client:
        with pytest.raises(AirDataError):
            await geocode(client, "Nowhereville")


async def test_geocode_blank_city_raises():
    async with httpx.AsyncClient() as client:
        with pytest.raises(AirDataError):
            await geocode(client, "   ")


@respx.mock
async def test_geocode_service_error_raises():
    respx.get(aqi.GEOCODE_URL).mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as client:
        with pytest.raises(AirDataError):
            await geocode(client, "Mysuru")


@respx.mock
async def test_fetch_returns_reading_and_requests_local_time():
    route = respx.get(aqi.AIR_URL).mock(return_value=httpx.Response(200, json=AIR))
    async with httpx.AsyncClient() as client:
        reading = await fetch_air_quality(client, PLACE)
    assert reading.us_aqi == 99
    assert reading.pm2_5 == 37.8
    assert route.calls.last.request.url.params["timezone"] == "auto"


@respx.mock
async def test_second_call_is_served_from_cache():
    route = respx.get(aqi.AIR_URL).mock(return_value=httpx.Response(200, json=AIR))
    async with httpx.AsyncClient() as client:
        await fetch_air_quality(client, PLACE)
        await fetch_air_quality(client, PLACE)
    assert route.call_count == 1


@respx.mock
async def test_cache_expires_after_ttl():
    route = respx.get(aqi.AIR_URL).mock(return_value=httpx.Response(200, json=AIR))
    async with httpx.AsyncClient() as client:
        await fetch_air_quality(client, PLACE, now=lambda: 0.0)
        await fetch_air_quality(client, PLACE, now=lambda: CACHE_TTL_SECONDS + 1)
    assert route.call_count == 2


@respx.mock
async def test_missing_aqi_raises():
    bad = {"current": {"time": "2026-11-19T15:30", "us_aqi": None}}
    respx.get(aqi.AIR_URL).mock(return_value=httpx.Response(200, json=bad))
    async with httpx.AsyncClient() as client:
        with pytest.raises(AirDataError):
            await fetch_air_quality(client, PLACE)


@respx.mock
async def test_timeout_raises_clean_error():
    respx.get(aqi.AIR_URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(AirDataError):
            await fetch_air_quality(client, PLACE)
