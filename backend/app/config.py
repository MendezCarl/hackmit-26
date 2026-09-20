"""Application settings for the lecture recovery backend."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field

DEVELOPMENT_ENV = "development"
TEST_ENV = "test"
DEMO_ENV = "demo"
PRODUCTION_ENV = "production"
KNOWN_ENVIRONMENTS = (DEVELOPMENT_ENV, TEST_ENV, DEMO_ENV, PRODUCTION_ENV)

MOCK_PROVIDER_MODE = "mock"
LIVE_PROVIDER_MODE = "live"
KNOWN_PROVIDER_MODES = (MOCK_PROVIDER_MODE, LIVE_PROVIDER_MODE)

DEFAULT_DEMO_SECRET = "dev-only-secret-change-me-before-production"
DEMO_HEAD_AWAY_WINDOW_MS = 5_000  # Demo clips are a few seconds long; production keeps 30 s.


class Settings(BaseModel):
    """Runtime configuration resolved from environment variables.

    Environment variables (all optional outside production):

    - ``APP_ENV``: ``development``, ``test``, ``demo``, or ``production``.
    - ``PROVIDER_MODE``: ``mock`` (deterministic synthetic cards) or ``live``.
    - ``APP_SECRET``: signing secret for JWT access tokens.
    - Threshold and limit knobs documented per field below.
    """

    app_env: str = Field(default=DEVELOPMENT_ENV, description="Deployment environment.")
    provider_mode: str = Field(
        default=MOCK_PROVIDER_MODE,
        description="Provider execution mode: mock produces synthetic cards.",
    )
    app_secret: str = Field(
        default=DEFAULT_DEMO_SECRET,
        description="Signing secret for JWT access tokens.",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm.")
    jwt_ttl_seconds: int = Field(
        default=3600, description="Access-token lifetime in seconds.", ge=1
    )
    minimum_group_size: int = Field(
        default=5,
        description=(
            "Minimum number of unique participating users before a professor "
            "summary is released instead of suppressed."
        ),
        ge=1,
    )
    aggregation_window_ms: int = Field(
        default=300_000,
        description="Fixed professor-summary bucket width in milliseconds.",
        ge=1,
    )
    context_padding_ms: int = Field(
        default=30_000,
        description="Default padding added around a requested recovery interval.",
        ge=0,
    )
    max_context_padding_ms: int = Field(
        default=120_000,
        description="Upper bound on recovery context padding after clamping.",
        ge=0,
    )
    min_missed_window_ms: int = Field(
        default=30_000,
        description=(
            "Configurable temporal rule: minimum signal-event duration before "
            "the event is considered recovery eligible."
        ),
        ge=0,
    )
    min_head_away_window_ms: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Optional shorter minimum duration for head_away events. When unset, "
            "min_missed_window_ms applies. Phone visibility never qualifies alone, "
            "and absence signals always use min_missed_window_ms."
        ),
    )
    phone_support_confidence: float = Field(default=0.5, ge=0, le=1)
    phone_looking_down_ms: int = Field(default=20_000, ge=1)
    phone_unfocused_absent_ms: int = Field(default=15_000, ge=1)
    max_batch_events: int = Field(
        default=50, description="Maximum signal events accepted per batch.", ge=1
    )
    max_batch_chunks: int = Field(
        default=200, description="Maximum transcript chunks accepted per batch.", ge=1
    )
    max_transcript_text_chars: int = Field(
        default=4_000,
        description="Maximum accepted text length for one transcript chunk.",
        ge=1,
    )
    openai_api_key: str | None = Field(
        default=None,
        description="API key for the live OpenAI adapter; opt-in only.",
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        description="Model used by the live OpenAI adapter.",
    )

    def is_demo_or_test(self) -> bool:
        """Return whether privileged demo/test helpers are available."""

        return self.app_env in (DEMO_ENV, TEST_ENV)


def _optional_positive_int(name: str) -> int | None:
    """Read an optional positive integer environment variable.

    Args:
        name: Environment variable name.

    Returns:
        The parsed integer, or None when the variable is unset or empty.

    Raises:
        ValueError: When the value is not a positive integer.
    """

    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    value = int(raw)
    if value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _settings_from_environment() -> Settings:
    """Build settings from environment variables with compatibility checks.

    Returns:
        Validated application settings.

    Raises:
        ValueError: When an environment value is unknown or production is
            configured with the default development secret.
    """

    settings = Settings(
        app_env=os.environ.get("APP_ENV", DEVELOPMENT_ENV),
        provider_mode=os.environ.get("PROVIDER_MODE", MOCK_PROVIDER_MODE),
        app_secret=os.environ.get("APP_SECRET", DEFAULT_DEMO_SECRET),
        jwt_algorithm=os.environ.get("JWT_ALGORITHM", "HS256"),
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        min_head_away_window_ms=_optional_positive_int("MIN_HEAD_AWAY_WINDOW_MS"),
    )
    if settings.app_env == DEMO_ENV and settings.min_head_away_window_ms is None:
        settings.min_head_away_window_ms = DEMO_HEAD_AWAY_WINDOW_MS
    if settings.app_env not in KNOWN_ENVIRONMENTS:
        raise ValueError(f"Unknown APP_ENV: {settings.app_env}")
    if settings.provider_mode not in KNOWN_PROVIDER_MODES:
        raise ValueError(f"Unknown PROVIDER_MODE: {settings.provider_mode}")
    if settings.app_env == PRODUCTION_ENV and settings.app_secret == DEFAULT_DEMO_SECRET:
        raise ValueError("Production requires a real APP_SECRET.")
    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached process settings resolved from the environment.

    Returns:
        Validated application settings.
    """

    return _settings_from_environment()
