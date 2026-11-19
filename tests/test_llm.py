import asyncio
from types import SimpleNamespace

from app.config import Settings
from app.schemas import Action, Advice, AirReading, Location, Profile
from app.services import engine, impact
from app.services.llm import build_facts, get_advice

SETTINGS = Settings(gemini_api_key="test", gemini_model="test-model", llm_timeout_seconds=0.05)
PLACE = Location(name="Mysuru", latitude=12.3, longitude=76.6, region="Karnataka")


def sample_advice() -> Advice:
    action = Action(title="t", detail="d", why="w")
    return Advice(
        summary="s",
        daily_routine=[action],
        indoor_air_hacks=[action],
        sustainable_alternatives=[action],
        impact_explanation="e",
    )


class FakeModels:
    def __init__(self, result=None, error=None, delay=0.0):
        self.result, self.error, self.delay, self.calls = result, error, delay, []

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.result


def fake_client(models):
    return SimpleNamespace(aio=SimpleNamespace(models=models))


def make_inputs(aqi=99, profile=None, language="en"):
    profile = profile or Profile(has_children=True, commute_mode="car")
    reading = AirReading(us_aqi=aqi, pm2_5=37.8)
    assessment = engine.assess(aqi, profile)
    saving = impact.commute_saving(profile.commute_mode, profile.commute_km)
    facts = build_facts(PLACE, reading, assessment, profile, saving, language)
    return facts, assessment, saving


async def test_successful_call_returns_gemini_advice():
    facts, assessment, saving = make_inputs()
    models = FakeModels(result=SimpleNamespace(parsed=sample_advice(), text=""))
    advice, source = await get_advice(fake_client(models), SETTINGS, facts, assessment, saving)
    assert source == "gemini"
    assert advice.summary == "s"
    assert models.calls[0]["model"] == "test-model"
    assert "Mysuru" in models.calls[0]["contents"]


async def test_text_is_parsed_when_parsed_is_missing():
    facts, assessment, saving = make_inputs()
    result = SimpleNamespace(parsed=None, text=sample_advice().model_dump_json())
    models = FakeModels(result=result)
    advice, source = await get_advice(fake_client(models), SETTINGS, facts, assessment, saving)
    assert source == "gemini"
    assert advice.summary == "s"


async def test_api_error_uses_fallback():
    facts, assessment, saving = make_inputs()
    models = FakeModels(error=RuntimeError("boom"))
    advice, source = await get_advice(fake_client(models), SETTINGS, facts, assessment, saving)
    assert source == "fallback"
    assert advice.daily_routine


async def test_timeout_uses_fallback():
    facts, assessment, saving = make_inputs()
    models = FakeModels(result=SimpleNamespace(parsed=sample_advice(), text=""), delay=0.5)
    _, source = await get_advice(fake_client(models), SETTINGS, facts, assessment, saving)
    assert source == "fallback"


async def test_incomplete_answer_uses_fallback():
    facts, assessment, saving = make_inputs()
    broken = sample_advice().model_copy(update={"daily_routine": []})
    models = FakeModels(result=SimpleNamespace(parsed=broken, text=""))
    _, source = await get_advice(fake_client(models), SETTINGS, facts, assessment, saving)
    assert source == "fallback"


async def test_missing_client_uses_fallback():
    facts, assessment, saving = make_inputs()
    advice, source = await get_advice(None, SETTINGS, facts, assessment, saving)
    assert source == "fallback"
    assert "Mysuru" in advice.summary


async def test_fallback_moves_exercise_indoors_when_air_is_unhealthy():
    facts, assessment, saving = make_inputs(aqi=180, profile=Profile())
    advice, _ = await get_advice(None, SETTINGS, facts, assessment, saving)
    assert "indoors" in advice.daily_routine[0].title.lower()


async def test_fallback_quotes_the_computed_saving():
    facts, assessment, saving = make_inputs()
    advice, _ = await get_advice(None, SETTINGS, facts, assessment, saving)
    assert str(saving["kg_co2e_saved_per_week"]) in advice.impact_explanation


def test_facts_carry_language_constraints_and_no_secrets():
    facts, _, _ = make_inputs(language="kn")
    assert facts["language"] == "Kannada"
    assert facts["constraints"]["outdoor_exercise"] == "light_only"
    assert "api_key" not in str(facts).lower()
