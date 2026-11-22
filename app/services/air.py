"""Provider chain: OpenAQ station data first, Open-Meteo model data as the fallback."""
import logging
import time
from collections.abc import Callable
from datetime import datetime

import httpx

from app.schemas import AirReading, Location
from app.services import aqi, openaq
from app.services.aqi import CACHE_TTL_SECONDS, AirDataError

logger = logging.getLogger(__name__)

_cache: dict[tuple[float, float], tuple[float, AirReading]] = {}


def clear_cache() -> None:
    """Empty the reading cache (used by tests)."""
    _cache.clear()


async def get_reading(
    client: httpx.AsyncClient,
    location: Location,
    openaq_key: str,
    utc_now: datetime | None = None,
    mono: Callable[[], float] = time.monotonic,
) -> AirReading:
    """Return the best available live reading, labelled with its source."""
    key = (round(location.latitude, 2), round(location.longitude, 2))
    cached = _cache.get(key)
    if cached and mono() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]
    try:
        reading = await openaq.fetch_openaq_reading(client, location, openaq_key, utc_now)
    except AirDataError as exc:
        logger.info("OpenAQ unavailable for %s (%s); using Open-Meteo", location.name, exc)
        reading = await aqi.fetch_air_quality(client, location, mono)
    _cache[key] = (mono(), reading)
    return reading
