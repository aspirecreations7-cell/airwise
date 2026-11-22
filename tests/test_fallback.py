from app.schemas import Profile
from app.services import engine, impact
from app.services.fallback import MAX_ROUTINE_ITEMS, fallback_advice


def advice_for(aqi, **flags):
    profile = Profile(**flags)
    assessment = engine.assess(aqi, profile)
    saving = impact.commute_saving(profile.commute_mode, profile.commute_km)
    return fallback_advice("Mysuru", assessment, saving, profile.model_dump())


def titles(advice):
    return [action.title.lower() for action in advice.daily_routine]


def test_children_get_child_specific_advice_on_poor_air():
    assert any("children" in title for title in titles(advice_for(120, has_children=True)))


def test_children_may_play_outside_on_good_air():
    assert any("play is fine" in title for title in titles(advice_for(40, has_children=True)))


def test_older_adults_and_respiratory_conditions_get_their_own_advice():
    text = " ".join(titles(advice_for(120, has_elderly=True, respiratory_condition=True)))
    assert "older" in text
    assert "medicines" in text


def test_two_wheeler_commute_gets_helmet_advice():
    assert any("helmet" in title for title in titles(advice_for(160, commute_mode="two_wheeler")))


def test_different_households_get_different_advice():
    family = advice_for(120, has_children=True, commute_mode="car")
    rider = advice_for(120, outdoor_worker=True, commute_mode="two_wheeler")
    assert titles(family) != titles(rider)


def test_car_commuters_are_offered_a_switch():
    advice = advice_for(120, commute_mode="car")
    assert "public transport" in advice.sustainable_alternatives[0].title.lower()
    assert "12.0" in advice.impact_explanation


def test_routine_is_capped():
    advice = advice_for(
        120,
        has_children=True,
        has_elderly=True,
        respiratory_condition=True,
        pregnant=True,
        outdoor_worker=True,
    )
    assert len(advice.daily_routine) <= MAX_ROUTINE_ITEMS


def test_missing_household_still_works():
    assessment = engine.assess(120, Profile())
    advice = fallback_advice("Mysuru", assessment, {})
    assert advice.daily_routine
    assert advice.indoor_air_hacks
    assert advice.sustainable_alternatives


def test_no_numbers_are_invented_without_an_impact_estimate():
    advice = advice_for(120)
    assert not any(char.isdigit() for char in advice.impact_explanation)


def test_plants_are_addressed_honestly():
    advice = advice_for(120)
    assert any("plants" in action.title.lower() for action in advice.indoor_air_hacks)
