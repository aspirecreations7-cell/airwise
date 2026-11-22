"""Shared helpers and payloads shaped like real OpenAQ v3 responses."""
from datetime import UTC, datetime

import httpx
import respx

from app.services import openaq

NOW = datetime(2026, 11, 21, 1, 0, tzinfo=UTC)
FRESH = "2026-11-21T00:15:00Z"
STALE = "2022-10-16T16:00:00Z"
OLD_STATION = "2018-02-22T02:45:00Z"
LOCATIONS_URL = f"{openaq.BASE_URL}/locations"


def station_url(station_id, suffix=""):
    return f"{openaq.BASE_URL}/locations/{station_id}{suffix}"


def location_item(station_id, name, lat, lon, last):
    return {
        "id": station_id,
        "name": name,
        "coordinates": {"latitude": lat, "longitude": lon},
        "datetimeLast": {"utc": last},
    }


def sensors_payload(*rows):
    sensors = [{"id": sid, "parameter": {"name": name, "units": units}} for sid, name, units in rows]
    return {"results": [{"sensors": sensors}]}


def latest_payload(*rows):
    return {
        "results": [
            {"sensorsId": sid, "value": value, "datetime": {"utc": utc}} for sid, value, utc in rows
        ]
    }


# Mirrors station 5548 (BTM Layout, Bengaluru - CPCB): duplicate sensors, only one fresh.
BTM_SENSORS = sensors_payload(
    (14635, "pm25", "ug/m3"),
    (12235361, "pm25", "ug/m3"),
    (1305377, "pm10", "ug/m3"),
    (12235360, "pm10", "ug/m3"),
    (12235358, "no2", "ppb"),
)
BTM_LATEST = latest_payload(
    (14635, 24.01, STALE),
    (12235361, 50.27, FRESH),
    (1305377, 57.7, STALE),
    (12235360, 168.59, FRESH),
    (12235358, 16.81, FRESH),
)
STALE_ONLY_LATEST = latest_payload((14635, 24.01, STALE), (1305377, 57.7, STALE))


def mock_locations(*items, status=200):
    body = {"results": list(items)}
    return respx.get(LOCATIONS_URL).mock(return_value=httpx.Response(status, json=body))


def mock_station(station_id, sensors, latest):
    respx.get(station_url(station_id)).mock(return_value=httpx.Response(200, json=sensors))
    respx.get(station_url(station_id, "/latest")).mock(
        return_value=httpx.Response(200, json=latest)
    )
