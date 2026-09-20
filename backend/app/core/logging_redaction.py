"""Log redaction keeping secrets and raw media references out of logs.

Authorization headers, bearer tokens, and WebSocket token query parameters are
redacted before any record is emitted. Transcript text, student identifiers,
and local media paths must never be logged by calling code; this filter is a
last line of defense for accidental leakage of credential patterns.
"""

from __future__ import annotations

import logging
import re

REDACTED_TEXT = "[REDACTED]"
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
BEARER_TOKEN_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+")
TOKEN_QUERY_PATTERN = re.compile(r"(token=)[A-Za-z0-9._~+/=-]+", re.IGNORECASE)


def redact_message(message: str) -> str:
    """Redact credential patterns from one log message.

    Args:
        message: Raw formatted log message.

    Returns:
        The message with bearer tokens and ``token=`` values replaced by a
        ``[REDACTED]`` placeholder.
    """

    redacted = BEARER_TOKEN_PATTERN.sub(f"Bearer {REDACTED_TEXT}", message)
    return TOKEN_QUERY_PATTERN.sub(r"\g<1>" + REDACTED_TEXT, redacted)


class RedactingLogFilter(logging.Filter):
    """Logging filter that redacts credentials from every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact the fully formatted message of one log record.

        Args:
            record: The log record being emitted.

        Returns:
            Always ``True`` so the record continues through the pipeline.
        """

        record.msg = redact_message(record.getMessage())
        record.args = None
        return True


def install_logging(level: int = logging.INFO) -> None:
    """Install the redacting handler on the root logger once per process.

    Args:
        level: Root logger level to configure.
    """

    root_logger = logging.getLogger()
    if any(
        isinstance(existing_filter, RedactingLogFilter)
        for handler in root_logger.handlers
        for existing_filter in handler.filters
    ):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    handler.addFilter(RedactingLogFilter())
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
