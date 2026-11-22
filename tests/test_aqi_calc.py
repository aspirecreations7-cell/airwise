import pytest

from app.services.aqi_calc import pm10_to_aqi, pm25_to_aqi, us_aqi_from_pm


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, 0), (9.0, 50), (9.1, 51), (35.4, 100), (35.5, 101), (55.4, 150),
        (55.5, 151), (125.4, 200), (125.5, 201), (225.4, 300), (225.5, 301),
        (325.4, 500), (999, 500), (50.27, 137),
    ],
)
def test_pm25_breakpoints(value, expected):
    assert pm25_to_aqi(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, 0), (54, 50), (55, 51), (154, 100), (155, 101), (254, 150), (255, 151),
        (354, 200), (355, 201), (424, 300), (425, 301), (504, 400), (505, 401),
        (604, 500), (999, 500), (168.59, 107),
    ],
)
def test_pm10_breakpoints(value, expected):
    assert pm10_to_aqi(value) == expected


def test_missing_or_negative_input_gives_none():
    assert pm25_to_aqi(None) is None
    assert pm10_to_aqi(-1) is None
    assert us_aqi_from_pm(None, None) is None


def test_overall_aqi_is_the_worst_sub_index():
    assert us_aqi_from_pm(50.27, 168.59) == 137
    assert us_aqi_from_pm(5.0, 200) == 123
    assert us_aqi_from_pm(None, 168.59) == 107
