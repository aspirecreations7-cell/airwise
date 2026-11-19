"""Deterministic rule engine: AQI plus household context -> tier and constraints."""
from app.schemas import Assessment, Profile

# US AQI breakpoints as (inclusive upper bound, category).
TIERS = [
    (50, "good"),
    (100, "moderate"),
    (150, "unhealthy_for_sensitive_groups"),
    (200, "unhealthy"),
    (300, "very_unhealthy"),
    (500, "hazardous"),
]
ORDER = [name for _, name in TIERS]
SENSITIVE_INDEX = ORDER.index("unhealthy_for_sensitive_groups")

BASE_CONSTRAINTS = {
    "good": {"outdoor_exercise": "normal", "mask": "not_needed", "ventilation": "open_windows"},
    "moderate": {"outdoor_exercise": "normal", "mask": "not_needed", "ventilation": "open_windows"},
    "unhealthy_for_sensitive_groups": {"outdoor_exercise": "light_only", "mask": "optional", "ventilation": "short_bursts"},
    "unhealthy": {"outdoor_exercise": "avoid", "mask": "n95_outdoors", "ventilation": "keep_closed"},
    "very_unhealthy": {"outdoor_exercise": "avoid", "mask": "n95_outdoors", "ventilation": "keep_closed"},
    "hazardous": {"outdoor_exercise": "avoid", "mask": "n95_outdoors", "ventilation": "keep_closed"},
}
EXPOSED_COMMUTES = ("walk", "cycle", "two_wheeler")


def aqi_category(aqi: int) -> str:
    """Map a US AQI value to its standard category."""
    if aqi < 0:
        raise ValueError("AQI cannot be negative")
    for upper, name in TIERS:
        if aqi <= upper:
            return name
    return ORDER[-1]


def is_sensitive(profile: Profile) -> bool:
    """True if anyone in the household belongs to a sensitive group."""
    return (
        profile.has_children
        or profile.has_elderly
        or profile.respiratory_condition
        or profile.pregnant
    )


def personal_tier(aqi: int, profile: Profile) -> str:
    """Escalate the public category for sensitive groups and outdoor workers.

    Good air is never escalated, so clean days are not over-restricted.
    """
    index = ORDER.index(aqi_category(aqi))
    if index == 0:
        return ORDER[0]
    if is_sensitive(profile):
        index += 1
    if profile.outdoor_worker:
        index += 1
    return ORDER[min(index, len(ORDER) - 1)]


def build_constraints(tier: str, profile: Profile) -> dict[str, str]:
    """Hard rules the LLM must respect when writing advice."""
    rules = dict(BASE_CONSTRAINTS[tier])
    index = ORDER.index(tier)
    if index >= SENSITIVE_INDEX:
        rules["purifier"] = "run_continuously" if profile.has_purifier else "recommended"
    else:
        rules["purifier"] = "optional"
    exposed = profile.commute_mode in EXPOSED_COMMUTES and index >= SENSITIVE_INDEX
    rules["commute"] = "reduce_exposure" if exposed else "no_change"
    return rules


def assess(aqi: int, profile: Profile) -> Assessment:
    """Run the full assessment for one AQI reading and one household."""
    tier = personal_tier(aqi, profile)
    return Assessment(
        aqi=aqi,
        category=aqi_category(aqi),
        personal_tier=tier,
        sensitive_group=is_sensitive(profile),
        constraints=build_constraints(tier, profile),
    )
