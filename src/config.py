"""Application settings loaded from environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for external services and logging."""

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_min_request_interval_seconds: float = Field(default=13.0, ge=0)
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
