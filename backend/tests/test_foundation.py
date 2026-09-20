"""Foundation tests: log redaction and configuration compatibility checks."""

import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import (  # noqa: E402
    DEFAULT_DEMO_SECRET,
    _settings_from_environment,
)
from app.core.logging_redaction import (  # noqa: E402
    REDACTED_TEXT,
    RedactingLogFilter,
    install_logging,
    redact_message,
)


def test_redact_message_masks_bearer_tokens() -> None:
    """Bearer tokens in log text must be replaced by a redaction marker."""

    message = "Rejected request with Authorization: Bearer abc123.def456"
    redacted = redact_message(message)
    assert "abc123" not in redacted
    assert f"Bearer {REDACTED_TEXT}" in redacted


def test_redact_message_masks_websocket_token_query() -> None:
    """WebSocket token query parameters must be redacted."""

    message = "connect /ws/v1/sessions/s_1?token=eyJhbGciOiJIUzI1NiJ9.payload.sig"
    redacted = redact_message(message)
    assert "eyJhbGciOiJIUzI1NiJ9" not in redacted
    assert f"token={REDACTED_TEXT}" in redacted


def test_redacting_filter_rewrites_records(caplog) -> None:
    """The filter must redact credentials in emitted records."""

    logger = logging.getLogger("foundation_redaction_test")
    handler = logging.StreamHandler()
    handler.addFilter(RedactingLogFilter())
    logger.addHandler(handler)
    try:
        logger.setLevel(logging.DEBUG)
        with caplog.at_level(logging.DEBUG, logger="foundation_redaction_test"):
            logger.info("Authorization: Bearer super-secret-token")
    finally:
        logger.removeHandler(handler)
    assert "super-secret-token" not in caplog.text
    assert REDACTED_TEXT in caplog.text


def test_install_logging_is_idempotent() -> None:
    """Installing logging twice must not add duplicate handlers."""

    install_logging()
    count_after_first = len(logging.getLogger().handlers)
    install_logging()
    count_after_second = len(logging.getLogger().handlers)
    assert count_after_second == count_after_first
    root_logger = logging.getLogger()
    assert any(
        isinstance(existing_filter, RedactingLogFilter)
        for handler in root_logger.handlers
        for existing_filter in handler.filters
    )


def test_production_rejects_default_secret(monkeypatch) -> None:
    """Production must refuse to start with the development secret."""

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_SECRET", DEFAULT_DEMO_SECRET)
    try:
        _settings_from_environment()
    except ValueError as exc:
        assert "APP_SECRET" in str(exc)
    else:
        raise AssertionError("Production with default secret must be rejected.")


def test_unknown_environment_is_rejected(monkeypatch) -> None:
    """Unknown APP_ENV values must fail fast."""

    monkeypatch.setenv("APP_ENV", "staging")
    try:
        _settings_from_environment()
    except ValueError as exc:
        assert "APP_ENV" in str(exc)
    else:
        raise AssertionError("Unknown APP_ENV must be rejected.")


def test_unknown_provider_mode_is_rejected(monkeypatch) -> None:
    """Unknown PROVIDER_MODE values must fail fast."""

    monkeypatch.setenv("PROVIDER_MODE", "turbo")
    try:
        _settings_from_environment()
    except ValueError as exc:
        assert "PROVIDER_MODE" in str(exc)
    else:
        raise AssertionError("Unknown PROVIDER_MODE must be rejected.")


def test_environment_threshold_overrides_are_loaded(monkeypatch) -> None:
    """Documented numeric environment variables must affect runtime settings."""

    monkeypatch.setenv("JWT_TTL_SECONDS", "7200")
    monkeypatch.setenv("MINIMUM_GROUP_SIZE", "7")
    monkeypatch.setenv("PHONE_SUPPORT_CONFIDENCE", "0.7")

    settings = _settings_from_environment()

    assert settings.jwt_ttl_seconds == 7200
    assert settings.minimum_group_size == 7
    assert settings.phone_support_confidence == 0.7
