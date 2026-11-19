import pytest

from app.schemas import Profile
from app.services.engine import aqi_category, assess, personal_tier


@pytest.mark.parametrize(
    "aqi,expected",
    [
        (0, "good"), (50, "good"), (51, "moderate"), (100, "moderate"),
        (101, "unhealthy_for_sensitive_groups"), (150, "unhealthy_for_sensitive_groups"),
        (151, "unhealthy"), (200, "unhealthy"), (201, "very_unhealthy"),
        (300, "very_unhealthy"), (301, "hazardous"), (500, "hazardous"), (650, "hazardous"),
    ],
)
def test_aqi_category_boundaries(aqi, expected):
    assert aqi_category(aqi) == expected


def test_negative_aqi_is_rejected():
    with pytest.raises(ValueError):
        aqi_category(-1)


def test_good_air_is_never_escalated():
    profile = Profile(has_children=True, outdoor_worker=True)
    assert personal_tier(40, profile) == "good"


def test_default_profile_on_moderate_air_has_no_restrictions():
    result = assess(99, Profile())
    assert result.personal_tier == "moderate"
    assert result.constraints["outdoor_exercise"] == "normal"


def test_sensitive_group_escalates_moderate_air():
    result = assess(99, Profile(has_children=True))
    assert result.personal_tier == "unhealthy_for_sensitive_groups"
    assert result.constraints["outdoor_exercise"] == "light_only"


def test_outdoor_worker_and_sensitive_group_escalate_twice():
    profile = Profile(respiratory_condition=True, outdoor_worker=True)
    assert personal_tier(99, profile) == "unhealthy"


def test_tier_is_capped_at_hazardous():
    profile = Profile(has_elderly=True, outdoor_worker=True)
    assert personal_tier(400, profile) == "hazardous"


def test_purifier_rule():
    assert assess(160, Profile(has_purifier=True)).constraints["purifier"] == "run_continuously"
    assert assess(160, Profile()).constraints["purifier"] == "recommended"


def test_exposed_commute_is_flagged_only_when_air_is_poor():
    assert assess(120, Profile(commute_mode="two_wheeler")).constraints["commute"] == "reduce_exposure"
    assert assess(60, Profile(commute_mode="two_wheeler")).constraints["commute"] == "no_change"
