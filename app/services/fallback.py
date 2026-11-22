"""Deterministic, profile-aware advice used when Gemini is unavailable."""
from typing import Any

from app.schemas import Action, Advice, Assessment

MAX_ROUTINE_ITEMS = 5

_EXERCISE = {
    "normal": Action(
        title="Exercise as usual",
        detail="Outdoor activity is fine today. Pick parks or quiet streets away from heavy traffic.",
        why="Air is in a range where normal activity adds little risk.",
    ),
    "light_only": Action(
        title="Keep outdoor exercise light",
        detail="Choose a gentle, shorter walk instead of running or sport.",
        why="Harder breathing pulls more polluted air deep into the lungs.",
    ),
    "avoid": Action(
        title="Move exercise indoors today",
        detail="Do yoga, stretching or a home workout instead of exercising outside.",
        why="Air is unhealthy for your household today, and avoiding hard outdoor effort cuts exposure the most.",
    ),
}
_MASK = {
    "optional": Action(
        title="Keep an N95 mask handy",
        detail="Wear a well-fitted N95 on busy roads or if the air irritates your throat.",
        why="N95 masks filter fine particles that ordinary cloth masks let through.",
    ),
    "n95_outdoors": Action(
        title="Wear a fitted N95 outdoors",
        detail="Use an N95 whenever you go out, and make sure it seals around the nose and chin.",
        why="Fine particles are high enough to matter even on short trips.",
    ),
}
_VENTILATION = {
    "open_windows": Action(
        title="Air out your home",
        detail="Open windows for a while, preferably when traffic is lightest.",
        why="Fresh air dilutes indoor pollutants when the outside air is clean.",
    ),
    "short_bursts": Action(
        title="Ventilate in short bursts",
        detail="Open windows for a few minutes at quiet times, then close them again.",
        why="Short airing refreshes the room without letting in much polluted air.",
    ),
    "keep_closed": Action(
        title="Keep windows closed",
        detail="Keep windows and doors shut while outdoor air is poor, and seal obvious gaps.",
        why="This keeps outdoor particles from flowing into your home.",
    ),
}
_PURIFIER = {
    "optional": Action(
        title="Purifier is optional today",
        detail="If you own one, run it in the room where you spend the most time.",
        why="Air is fairly clean, so a purifier adds only a small benefit.",
    ),
    "recommended": Action(
        title="Use a purifier in one key room",
        detail="If you can, run a HEPA purifier in the bedroom or the main living room.",
        why="A purifier lowers indoor particle levels when outdoor air is poor.",
    ),
    "run_continuously": Action(
        title="Run your purifier continuously",
        detail="Keep the purifier on in the room where your family spends the most time.",
        why="It keeps indoor particle levels low while outdoor air is poor.",
    ),
}
_INDOOR_SOURCES = Action(
    title="Keep indoor sources low",
    detail="Skip incense and mosquito coils, never burn waste, and damp-mop instead of sweeping.",
    why="These add particles to the air you breathe indoors.",
)
_PLANTS = Action(
    title="Treat plants as a bonus",
    detail="Indoor plants add greenery but do little to clean the air in a home. Rely on ventilation timing and a purifier first.",
    why="Home-sized rooms need far more cleaning power than a few plants provide.",
)
_COMMUTE = {
    "two_wheeler": Action(
        title="Fit an N95 under your helmet",
        detail="Pick an N95 that seals under your helmet, and check the fit before you ride.",
        why="Riders breathe traffic exhaust directly.",
    ),
    "walk": Action(
        title="Walk on quieter back streets",
        detail="Avoid main roads and busy junctions where you can, even if the route is a little longer.",
        why="Air is usually cleaner away from heavy traffic.",
    ),
    "cycle": Action(
        title="Cycle on quieter back streets",
        detail="Avoid main roads, wear a fitted mask and ease off the effort.",
        why="Hard breathing next to traffic raises how much you inhale.",
    ),
    "car": Action(
        title="Set the car to recirculate",
        detail="Keep windows up and use recirculated air in heavy traffic.",
        why="This reduces how much exhaust is drawn into the cabin.",
    ),
    "public_transport": Action(
        title="Wait away from traffic",
        detail="Stand back from the road at stops and wear a mask in crowded places.",
        why="Roadside air at stops is often the most polluted part of the trip.",
    ),
    "work_from_home": Action(
        title="Use today to skip the commute",
        detail="Stay in, and keep errands short and combined.",
        why="No commute means no roadside exposure.",
    ),
}
_SHARED_TRIPS = Action(
    title="Combine and share trips",
    detail="Group errands into one trip and share rides when you can.",
    why="Fewer vehicle trips mean less traffic pollution on your street.",
)
_SHORT_TRIPS = Action(
    title="Walk or use public transport for short trips",
    detail="On days when the air is better, leave the vehicle at home for nearby errands.",
    why="This cuts both your exposure in traffic and your emissions.",
)
_SWITCH_CAR = Action(
    title="Try public transport or a carpool",
    detail="Even two or three days a week helps. The estimate below shows the saving.",
    why="Fewer cars on the road means less traffic pollution and fewer emissions.",
)


def _household_actions(household: dict[str, Any], poor: bool) -> list[Action]:
    """Advice that depends on who lives in the household."""
    actions: list[Action] = []
    if household.get("has_children"):
        if poor:
            actions.append(
                Action(
                    title="Keep children's outdoor play indoors today",
                    detail="Swap park time for indoor games, and ask the school to keep sports light and short.",
                    why="Children breathe more air for their body size, so polluted air affects them sooner.",
                )
            )
        else:
            actions.append(
                Action(
                    title="Outdoor play is fine today",
                    detail="Choose parks and playgrounds away from busy roads.",
                    why="Air is in a range where normal play adds little risk.",
                )
            )
    if not poor:
        return actions
    if household.get("has_elderly"):
        actions.append(
            Action(
                title="Keep walks short for older family members",
                detail="Choose light indoor movement, and go out only when needed, wearing an N95.",
                why="Older adults are more sensitive to fine particles.",
            )
        )
    if household.get("respiratory_condition"):
        actions.append(
            Action(
                title="Keep prescribed medicines within reach",
                detail="Follow your doctor's plan, and call your doctor if breathing gets worse.",
                why="Polluted air can aggravate breathing conditions.",
            )
        )
    if household.get("pregnant"):
        actions.append(
            Action(
                title="Limit time near heavy traffic",
                detail="Keep outings short and away from busy roads, and speak to your doctor if you feel unwell.",
                why="Reducing exposure is a sensible precaution during pregnancy.",
            )
        )
    if household.get("outdoor_worker"):
        actions.append(
            Action(
                title="Take clean-air breaks during outdoor work",
                detail="Wear an N95 for outdoor tasks, and rest indoors between jobs when you can.",
                why="Long hours outside multiply your exposure through the day.",
            )
        )
    return actions


def _explanation(impact: dict[str, Any], poor: bool) -> str:
    """Explain impact using only numbers computed in code."""
    if impact:
        return (
            f"Switching your commute from {impact['commute_switch_from'].replace('_', ' ')} "
            f"to {impact['commute_switch_to'].replace('_', ' ')} would save about "
            f"{impact['kg_co2e_saved_per_week']} kg CO2e a week "
            f"({impact['assumption']}). These are estimates."
        )
    if poor:
        return (
            "Wearing a fitted mask outdoors, keeping windows closed and running a purifier "
            "each lower how much fine dust you breathe in today. Fewer vehicle trips also "
            "cut street pollution. No exact figures are claimed here."
        )
    return (
        "Fewer vehicle trips, less idling and no open burning all reduce the pollution on "
        "your street. Exact savings depend on your routine."
    )


def fallback_advice(
    place: str,
    assessment: Assessment,
    impact: dict[str, Any],
    household: dict[str, Any] | None = None,
) -> Advice:
    """Rule-based advice that adapts to the household and commute."""
    household = household or {}
    rules = assessment.constraints
    poor = rules["outdoor_exercise"] != "normal"
    mode = household.get("commute_mode")

    routine = [_EXERCISE[rules["outdoor_exercise"]]]
    if rules["mask"] in _MASK:
        routine.append(_MASK[rules["mask"]])
    routine += _household_actions(household, poor)
    if poor and mode in _COMMUTE:
        routine.append(_COMMUTE[mode])

    indoor = [
        _VENTILATION[rules["ventilation"]],
        _PURIFIER[rules["purifier"]],
        _INDOOR_SOURCES,
        _PLANTS,
    ]
    alternatives = [_SHARED_TRIPS, _SHORT_TRIPS]
    if mode == "car":
        alternatives.insert(0, _SWITCH_CAR)

    summary = (
        f"Air in {place} is {assessment.category.replace('_', ' ')} "
        f"(US AQI {assessment.aqi}). For your household it counts as "
        f"{assessment.personal_tier.replace('_', ' ')}."
    )
    return Advice(
        summary=summary,
        daily_routine=routine[:MAX_ROUTINE_ITEMS],
        indoor_air_hacks=indoor,
        sustainable_alternatives=alternatives,
        impact_explanation=_explanation(impact, poor),
    )
