import asyncio
from types import SimpleNamespace

from app.config import Settings
from app.schemas import Action, Advice, Profile
from app.services import llm
from tests.test_llm import make_inputs, sample_advice

OVERLOADED = RuntimeError("503 UNAVAILABLE")
GOOD = Action(title="Plan ahead", detail="Do indoor stretching.", why="Less exposure.")
BAD = Advice(
    summary="Air is poor.",
    daily_routine=[Action(title="Go for a morning jog", detail="Jog in the park.", why="Fresh air.")],
    indoor_air_hacks=[GOOD],
    sustainable_alternatives=[GOOD],
    impact_explanation="Fewer trips help.",
)


def settings(models=("m2", "m3"), timeout=1.0):
    return Settings(
        gemini_api_key="k",
        gemini_model="m1",
        llm_timeout_seconds=timeout,
        gemini_fallback_models=models,
    )


class Router:
    """Fake Gemini models endpoint where each model name has its own outcome."""

    def __init__(self, outcomes, delay=0.0):
        self.outcomes, self.delay, self.calls = outcomes, delay, []

    async def generate_content(self, **kwargs):
        model = kwargs["model"]
        self.calls.append(model)
        if self.delay:
            await asyncio.sleep(self.delay)
        outcome = self.outcomes[model]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(parsed=outcome, text="")


def client_for(router):
    return SimpleNamespace(aio=SimpleNamespace(models=router))


async def run(router, config=None, **kwargs):
    facts, assessment, saving = make_inputs(**kwargs)
    return await llm.get_advice_result(
        client_for(router), config or settings(), facts, assessment, saving
    )


async def test_next_model_answers_when_the_first_is_overloaded():
    router = Router({"m1": OVERLOADED, "m2": sample_advice(), "m3": sample_advice()})
    result = await run(router)
    assert (result.source, result.model) == ("gemini", "m2")
    assert router.calls == ["m1", "m2"]


async def test_failed_model_is_skipped_then_retried_after_the_cooldown(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(llm, "_now", lambda: clock["t"])
    router = Router({"m1": OVERLOADED, "m2": sample_advice(), "m3": sample_advice()})
    await run(router)
    await run(router)
    assert router.calls == ["m1", "m2", "m2"]
    clock["t"] += llm.COOLDOWN_SECONDS + 1
    await run(router)
    assert router.calls[-2:] == ["m1", "m2"]


async def test_everything_failing_gives_the_fallback():
    router = Router({"m1": OVERLOADED, "m2": OVERLOADED, "m3": OVERLOADED})
    result = await run(router)
    assert result.source == "fallback"
    assert result.model == ""
    assert result.advice.daily_routine


async def test_unsafe_answer_is_rejected_and_the_next_model_is_used():
    router = Router({"m1": BAD, "m2": sample_advice()})
    result = await run(router, settings(models=("m2",)), aqi=180, profile=Profile())
    assert (result.source, result.model) == ("gemini", "m2")


async def test_all_unsafe_answers_give_the_fallback_and_record_why():
    router = Router({"m1": BAD, "m2": BAD})
    result = await run(router, settings(models=("m2",)), aqi=180, profile=Profile())
    assert result.source == "fallback"
    assert "jog" in " ".join(result.problems).lower()


async def test_empty_sections_are_rejected():
    empty = sample_advice().model_copy(update={"indoor_air_hacks": []})
    router = Router({"m1": empty, "m2": sample_advice()})
    result = await run(router, settings(models=("m2",)))
    assert result.model == "m2"


async def test_slow_models_hit_the_overall_timeout():
    router = Router({"m1": sample_advice(), "m2": sample_advice(), "m3": sample_advice()}, delay=0.5)
    result = await run(router, settings(timeout=0.05))
    assert result.source == "fallback"


async def test_missing_client_gives_the_fallback_without_calls():
    facts, assessment, saving = make_inputs()
    result = await llm.get_advice_result(None, settings(), facts, assessment, saving)
    assert result.source == "fallback"


async def test_get_advice_keeps_its_two_value_shape():
    router = Router({"m1": sample_advice()})
    facts, assessment, saving = make_inputs()
    advice, source = await llm.get_advice(client_for(router), settings(), facts, assessment, saving)
    assert source == "gemini"
    assert advice.summary == "s"


def test_model_list_has_no_duplicates_or_blanks():
    config = Settings("k", "a", 1.0, gemini_fallback_models=("a", "b", ""))
    assert llm.models_to_try(config) == ["a", "b"]


class SlowFirst(Router):
    """The first model hangs. The others answer normally."""

    async def generate_content(self, **kwargs):
        if kwargs["model"] == "m1":
            await asyncio.sleep(0.5)
        return await super().generate_content(**kwargs)


async def test_a_slow_model_is_abandoned_and_the_next_one_answers():
    router = SlowFirst({"m1": sample_advice(), "m2": sample_advice()})
    config = Settings(
        gemini_api_key="k",
        gemini_model="m1",
        llm_timeout_seconds=2.0,
        gemini_fallback_models=("m2",),
        llm_model_timeout_seconds=0.05,
    )
    result = await run(router, config)
    assert (result.source, result.model) == ("gemini", "m2")
    await run(router, config)
    assert router.calls == ["m2", "m2"]
