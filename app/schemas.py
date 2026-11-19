"""Data models shared by the API, the rule engine and the LLM layer."""
from typing import Literal

from pydantic import BaseModel, ConfigDict

CommuteMode = Literal[
    "walk", "cycle", "two_wheeler", "car", "public_transport", "work_from_home"
]


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
