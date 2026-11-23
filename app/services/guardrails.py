"""Checks that an AI answer respects the rule engine and does not invent numbers.

These are keyword heuristics, not proof of safety. They catch the most damaging
mistakes (advice that contradicts the rules, made-up statistics, overclaims) and
route the user to a safe answer instead.
"""
import json
import re
from typing import Any

from app.schemas import Action, Advice, Assessment

NUMBER = re.compile(r"\d+(?:\.\d+)?")
UNIT_TOKENS = re.compile(r"\b(?:KN95|N95|FFP[23])\b|PM\s?(?:2\.5|10)|CO2e?", re.IGNORECASE)
OVERCLAIM = re.compile(
    r"\b(?:cures?|cured|guarantee[sd]?|completely safe|totally safe|100% safe|"
    r"eliminates all|will prevent)\b",
    re.IGNORECASE,
)
FREE_INTEGER_LIMIT = 10
TOLERANCE = 0.051

OUTDOOR_NEGATIONS = (
    "instead", "avoid", "skip", "do not", "don't", "dont", "never", "not ", "no ",
    "indoor", "inside", "stay in", "cancel", "postpone", "without", "swap", "replace",
)
VENT_NEGATIONS = ("closed", "shut", "do not", "don't", "dont", "avoid", "never", "not ", "instead")

AVOID_TERMS = (
    "jog", "run outside", "running outside", "outdoor run", "go for a run",
    "morning walk", "evening walk", "walk outside", "walk in the park",
    "exercise outside", "exercising outside", "workout outside", "outdoor workout",
    "outdoor exercise", "outdoor sport", "play outside", "playing outside",
    "outdoor play", "play in the park", "cycling outdoors", "go cycling",
)
LIGHT_TERMS = (
    "jog", "run outside", "running outside", "outdoor run", "go for a run",
    "sprint", "vigorous", "intense", "heavy workout", "football", "cricket",
)
VENT_TERMS = (
    "open window", "open the window", "open your window", "open all window",
    "air out", "keep windows open", "keep the windows open",
)
MASK_TERMS = (
    "no need for a mask", "no mask needed", "mask is optional", "mask is not needed",
    "mask isn't needed", "don't need a mask", "do not need a mask",
)


def _action_text(action: Action) -> str:
    return f"{action.title} {action.detail}".lower()


def _flag(actions: list[Action], terms: tuple[str, ...], negations: tuple[str, ...]) -> list[str]:
    """Titles of actions that use a risky phrase without any softening phrase."""
    hits = []
    for action in actions:
        text = _action_text(action)
        if any(term in text for term in terms) and not any(n in text for n in negations):
            hits.append(action.title)
    return hits


def _invented_numbers(text: str, allowed: set[float]) -> set[str]:
    """Numbers that are neither small counts nor present in the verified facts."""
    found = set()
    for token in NUMBER.findall(UNIT_TOKENS.sub(" ", text)):
        value = float(token)
        if "." not in token and value <= FREE_INTEGER_LIMIT:
            continue
        if not any(abs(value - number) <= TOLERANCE for number in allowed):
            found.add(token)
    return found


def check_advice(advice: Advice, assessment: Assessment, facts: dict[str, Any]) -> list[str]:
    """Return a list of problems. An empty list means the answer passed every check."""
    rules = assessment.constraints
    everything = [*advice.daily_routine, *advice.indoor_air_hacks, *advice.sustainable_alternatives]
    problems: list[str] = []

    exercise = rules.get("outdoor_exercise")
    if exercise == "avoid":
        for title in _flag(advice.daily_routine, AVOID_TERMS, OUTDOOR_NEGATIONS):
            problems.append(f"suggests outdoor activity although the rules say avoid: {title}")
    elif exercise == "light_only":
        for title in _flag(advice.daily_routine, LIGHT_TERMS, OUTDOOR_NEGATIONS):
            problems.append(f"suggests strenuous activity although the rules say light only: {title}")

    if rules.get("ventilation") == "keep_closed":
        for title in _flag(advice.indoor_air_hacks, VENT_TERMS, VENT_NEGATIONS):
            problems.append(f"suggests opening windows although the rules say keep closed: {title}")

    if rules.get("mask") == "n95_outdoors":
        for title in _flag(everything, MASK_TERMS, ()):
            problems.append(f"says a mask is not needed although the rules require one: {title}")

    texts = [advice.summary, advice.impact_explanation]
    texts += [f"{a.title} {a.detail} {a.why}" for a in everything]
    if any(OVERCLAIM.search(text) for text in texts):
        problems.append("overclaims safety or effect")

    allowed = {float(x) for x in NUMBER.findall(json.dumps(facts, ensure_ascii=False))}
    invented = _invented_numbers(f"{advice.summary} {advice.impact_explanation}", allowed)
    if invented:
        problems.append("uses numbers that are not in the facts: " + ", ".join(sorted(invented)))
    return problems
