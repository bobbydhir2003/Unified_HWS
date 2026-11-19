from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Undeclared"
    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://undeclared:undeclared@localhost:5432/undeclared"
    redis_url: str = "redis://localhost:6379/0"
    # When true, Celery tasks run inline (no worker/redis required). Useful for tests and minimal local dev.
    celery_eager: bool = False

    secret_key: str = "dev-insecure-change-me-0123456789abcdef"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    mfa_token_minutes: int = 5
    # Roles that must enroll in MFA before they can use the app (enforced when enforce_mfa=True).
    enforce_mfa: bool = False
    mfa_required_roles: list[str] = ["super_admin", "clinic_admin"]
    max_failed_logins: int = 5
    lockout_minutes: int = 15

    cors_origins: list[str] = ["http://localhost:5173"]
    frontend_url: str = "http://localhost:5173"
    cookie_secure: bool = False

    # Object storage (S3-compatible). "local" stores under storage_local_path.
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_path: str = "./var/storage"
    s3_bucket: str = "undeclared-documents"
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    max_upload_mb: int = 25

    # AI. "simulated" never sends data off-box. "anthropic" requires a BAA before real PHI is used.
    ai_provider: Literal["simulated", "anthropic"] = "simulated"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    ai_phi_allowed: bool = False  # must be explicitly enabled to send PHI to an external provider

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
