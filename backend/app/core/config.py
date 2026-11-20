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
    ai_provider: Literal["simulated", "anthropic", "openai"] = "simulated"
    # OpenAI (backend secret only). Models are configuration, not code: set AI_TEXT_MODEL etc. to models your account offers.
    openai_api_key: str | None = None
    ai_text_model: str = ""
    ai_vision_model: str = ""  # defaults to AI_TEXT_MODEL when empty
    ai_transcription_model: str = ""
    ai_timeout_seconds: float = 60.0
    ai_max_retries: int = 2
    ai_prices: dict[str, list[float]] = {}  # {"model-prefix": [usd_per_m_input, usd_per_m_output]} for cost tracking
    # Synthetic-data organizations (settings.synthetic_data) may use external AI in development: their data is not PHI.
    ai_allow_synthetic_external: bool = True
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"
    ai_phi_allowed: bool = False
    scribe_retain_audio: bool = False

    # External integration adapters (see app/integrations/adapters.py). Only simulated ones ship today.
    order_transmitter_adapter: str = "simulated"
    clearinghouse_adapter: str = "simulated"
    message_gateway_adapter: str = "outbox"

    # Abuse protection (per client IP, per process). Put a WAF/edge limiter in front in production.
    rate_limit_enabled: bool = True
    # One-click role sign-in for a synthetic-data demonstration deployment (app/core/demo.py). Refused in production.
    demo_mode: bool = False
    rls_enabled: bool = True
    credentials_encryption_key: str | None = None  # Fernet key for stored secrets (AI keys); required in production
    eligibility_adapter: str = "simulated"
    engine_inprocess_scheduler: bool = False  # dev without Celery beat: run dispatcher/monitors/escalations in the API process  # PostgreSQL row-level security for tenant requests (app.core.rls)
    rate_limit_auth_per_minute: int = 20  # delete raw audio once transcribed (default: minimize retained PHI)  # must be explicitly enabled to send PHI to an external provider

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
