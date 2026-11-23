import pytest

from app.schemas import Action, Advice, AirReading, Location, Profile
from app.services import engine, impact
from app.services.fallback import fallback_advice
from app.services.guardrails import check_advice
from app.services.llm import build_facts

PLACE = Location(name="Mysuru", latitude=12.3, longitude=76.6)
OK = Action(title="Plan ahead", detail="Do indoor stretching.", why="Less exposure.")


def setup(aqi, profile=None):
    profile = profile or Profile(commute_mode="car", commute_km=10)
    assessment = engine.assess(aqi, profile)
    saving = impact.commute_saving(profile.commute_mode, profile.commute_km)
    reading = AirReading(us_aqi=aqi, pm2_5=40.0, pm10=60.0)
    facts = build_facts(PLACE, reading, assessment, profile, saving, "en")
    return assessment, facts, saving, profile


def advice_with(daily=None, indoor=None, summary="Air is poor today.", explanation="Fewer trips help."):
    return Advice(
        summary=summary,
        daily_routine=daily or [OK],
        indoor_air_hacks=indoor or [OK],
        sustainable_alternatives=[OK],
        impact_explanation=explanation,
    )


def test_clean_advice_passes():
    assessment, facts, _, _ = setup(180)
    assert check_advice(advice_with(), assessment, facts) == []


def test_outdoor_activity_is_rejected_when_rules_say_avoid():
    assessment, facts, _, _ = setup(180)
    jog = Action(title="Go for a morning jog", detail="Jog in the park.", why="Fresh air.")
    problems = check_advice(advice_with(daily=[jog]), assessment, facts)
    assert any("jog" in problem.lower() for problem in problems)


def test_indoor_alternative_to_outdoor_exercise_is_allowed():
    assessment, facts, _, _ = setup(180)
    yoga = Action(
        title="Move exercise indoors",
        detail="Do yoga instead of exercising outside.",
        why="Less exposure.",
    )
    assert check_advice(advice_with(daily=[yoga]), assessment, facts) == []


def test_strenuous_activity_is_rejected_when_rules_say_light_only():
    assessment, facts, _, _ = setup(120, Profile())
    assert assessment.constraints["outdoor_exercise"] == "light_only"
    run = Action(title="Go for a run", detail="Run for an hour.", why="Fitness.")
    gentle = Action(title="Take a gentle walk", detail="Keep it short.", why="Easy on lungs.")
    assert check_advice(advice_with(daily=[run]), assessment, facts)
    assert check_advice(advice_with(daily=[gentle]), assessment, facts) == []


def test_opening_windows_is_rejected_when_rules_say_keep_closed():
    assessment, facts, _, _ = setup(180)
    opened = Action(title="Fresh air", detail="Open windows for an hour.", why="Fresh air.")
    closed = Action(title="Keep windows closed", detail="Seal the gaps.", why="Blocks dust.")
    negated = Action(title="Windows", detail="Do not open windows today.", why="Blocks dust.")
    assert check_advice(advice_with(indoor=[opened]), assessment, facts)
    assert check_advice(advice_with(indoor=[closed]), assessment, facts) == []
    assert check_advice(advice_with(indoor=[negated]), assessment, facts) == []


def test_opening_windows_is_fine_on_clean_air():
    assessment, facts, _, _ = setup(40)
    opened = Action(title="Fresh air", detail="Open windows for an hour.", why="Fresh air.")
    assert check_advice(advice_with(indoor=[opened]), assessment, facts) == []


def test_contradicting_the_mask_rule_is_rejected():
    assessment, facts, _, _ = setup(180)
    bad = Action(title="Outdoors", detail="No need for a mask outdoors.", why="Air is fine.")
    assert check_advice(advice_with(daily=[bad]), assessment, facts)


def test_overclaims_are_rejected_but_ordinary_words_are_not():
    assessment, facts, _, _ = setup(180)
    bad = Action(title="Purifier", detail="This will cure asthma.", why="Clean air.")
    fine = Action(title="Secure the windows", detail="Seal gaps.", why="Blocks dust.")
    assert "overclaims safety or effect" in check_advice(advice_with(indoor=[bad]), assessment, facts)
    assert check_advice(advice_with(indoor=[fine]), assessment, facts) == []


def test_invented_numbers_are_rejected():
    assessment, facts, _, _ = setup(180)
    bad = advice_with(explanation="Switching saves about 45 kg CO2e a week.")
    problems = check_advice(bad, assessment, facts)
    assert any("45" in problem for problem in problems)


def test_numbers_from_the_facts_and_unit_names_are_allowed():
    assessment, facts, saving, _ = setup(180)
    kilos = saving["kg_co2e_saved_per_week"]
    text = f"Switching saves about {kilos} kg CO2e a week. Wear an N95 when PM2.5 is high for 5 days."
    assert check_advice(advice_with(explanation=text), assessment, facts) == []
    summary = "US AQI 180 is unhealthy."
    assert check_advice(advice_with(summary=summary), assessment, facts) == []


@pytest.mark.parametrize("aqi", [30, 80, 120, 180, 250, 400])
@pytest.mark.parametrize(
    "flags",
    [
        {},
        {"has_children": True, "commute_mode": "car"},
        {"has_elderly": True, "respiratory_condition": True, "commute_mode": "walk"},
        {"outdoor_worker": True, "commute_mode": "two_wheeler", "commute_km": 15},
        {"pregnant": True, "has_purifier": True, "commute_mode": "cycle"},
        {"has_children": True, "has_elderly": True, "outdoor_worker": True, "commute_mode": "public_transport"},
    ],
)
def test_our_own_fallback_passes_every_guardrail(aqi, flags):
    profile = Profile(**flags)
    assessment, facts, saving, _ = setup(aqi, profile)
    advice = fallback_advice("Mysuru", assessment, saving, profile.model_dump())
    assert check_advice(advice, assessment, facts) == []
