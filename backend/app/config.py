"""Application settings, loaded from environment variables and backend/.env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]

_PLACEHOLDER_SECRETS = {"", "change-me", "change-me-to-a-long-random-string"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application
    app_name: str = "KAAMSETU"
    app_version: str = "0.1.0"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://localhost:8081"

    # Gnani (used from Phase 2; declared here so settings are validated in one place)
    gnani_api_key: SecretStr = SecretStr("")
    gnani_api_base_url: str = "https://api.vachana.ai"
    gnani_prisma_model: str = "prisma-v3.0"
    gnani_prisma_default_language: str = "indic-auto"
    gnani_timbre_model: str = "timbre-v2.5"
    gnani_timbre_voice_hi: str = "Nalini"
    gnani_timbre_voice_en: str = "Kaveri"
    gnani_timbre_voice_te: str = "Suhana"
    gnani_timbre_voice_hinglish: str = "Poorvi"
    gnani_timeout_seconds: float = 30.0
    gnani_max_retries: int = 3
    # Docs give "Only 1 active request is allowed at a time" as an example limit. Shared by Prisma and Timbre.
    gnani_max_concurrency: int = 1
    # Hinglish handling (settled empirically in Phase 2; see docs/GNANI_INTEGRATION.md "Measured").
    # en-IN returns Latin-script Hinglish ("motor ka pressure abnormal hai"), matching how users type it.
    gnani_prisma_hinglish_language: str = "en-IN"
    gnani_prisma_hinglish_format: str | None = None
    gnani_timbre_hinglish_language: str = "hi-en"
    gnani_timbre_container: Literal["wav", "mp3", "ogg"] = "mp3"
    gnani_timbre_sample_rate: int = 24000
    gnani_timbre_mp3_bitrate: str = "64k"

    # Database
    database_url: str = "postgresql+pg8000://kaamsetu:kaamsetu@localhost:5432/kaamsetu"
    database_url_test: str | None = None

    # Auth
    jwt_secret_key: SecretStr = SecretStr("change-me")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Limits and policy
    max_audio_upload_mb: int = 10
    max_audio_seconds: int = 30
    audio_retention: str = "none"
    allow_self_approval: bool = False
    rate_limit_enabled: bool = True
    rate_limit_login_per_minute: int = 10
    rate_limit_voice_per_minute: int = 30

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        if self.app_env == "production":
            secret = self.jwt_secret_key.get_secret_value()
            if secret in _PLACEHOLDER_SECRETS or len(secret) < 32:
                raise ValueError("JWT_SECRET_KEY must be a random value of at least 32 characters in production")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def test_database_url(self) -> str:
        """Database used by pytest. Defaults to the main database name with a `_test` suffix."""
        if self.database_url_test:
            return self.database_url_test
        url = make_url(self.database_url)
        return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)

    @property
    def max_request_bytes(self) -> int:
        # Audio limit plus 1 MB headroom for multipart overhead and form fields.
        return (self.max_audio_upload_mb + 1) * 1024 * 1024

    @field_validator("gnani_prisma_hinglish_format", mode="before")
    @classmethod
    def _empty_format_is_none(cls, value: object) -> object:
        return None if value in ("", None) else value

    @property
    def gnani_configured(self) -> bool:
        return bool(self.gnani_api_key.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
