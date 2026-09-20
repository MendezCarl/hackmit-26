"""Shared UTC clock used for wall-clock timestamps across features."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Return the current UTC wall-clock time as an ISO 8601 string.

    Returns:
        UTC timestamp with millisecond precision ending in ``Z``, matching
        the repository contract for wall-clock values.
    """

    formatted = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")
    return formatted[:-3] + "Z"
