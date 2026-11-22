"""OpenAQ v3 client: nearest fresh monitoring station with live PM2.5 and PM10."""
import math
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx

from app.schemas import AirReading, Location
from app.services.aqi import AirDataError
from app.services.aqi_calc import us_aqi_from_pm

BASE_URL = "https://api.openaq.org/v3"
PM25_PARAMETER_ID = 2
SEARCH_RADIUS_M = 25000
MAX_AGE = timedelta(hours=6)
CLOCK_SKEW = timedelta(minutes=10)
MAX_STATIONS_TRIED = 3
IST = timezone(timedelta(hours=5, minutes=30))
SOURCE_NAME = "OpenAQ (live monitoring stations)"
AQI_METHOD = "US AQI computed from PM2.5 and PM10 (US EPA breakpoints)"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def parse_utc(text: str | None) -> datetime | None:
    """Parse an ISO timestamp from OpenAQ into an aware datetime."""
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def is_fresh(when: datetime | None, now: datetime) -> bool:
    """True if a timestamp is recent enough to present as live data."""
    if when is None:
        return False
    return -CLOCK_SKEW <= now - when <= MAX_AGE


async def _get(
    client: httpx.AsyncClient, path: str, params: dict[str, Any], api_key: str
) -> dict[str, Any]:
    try:
        response = await client.get(
            f"{BASE_URL}{path}", params=params, headers={"X-API-Key": api_key}
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise AirDataError("Station data service unavailable") from exc


def pick_pm_values(
    sensors: list[dict[str, Any]], latest: list[dict[str, Any]], now: datetime
) -> dict[str, tuple[float, datetime]]:
    """Per pollutant, the freshest value across duplicate sensors, ignoring stale ones."""
    names: dict[Any, str] = {}
    for sensor in sensors:
        parameter = sensor.get("parameter") or {}
        name = parameter.get("name")
        if sensor.get("id") is not None and name in ("pm25", "pm10"):
            if "g/m" in (parameter.get("units") or ""):
                names[sensor["id"]] = name
    best: dict[str, tuple[float, datetime]] = {}
    for item in latest:
        name = names.get(item.get("sensorsId"))
        value = item.get("value")
        when = parse_utc((item.get("datetime") or {}).get("utc"))
        if name is None or value is None or value < 0 or not is_fresh(when, now):
            continue
        if name not in best or when > best[name][1]:
            best[name] = (float(value), when)
    return best


def _nearest_fresh(
    items: list[dict[str, Any]], origin: Location, now: datetime
) -> list[tuple[float, dict[str, Any]]]:
    found = []
    for item in items:
        last = parse_utc((item.get("datetimeLast") or {}).get("utc"))
        coords = item.get("coordinates") or {}
        lat, lon = coords.get("latitude"), coords.get("longitude")
        if lat is None or lon is None or not is_fresh(last, now):
            continue
        found.append((haversine_km(origin.latitude, origin.longitude, lat, lon), item))
    found.sort(key=lambda pair: pair[0])
    return found


async def _station_reading(
    client: httpx.AsyncClient,
    item: dict[str, Any],
    distance: float,
    api_key: str,
    now: datetime,
) -> AirReading | None:
    station_id = item.get("id")
    if station_id is None:
        return None
    detail = await _get(client, f"/locations/{station_id}", {}, api_key)
    latest = await _get(client, f"/locations/{station_id}/latest", {"limit": 100}, api_key)
    sensors = ((detail.get("results") or [{}])[0]).get("sensors") or []
    values = pick_pm_values(sensors, latest.get("results") or [], now)
    pm25 = values.get("pm25")
    pm10 = values.get("pm10")
    aqi = us_aqi_from_pm(pm25[0] if pm25 else None, pm10[0] if pm10 else None)
    if aqi is None:
        return None
    observed = min(when for _, when in values.values())
    return AirReading(
        us_aqi=aqi,
        pm2_5=pm25[0] if pm25 else None,
        pm10=pm10[0] if pm10 else None,
        observed_at=observed.astimezone(IST).isoformat(timespec="minutes"),
        source=SOURCE_NAME,
        station=item.get("name", ""),
        distance_km=round(distance, 1),
        aqi_method=AQI_METHOD,
    )


async def fetch_openaq_reading(
    client: httpx.AsyncClient,
    location: Location,
    api_key: str,
    now: datetime | None = None,
) -> AirReading:
    """Return a live reading from the nearest station that has fresh PM data."""
    if not api_key:
        raise AirDataError("OpenAQ API key is not configured")
    now = now or datetime.now(UTC)
    params = {
        "coordinates": f"{location.latitude:.4f},{location.longitude:.4f}",
        "radius": SEARCH_RADIUS_M,
        "parameters_id": PM25_PARAMETER_ID,
        "limit": 100,
    }
    data = await _get(client, "/locations", params, api_key)
    candidates = _nearest_fresh(data.get("results") or [], location, now)
    for distance, item in candidates[:MAX_STATIONS_TRIED]:
        reading = await _station_reading(client, item, distance, api_key, now)
        if reading is not None:
            return reading
    raise AirDataError("No recent station data near this location")
