from datetime import timedelta

import httpx
import pytest
import respx

from app.schemas import Location
from app.services import openaq
from app.services.aqi import AirDataError
from tests.openaq_helpers import (
    BTM_LATEST,
    BTM_SENSORS,
    FRESH,
    NOW,
    OLD_STATION,
    STALE_ONLY_LATEST,
    location_item,
    mock_locations,
    mock_station,
)

CITY = Location(name="Bengaluru", latitude=12.9716, longitude=77.5946)
KEY = "test-key"


@respx.mock
async def test_uses_fresh_sensors_and_ignores_stale_duplicates():
    route = mock_locations(
        location_item(412, "Peenya, Bengaluru - KSPCB", 13.0, 77.5, OLD_STATION),
        location_item(5548, "BTM Layout, Bengaluru - CPCB", 12.9135, 77.5951, FRESH),
    )
    mock_station(5548, BTM_SENSORS, BTM_LATEST)
    async with httpx.AsyncClient() as client:
        reading = await openaq.fetch_openaq_reading(client, CITY, KEY, NOW)
    assert reading.pm2_5 == 50.27
    assert reading.pm10 == 168.59
    assert reading.us_aqi == 137
    assert reading.station == "BTM Layout, Bengaluru - CPCB"
    assert reading.source.startswith("OpenAQ")
    assert reading.observed_at == "2026-11-21T05:45+05:30"
    assert 6.0 < reading.distance_km < 7.0
    request = route.calls.last.request
    assert request.headers["X-API-Key"] == KEY
    assert request.url.params["parameters_id"] == "2"


@respx.mock
async def test_nearest_fresh_station_wins():
    mock_locations(
        location_item(2, "Far", 13.20, 77.60, FRESH),
        location_item(1, "Near", 12.98, 77.59, FRESH),
    )
    mock_station(1, BTM_SENSORS, BTM_LATEST)
    async with httpx.AsyncClient() as client:
        reading = await openaq.fetch_openaq_reading(client, CITY, KEY, NOW)
    assert reading.station == "Near"


@respx.mock
async def test_falls_through_when_nearest_station_has_no_fresh_pm():
    mock_locations(
        location_item(1, "Near", 12.98, 77.59, FRESH),
        location_item(2, "Far", 13.05, 77.60, FRESH),
    )
    mock_station(1, BTM_SENSORS, STALE_ONLY_LATEST)
    mock_station(2, BTM_SENSORS, BTM_LATEST)
    async with httpx.AsyncClient() as client:
        reading = await openaq.fetch_openaq_reading(client, CITY, KEY, NOW)
    assert reading.station == "Far"


@respx.mock
async def test_only_stale_stations_raises():
    mock_locations(location_item(412, "Peenya", 13.0, 77.5, OLD_STATION))
    async with httpx.AsyncClient() as client:
        with pytest.raises(AirDataError):
            await openaq.fetch_openaq_reading(client, CITY, KEY, NOW)


@respx.mock
async def test_no_stations_raises():
    mock_locations()
    async with httpx.AsyncClient() as client:
        with pytest.raises(AirDataError):
            await openaq.fetch_openaq_reading(client, CITY, KEY, NOW)


@respx.mock
async def test_service_error_raises_clean_error():
    mock_locations(status=500)
    async with httpx.AsyncClient() as client:
        with pytest.raises(AirDataError):
            await openaq.fetch_openaq_reading(client, CITY, KEY, NOW)


async def test_missing_key_raises_without_network():
    async with httpx.AsyncClient() as client:
        with pytest.raises(AirDataError):
            await openaq.fetch_openaq_reading(client, CITY, "", NOW)


def test_pick_pm_values_ignores_bad_values():
    sensors = [
        {"id": 1, "parameter": {"name": "pm25", "units": "ug/m3"}},
        {"id": 2, "parameter": {"name": "pm10", "units": "ppb"}},
    ]
    latest = [
        {"sensorsId": 1, "value": -4, "datetime": {"utc": FRESH}},
        {"sensorsId": 2, "value": 10, "datetime": {"utc": FRESH}},
        {"sensorsId": 99, "value": 5, "datetime": {"utc": FRESH}},
    ]
    assert openaq.pick_pm_values(sensors, latest, NOW) == {}


def test_freshness_window():
    assert openaq.is_fresh(NOW - timedelta(hours=6), NOW)
    assert not openaq.is_fresh(NOW - timedelta(hours=6, seconds=1), NOW)
    assert openaq.is_fresh(NOW + timedelta(minutes=5), NOW)
    assert not openaq.is_fresh(NOW + timedelta(minutes=30), NOW)
    assert not openaq.is_fresh(None, NOW)
