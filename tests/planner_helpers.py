"""Shared forecast data for the day planner tests."""
from datetime import UTC, datetime

TODAY_VALUES = {hour: 100 for hour in range(6)} | {
    6: 160, 7: 150, 8: 140, 9: 130, 10: 120,
    11: 100, 12: 90, 13: 80, 14: 90, 15: 100, 16: 110,
    17: 130, 18: 150, 19: 170, 20: 160, 21: 140,
    22: 120, 23: 120,
}

# Local India time is UTC plus 5 hours 30 minutes.
AT_0730 = datetime(2026, 11, 23, 2, 0, tzinfo=UTC)
AT_1320 = datetime(2026, 11, 23, 7, 50, tzinfo=UTC)
AT_1830 = datetime(2026, 11, 23, 13, 0, tzinfo=UTC)
AT_2230 = datetime(2026, 11, 23, 17, 0, tzinfo=UTC)


def hourly_payload(overrides=None):
    """Two days of hourly AQI. Tomorrow is 500 everywhere so leaks are obvious."""
    today = TODAY_VALUES | (overrides or {})
    times, values = [], []
    for hour in range(24):
        times.append(f"2026-11-23T{hour:02d}:00")
        values.append(today[hour])
    for hour in range(24):
        times.append(f"2026-11-24T{hour:02d}:00")
        values.append(500)
    return {"utc_offset_seconds": 19800, "hourly": {"time": times, "us_aqi": values}}
