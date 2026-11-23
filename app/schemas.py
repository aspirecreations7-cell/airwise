"""Data models shared by the API, the rule engine and the LLM layer."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CommuteMode = Literal[
    "walk", "cycle", "two_wheeler", "car", "public_transport", "work_from_home"
]
Language = Literal["en", "kn", "hi"]


class Profile(BaseModel):
    """Household context supplied by the user. Never stored."""

    model_config = ConfigDict(extra="forbid")

    has_children: bool = False
    has_elderly: bool = False
    respiratory_condition: bool = False
    pregnant: bool = False
    outdoor_worker: bool = False
    has_purifier: bool = False
    commute_mode: CommuteMode = "public_transport"
    commute_km: float = Field(default=10, ge=0, le=100)


class Assessment(BaseModel):
    """Output of the rule engine, passed to the LLM as trusted facts."""

    aqi: int
    category: str
    personal_tier: str
    sensitive_group: bool
    constraints: dict[str, str]


class Location(BaseModel):
    """A resolved place from the geocoding service."""

    name: str
    latitude: float
    longitude: float
    country: str = ""
    region: str = ""


class AirReading(BaseModel):
    """A live air quality reading for one location."""

    us_aqi: int
    pm2_5: float | None = None
    pm10: float | None = None
    nitrogen_dioxide: float | None = None
    ozone: float | None = None
    observed_at: str = ""
    source: str = ""
    station: str = ""
    distance_km: float | None = None
    aqi_method: str = ""


class Action(BaseModel):
    """One piece of advice with the reason behind it."""

    title: str
    detail: str
    why: str


class Advice(BaseModel):
    """The structured answer Gemini must return."""

    summary: str
    daily_routine: list[Action]
    indoor_air_hacks: list[Action]
    sustainable_alternatives: list[Action]
    impact_explanation: str


class PeriodPlan(BaseModel):
    """Forecast summary for one part of the day."""

    period: str
    label: str
    avg_aqi: int
    best_hour: str
    best_hour_aqi: int
    tier: str
    outdoor: str
    cleanest: bool = False


class DayPlan(BaseModel):
    """Today's remaining day split into morning, afternoon and evening."""

    date: str
    periods: list[PeriodPlan]
    source: str
    note: str
