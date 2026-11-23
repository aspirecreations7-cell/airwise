import httpx
import pytest
import respx

from app.schemas import Location, Profile
from app.services import planner
from app.services.aqi import AIR_URL
from tests.planner_helpers import AT_0730, AT_1320, AT_1830, AT_2230, hourly_payload

PLACE = Location(name="Mysuru", latitude=12.3, longitude=76.64)


@pytest.fixture(autouse=True)
def fresh_cache():
    planner.clear_cache()
    yield
    planner.clear_cache()


def plan_at(moment, profile=None, overrides=None):
    data = hourly_payload(overrides)
    return planner.build_day_plan(
        data["hourly"]["time"], data["hourly"]["us_aqi"], 19800, profile or Profile(), moment
    )


def test_three_periods_with_labels_and_values():
    plan = plan_at(AT_0730)
    assert [p.period for p in plan.periods] == ["morning", "afternoon", "evening"]
    assert [p.label for p in plan.periods] == [
        "6 am to 11 am",
        "11 am to 5 pm",
        "5 pm to 10 pm",
    ]
    assert [p.avg_aqi for p in plan.periods] == [135, 95, 150]
    assert [p.best_hour for p in plan.periods] == ["10 am", "1 pm", "5 pm"]
    assert [p.best_hour_aqi for p in plan.periods] == [120, 80, 130]
    assert plan.date == "2026-11-23"
    assert plan.source.startswith("Open-Meteo")


def test_cleanest_period_is_marked():
    plan = plan_at(AT_0730)
    assert [p.period for p in plan.periods if p.cleanest] == ["afternoon"]


def test_past_hours_are_dropped():
    plan = plan_at(AT_1320)
    assert [p.period for p in plan.periods] == ["afternoon", "evening"]
    assert plan.periods[0].avg_aqi == 95


def test_single_remaining_period_is_not_called_cleanest():
    plan = plan_at(AT_1830)
    assert [p.period for p in plan.periods] == ["evening"]
    assert plan.periods[0].avg_aqi == 155
    assert not plan.periods[0].cleanest


def test_nothing_left_today_gives_none():
    assert plan_at(AT_2230) is None


def test_missing_values_are_skipped():
    plan = plan_at(AT_0730, overrides={8: None})
    assert plan.periods[0].avg_aqi == 133


def test_household_changes_the_verdict():
    default = plan_at(AT_0730)
    family = plan_at(AT_0730, Profile(has_children=True))
    assert [p.outdoor for p in default.periods][:2] == ["light_only", "normal"]
    assert [p.outdoor for p in family.periods][:2] == ["avoid", "light_only"]


@respx.mock
async def test_fetch_requests_hourly_forecast_in_local_time():
    route = respx.get(AIR_URL).mock(return_value=httpx.Response(200, json=hourly_payload()))
    async with httpx.AsyncClient() as client:
        plan = await planner.get_day_plan(client, PLACE, Profile(), at=AT_0730)
    assert len(plan.periods) == 3
    params = route.calls.last.request.url.params
    assert params["hourly"] == "us_aqi"
    assert params["timezone"] == "auto"


@respx.mock
async def test_forecast_is_cached():
    route = respx.get(AIR_URL).mock(return_value=httpx.Response(200, json=hourly_payload()))
    async with httpx.AsyncClient() as client:
        await planner.get_day_plan(client, PLACE, Profile(), at=AT_0730, mono=lambda: 0.0)
        await planner.get_day_plan(client, PLACE, Profile(), at=AT_0730, mono=lambda: 0.0)
    assert route.call_count == 1


@respx.mock
async def test_forecast_service_error_gives_none():
    respx.get(AIR_URL).mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as client:
        assert await planner.get_day_plan(client, PLACE, Profile(), at=AT_0730) is None


@respx.mock
async def test_malformed_forecast_gives_none():
    respx.get(AIR_URL).mock(return_value=httpx.Response(200, json={"current": {}}))
    async with httpx.AsyncClient() as client:
        assert await planner.get_day_plan(client, PLACE, Profile(), at=AT_0730) is None
