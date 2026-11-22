"""FastAPI application: one endpoint that turns a place and a household into advice."""
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from google import genai
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.config import Settings, get_settings
from app.schemas import Advice, AirReading, Assessment, Language, Location, Profile
from app.services import air, aqi, engine, impact
from app.services.aqi import AirDataError
from app.services.limits import DailyBudget, RateLimiter
from app.services.llm import build_facts, get_advice

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "General guidance, not medical advice. If anyone has symptoms such as trouble "
    "breathing or chest pain, contact a doctor."
)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(self)",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'",
}
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_UNSET: Any = object()


class AdviceRequest(BaseModel):
    """Either a city name or coordinates inside India, plus the household profile."""

    model_config = ConfigDict(extra="forbid")

    city: str | None = Field(default=None, min_length=2, max_length=80, pattern=r"^[\w .,'()-]+$")
    latitude: float | None = Field(default=None, ge=6.0, le=37.5)
    longitude: float | None = Field(default=None, ge=68.0, le=97.5)
    profile: Profile = Field(default_factory=Profile)
    language: Language = "en"

    @model_validator(mode="after")
    def need_a_place(self) -> Self:
        has_city = bool(self.city and self.city.strip())
        has_point = self.latitude is not None and self.longitude is not None
        if not has_city and not has_point:
            raise PydanticCustomError(
                "missing_place", "Provide a city, or both latitude and longitude"
            )
        return self


class AdviceResponse(BaseModel):
    location: Location
    reading: AirReading
    assessment: Assessment
    advice: Advice
    advice_source: str
    disclaimer: str = DISCLAIMER


def client_id(request: Request) -> str:
    """Best-effort client identity for rate limiting (daily budget is the hard stop)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def resolve_location(http: httpx.AsyncClient, body: AdviceRequest) -> Location:
    """Coordinates win over a city name, so auto-detect needs no geocoding call."""
    if body.latitude is not None and body.longitude is not None:
        return Location(
            name="Your location",
            latitude=body.latitude,
            longitude=body.longitude,
            country="India",
        )
    return await aqi.geocode(http, body.city or "")


def create_app(
    settings: Settings | None = None,
    llm_client: Any = _UNSET,
    rate_limit: int = 20,
    daily_llm_limit: int = 300,
) -> FastAPI:
    """Build the application. Dependencies are injectable so tests never hit the network."""
    settings = settings or get_settings()
    if llm_client is _UNSET:
        llm_client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None
    limiter = RateLimiter(rate_limit, 60.0)
    budget = DailyBudget(daily_llm_limit)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient(timeout=aqi.TIMEOUT) as http:
            application.state.http = http
            yield

    app = FastAPI(
        title="AirWise",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/advice", response_model=AdviceResponse)
    async def create_advice(body: AdviceRequest, request: Request) -> AdviceResponse:
        if not limiter.allow(client_id(request)):
            raise HTTPException(
                status_code=429, detail="Too many requests. Please wait a minute and try again."
            )
        http: httpx.AsyncClient = request.app.state.http
        try:
            location = await resolve_location(http, body)
            reading = await air.get_reading(http, location, settings.openaq_api_key)
        except AirDataError as exc:
            # AirDataError messages are written to be safe to show to users.
            status = 404 if str(exc).startswith("Could not find") else 503
            raise HTTPException(status_code=status, detail=str(exc)) from exc

        assessment = engine.assess(reading.us_aqi, body.profile)
        saving = impact.commute_saving(body.profile.commute_mode, body.profile.commute_km)
        facts = build_facts(location, reading, assessment, body.profile, saving, body.language)
        facts["data_source"] = {
            "name": reading.source,
            "station": reading.station,
            "observed_at": reading.observed_at,
            "aqi_method": reading.aqi_method,
        }
        today = datetime.now(UTC).date().isoformat()
        client = llm_client if llm_client is not None and budget.take(today) else None
        advice, source = await get_advice(client, settings, facts, assessment, saving)
        return AdviceResponse(
            location=location,
            reading=reading,
            assessment=assessment,
            advice=advice,
            advice_source=source,
        )

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()
