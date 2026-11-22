"""Convert PM concentrations (ug/m3) to US AQI sub-indices using EPA breakpoints."""
import math

Breakpoints = list[tuple[float, float, int, int]]

# (concentration low, concentration high, AQI low, AQI high)
PM25_BREAKPOINTS: Breakpoints = [
    (0.0, 9.0, 0, 50),
    (9.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200),
    (125.5, 225.4, 201, 300),
    (225.5, 325.4, 301, 500),
]
PM10_BREAKPOINTS: Breakpoints = [
    (0, 54, 0, 50),
    (55, 154, 51, 100),
    (155, 254, 101, 150),
    (255, 354, 151, 200),
    (355, 424, 201, 300),
    (425, 504, 301, 400),
    (505, 604, 401, 500),
]


def _sub_index(value: float | None, table: Breakpoints, decimals: int) -> int | None:
    """Linear interpolation inside the matching breakpoint band, capped at 500."""
    if value is None or value < 0:
        return None
    scale = 10**decimals
    truncated = math.floor(value * scale + 1e-9) / scale
    if truncated > table[-1][1]:
        return table[-1][3]
    for c_low, c_high, a_low, a_high in table:
        if truncated <= c_high:
            return round((a_high - a_low) / (c_high - c_low) * (truncated - c_low) + a_low)
    return table[-1][3]


def pm25_to_aqi(value: float | None) -> int | None:
    """AQI sub-index for PM2.5 (truncated to one decimal, as EPA specifies)."""
    return _sub_index(value, PM25_BREAKPOINTS, 1)


def pm10_to_aqi(value: float | None) -> int | None:
    """AQI sub-index for PM10 (truncated to a whole number)."""
    return _sub_index(value, PM10_BREAKPOINTS, 0)


def us_aqi_from_pm(pm25: float | None, pm10: float | None) -> int | None:
    """Overall AQI is the worst sub-index. Returns None if both inputs are missing."""
    indices = [i for i in (pm25_to_aqi(pm25), pm10_to_aqi(pm10)) if i is not None]
    return max(indices) if indices else None
