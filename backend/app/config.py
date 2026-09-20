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
OPENAI_LIVE_PROVIDER = "openai"
MUSE_LIVE_PROVIDER = "meta_muse"
KNOWN_LIVE_PROVIDERS = (OPENAI_LIVE_PROVIDER, MUSE_LIVE_PROVIDER)

DEFAULT_DEMO_SECRET = "dev-only-secret-change-me-before-production"


def _read_int(name: str, default: int) -> int:
    """Read an integer environment variable.

    Args:
        name: Environment variable name.
        default: Value used when the environment variable is unset.

    Returns:
        Parsed integer value.

    Raises:
        ValueError: If the environment variable is set but is not an integer.
    """

    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc


def _read_float(name: str, default: float) -> float:
    """Read a floating-point environment variable.

    Args:
        name: Environment variable name.
        default: Value used when the environment variable is unset.

    Returns:
        Parsed floating-point value.

    Raises:
        ValueError: If the environment variable is set but is not numeric.
    """

    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric.") from exc


class Settings(BaseModel):
    """Runtime configuration resolved from environment variables.

    Environment variables (all optional outside production):

    - ``APP_ENV``: ``development``, ``test``, ``demo``, or ``production``.
    - ``PROVIDER_MODE``: ``mock`` (deterministic synthetic cards) or ``live``.
    - ``LIVE_PROVIDER``: ``openai`` or ``meta_muse`` when ``PROVIDER_MODE=live``.
    - ``APP_SECRET``: signing secret for JWT access tokens.
    - ``OPENAI_API_KEY`` and ``OPENAI_MODEL``: OpenAI live-provider settings.
    - ``MUSE_API_KEY``, ``MUSE_MODEL``, and ``MUSE_BASE_URL``: Meta Muse
      live-provider settings.
    - ``MONGODB_URI`` and ``MONGODB_DATABASE``: optional MongoDB persistence;
      the URI is never logged.
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
    live_provider: str = Field(
        default=OPENAI_LIVE_PROVIDER,
        description=(
            "Which cloud provider serves PROVIDER_MODE=live: openai or meta_muse."
        ),
    )
    muse_api_key: str | None = Field(
        default=None,
        description="Meta Model API key for the Muse adapter; never logged or returned.",
    )
    muse_model: str = Field(
        default="muse-spark-1.2",
        description="Model used by the live Meta Muse adapter.",
    )
    muse_base_url: str = Field(
        default="https://api.meta.ai/v1",
        description="Base URL for the OpenAI-compatible Meta Model API.",
    )
    mongodb_uri: str | None = Field(
        default=None,
        description="MongoDB connection URI; never logged.",
    )
    mongodb_database: str = Field(
        default="bloom",
        description="MongoDB database name for optional persistence.",
    )

    def is_demo_or_test(self) -> bool:
        """Return whether privileged demo/test helpers are available."""

        return self.app_env in (DEMO_ENV, TEST_ENV)


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
        jwt_ttl_seconds=_read_int("JWT_TTL_SECONDS", 3600),
        minimum_group_size=_read_int("MINIMUM_GROUP_SIZE", 5),
        aggregation_window_ms=_read_int("AGGREGATION_WINDOW_MS", 300_000),
        context_padding_ms=_read_int("CONTEXT_PADDING_MS", 30_000),
        max_context_padding_ms=_read_int("MAX_CONTEXT_PADDING_MS", 120_000),
        min_missed_window_ms=_read_int("MIN_MISSED_WINDOW_MS", 30_000),
        phone_support_confidence=_read_float("PHONE_SUPPORT_CONFIDENCE", 0.5),
        phone_looking_down_ms=_read_int("PHONE_LOOKING_DOWN_MS", 20_000),
        phone_unfocused_absent_ms=_read_int("PHONE_UNFOCUSED_ABSENT_MS", 15_000),
        max_batch_events=_read_int("MAX_BATCH_EVENTS", 50),
        max_batch_chunks=_read_int("MAX_BATCH_CHUNKS", 200),
        max_transcript_text_chars=_read_int("MAX_TRANSCRIPT_TEXT_CHARS", 4_000),
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        live_provider=os.environ.get("LIVE_PROVIDER", OPENAI_LIVE_PROVIDER),
        muse_api_key=os.environ.get("MUSE_API_KEY"),
        muse_model=os.environ.get("MUSE_MODEL", "muse-spark-1.2"),
        muse_base_url=os.environ.get("MUSE_BASE_URL", "https://api.meta.ai/v1"),
        mongodb_uri=os.environ.get("MONGODB_URI"),
        mongodb_database=os.environ.get("MONGODB_DATABASE", "bloom"),
    )
    if settings.app_env not in KNOWN_ENVIRONMENTS:
        raise ValueError(f"Unknown APP_ENV: {settings.app_env}")
    if settings.provider_mode not in KNOWN_PROVIDER_MODES:
        raise ValueError(f"Unknown PROVIDER_MODE: {settings.provider_mode}")
    if settings.live_provider not in KNOWN_LIVE_PROVIDERS:
        raise ValueError(f"Unknown LIVE_PROVIDER: {settings.live_provider}")
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
