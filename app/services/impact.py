"""Deterministic impact estimates. The LLM may only explain these numbers."""
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

FACTORS_PATH = Path(__file__).resolve().parent.parent / "data" / "factors.json"
GREENER_ALTERNATIVE = {"car": "public_transport"}
COMMUTE_DAYS_PER_WEEK = 5


@lru_cache
def load_factors() -> dict[str, Any]:
    """Load the emission factors file once."""
    return json.loads(FACTORS_PATH.read_text(encoding="utf-8"))


def commute_saving(mode: str, commute_km: float) -> dict[str, Any]:
    """Estimate weekly CO2e saved by switching to a greener commute mode.

    Returns an empty dict when there is nothing meaningful to claim.
    """
    alternative = GREENER_ALTERNATIVE.get(mode)
    if alternative is None or commute_km <= 0:
        return {}
    per_km = load_factors()["commute_kg_co2e_per_km"]
    daily = 2 * commute_km * (per_km[mode] - per_km[alternative])
    weekly = round(daily * COMMUTE_DAYS_PER_WEEK, 1)
    if weekly <= 0:
        return {}
    return {
        "commute_switch_from": mode,
        "commute_switch_to": alternative,
        "kg_co2e_saved_per_week": weekly,
        "assumption": (
            f"{commute_km:g} km each way, {COMMUTE_DAYS_PER_WEEK} days a week, "
            "estimated emission factors"
        ),
    }
