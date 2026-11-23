"""Day planner: ranks morning, afternoon and evening by forecast air quality."""
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.schemas import DayPlan, Location, PeriodPlan, Profile
from app.services import engine
from app.services.aqi import AIR_URL, AirDataError

logger = logging.getLogger(__name__)

SOURCE_NAME = "Open-Meteo hourly forecast (model estimate)"
NOTE = (
    "Hours are ranked using a model forecast, which can differ from the live reading "
    "above. Use the order as a guide, not an exact value."
)
CACHE_TTL_SECONDS = 30 * 60
# (name, first hour included, first hour excluded) in local time
PERIODS = (("morning", 6, 11), ("afternoon", 11, 17), ("evening", 17, 22))

_cache: dict[tuple[float, float], tuple[float, dict[str, Any]]] = {}


def clear_cache() -> None:
    """Empty the forecast cache (used by tests)."""
    _cache.clear()


def utc_now() -> datetime:
    """Current UTC time. Tests replace this function to control the clock."""
    return datetime.now(UTC)


def hour_label(hour: int) -> str:
    """Format a 24 hour clock hour as for example '5 pm'."""
    suffix = "am" if hour < 12 else "pm"
    return f"{hour % 12 or 12} {suffix}"


def range_label(start: int, end: int) -> str:
    """Format a period such as '6 am to 11 am'."""
    return f"{hour_label(start)} to {hour_label(end)}"


async def fetch_hourly(
    client: httpx.AsyncClient,
    location: Location,
    mono: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Fetch the hourly AQI forecast for today and tomorrow, cached for 30 minutes."""
    key = (round(location.latitude, 2), round(location.longitude, 2))
    cached = _cache.get(key)
    if cached and mono() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]
    params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "hourly": "us_aqi",
        "forecast_days": 2,
        "timezone": "auto",
    }
    try:
        response = await client.get(AIR_URL, params=params)
        response.raise_for_status()
        payload = response.json()
        hourly = payload["hourly"]
        data = {
            "times": hourly["time"],
            "values": hourly["us_aqi"],
            "offset": payload.get("utc_offset_seconds") or 0,
        }
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise AirDataError("Forecast service unavailable") from exc
    _cache[key] = (mono(), data)
    return data


def build_day_plan(
    times: list[str],
    values: list[Any],
    offset_seconds: int,
    profile: Profile,
    now_utc: datetime,
) -> DayPlan | None:
    """Summarise the remaining hours of today for each part of the day."""
    local_now = (now_utc + timedelta(seconds=offset_seconds)).replace(tzinfo=None)
    today = local_now.date()
    first_hour = local_now.replace(minute=0, second=0, microsecond=0)
    hours: list[tuple[datetime, int]] = []
    for stamp, value in zip(times, values, strict=False):
        if not isinstance(value, int | float) or value < 0:
            continue
        try:
            when = datetime.fromisoformat(stamp).replace(tzinfo=None)
        except (TypeError, ValueError):
            continue
        if when.date() == today and when >= first_hour:
            hours.append((when, round(value)))

    periods: list[PeriodPlan] = []
    for name, start, end in PERIODS:
        slot = [(when, value) for when, value in hours if start <= when.hour < end]
        if not slot:
            continue
        average = round(sum(value for _, value in slot) / len(slot))
        best_when, best_value = min(slot, key=lambda item: (item[1], item[0]))
        assessment = engine.assess(average, profile)
        periods.append(
            PeriodPlan(
                period=name,
                label=range_label(start, end),
                avg_aqi=average,
                best_hour=hour_label(best_when.hour),
                best_hour_aqi=best_value,
                tier=assessment.personal_tier,
                outdoor=assessment.constraints["outdoor_exercise"],
            )
        )
    if not periods:
        return None
    if len(periods) > 1:
        index = min(range(len(periods)), key=lambda i: periods[i].avg_aqi)
        periods[index] = periods[index].model_copy(update={"cleanest": True})
    return DayPlan(date=today.isoformat(), periods=periods, source=SOURCE_NAME, note=NOTE)


async def get_day_plan(
    client: httpx.AsyncClient,
    location: Location,
    profile: Profile,
    at: datetime | None = None,
    mono: Callable[[], float] = time.monotonic,
) -> DayPlan | None:
    """Return today's plan, or None if the forecast is unavailable. Never raises."""
    try:
        data = await fetch_hourly(client, location, mono)
    except AirDataError as exc:
        logger.info("Day plan unavailable for %s (%s)", location.name, exc)
        return None
    return build_day_plan(
        data["times"], data["values"], data["offset"], profile, at or utc_now()
    )
