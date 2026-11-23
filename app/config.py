"""Settings loaded from environment variables, with a tiny .env reader."""
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "gemini-3.1-flash-lite"
DEFAULT_FALLBACK_MODELS = "gemini-3.5-flash-lite,gemini-3.5-flash"
DEFAULT_TOTAL_TIMEOUT = "30"
DEFAULT_MODEL_TIMEOUT = "12"


def load_env_file(path: str = ".env") -> None:
    """Load KEY=VALUE lines into the environment without overriding existing values."""
    file = Path(path)
    if not file.is_file():
        return
    for raw in file.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _split(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    llm_timeout_seconds: float
    openaq_api_key: str = ""
    gemini_fallback_models: tuple[str, ...] = ()
    llm_model_timeout_seconds: float = 12.0


def get_settings() -> Settings:
    """Read settings from .env and the environment."""
    load_env_file()
    return Settings(
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        gemini_model=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL),
        llm_timeout_seconds=float(os.environ.get("LLM_TIMEOUT_SECONDS", DEFAULT_TOTAL_TIMEOUT)),
        openaq_api_key=os.environ.get("OPENAQ_API_KEY", ""),
        gemini_fallback_models=_split(
            os.environ.get("GEMINI_FALLBACK_MODELS", DEFAULT_FALLBACK_MODELS)
        ),
        llm_model_timeout_seconds=float(
            os.environ.get("LLM_MODEL_TIMEOUT_SECONDS", DEFAULT_MODEL_TIMEOUT)
        ),
    )
