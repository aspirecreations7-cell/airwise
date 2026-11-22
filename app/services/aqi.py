"""Open-Meteo access: geocoding and modelled air quality, with a small TTL cache."""
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import httpx

from app.schemas import AirReading, Location

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
CACHE_TTL_SECONDS = 15 * 60
TIMEOUT = httpx.Timeout(8.0)
SOURCE_NAME = "Open-Meteo Air Quality API (model estimate)"
AQI_METHOD = "US AQI as reported by Open-Meteo"
ALIASES = {
    "mysore": "mysuru",
    "bangalore": "bengaluru",
    "bombay": "mumbai",
    "madras": "chennai",
    "calcutta": "kolkata",
}

_cache: dict[tuple[float, float], tuple[float, AirReading]] = {}


class AirDataError(Exception):
    """Raised when location or air quality data cannot be obtained."""


def clear_cache() -> None:
    """Empty the reading cache (used by tests)."""
    _cache.clear()


def _local_iso(text: str, offset_seconds: int) -> str:
    """Attach the location's UTC offset to Open-Meteo's local timestamp."""
    try:
        naive = datetime.fromisoformat(text)
    except ValueError:
        return text
    zone = timezone(timedelta(seconds=offset_seconds))
    return naive.replace(tzinfo=zone).isoformat(timespec="minutes")


async def geocode(client: httpx.AsyncClient, city: str) -> Location:
    """Resolve an Indian city name to coordinates using the first match."""
    name = city.strip()
    if not name:
        raise AirDataError("City name is empty")
    name = ALIASES.get(name.lower(), name)
    params = {"name": name, "count": 1, "countryCode": "IN"}
    try:
        response = await client.get(GEOCODE_URL, params=params)
        response.raise_for_status()
        results = response.json().get("results") or []
    except (httpx.HTTPError, ValueError) as exc:
        raise AirDataError("Location service unavailable") from exc
    if not results:
        raise AirDataError(f"Could not find a place called '{city}'")
    top = results[0]
    return Location(
        name=top["name"],
        latitude=top["latitude"],
        longitude=top["longitude"],
        country=top.get("country", ""),
        region=top.get("admin1", ""),
    )


async def fetch_air_quality(
    client: httpx.AsyncClient,
    location: Location,
    now: Callable[[], float] = time.monotonic,
) -> AirReading:
    """Return the current modelled reading for a location, cached for 15 minutes."""
    key = (round(location.latitude, 2), round(location.longitude, 2))
    cached = _cache.get(key)
    if cached and now() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]
    params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "current": "us_aqi,pm2_5,pm10,nitrogen_dioxide,ozone",
        "timezone": "auto",
    }
    try:
        response = await client.get(AIR_URL, params=params)
        response.raise_for_status()
        payload = response.json()
        current = payload["current"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise AirDataError("Air quality service unavailable") from exc
    if current.get("us_aqi") is None:
        raise AirDataError("No AQI value is available for this location")
    reading = AirReading(
        us_aqi=round(current["us_aqi"]),
        pm2_5=current.get("pm2_5"),
        pm10=current.get("pm10"),
        nitrogen_dioxide=current.get("nitrogen_dioxide"),
        ozone=current.get("ozone"),
        observed_at=_local_iso(current.get("time", ""), payload.get("utc_offset_seconds") or 0),
        source=SOURCE_NAME,
        aqi_method=AQI_METHOD,
    )
    _cache[key] = (now(), reading)
    return reading
