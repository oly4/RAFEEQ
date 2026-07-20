from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_repo_root() -> Path:
    candidates = [Path.cwd(), *Path(__file__).resolve().parents]
    for candidate in candidates:
        if (candidate / "AGENTS.md").exists() or (candidate / ".env").exists():
            return candidate
    return Path.cwd()


REPO_ROOT = _find_repo_root()
ROOT_ENV = REPO_ROOT / ".env"
ROBOT_ENV = REPO_ROOT / ".env.robot"


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./data/rafeeq.db"
    redis_url: str = "redis://redis:6379/0"
    jwt_access_secret: SecretStr | None = None
    jwt_refresh_secret: SecretStr | None = None
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 30
    cors_allowed_origins: str = "http://localhost:8080,http://127.0.0.1:8080"
    cors_allowed_origin_regex: str = (
        r"https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|"
        r"172\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+)(:\d+)?"
    )
    log_level: str = "INFO"
    openai_api_key: SecretStr | None = None
    openai_text_model: str = "gpt-5.4-nano"
    openai_transcription_model: str = "gpt-4o-mini-transcribe"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "alloy"

    model_config = SettingsConfigDict(env_file=(ROOT_ENV, ROBOT_ENV), extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [value.strip() for value in self.cors_allowed_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
