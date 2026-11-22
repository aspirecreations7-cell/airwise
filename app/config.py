"""Settings loaded from environment variables, with a tiny .env reader."""
import os
from dataclasses import dataclass
from pathlib import Path


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


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    llm_timeout_seconds: float
    openaq_api_key: str = ""


def get_settings() -> Settings:
    """Read settings from .env and the environment."""
    load_env_file()
    return Settings(
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
        llm_timeout_seconds=float(os.environ.get("LLM_TIMEOUT_SECONDS", "20")),
        openaq_api_key=os.environ.get("OPENAQ_API_KEY", ""),
    )
