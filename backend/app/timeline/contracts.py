"""Typed integration ports supplied by Person A; no authentication is invented here."""

from datetime import datetime
from typing import Annotated, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_LECTURE_MS = 8 * 60 * 60 * 1000
MAX_QUERY_MS = 10 * 60 * 1000
Identifier = Annotated[
    str, Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
]
Milliseconds = Annotated[int, Field(strict=True, ge=0, le=MAX_LECTURE_MS)]


class StrictModel(BaseModel):
    """Reject unknown properties and non-finite numbers at every feature boundary."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Interval(StrictModel):
    """A half-open interval on the lecture clock, measured in integer milliseconds."""

    start_ms: Milliseconds = Field(description="Inclusive lecture-relative start.")
    end_ms: Milliseconds = Field(description="Exclusive lecture-relative end.")

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        """Return this interval; raise ValueError for empty or reversed intervals."""
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class SessionGrant(StrictModel):
    """Trusted authorization result from the host, never accepted as HTTP input."""

    session_id: Identifier
    lecture_id: Identifier
    actor_id: Identifier
    participant_key: Identifier
    role: Literal["student", "professor", "transcriber"]
    can_signal: bool = False
    can_transcribe: bool = False
    can_use_dropbox: bool = False
    has_signal_consent: bool = False
    is_ended: bool = False
    duration_ms: Annotated[int, Field(strict=True, gt=0, le=MAX_LECTURE_MS)]
    clock_origin_epoch_ms: Annotated[int, Field(strict=True, ge=0)]


class Participation(Interval):
    """Trusted opted-in attendance interval; internal keys never reach professors."""

    participant_key: Identifier
    has_aggregate_consent: bool


class SessionAccess(Protocol):
    """Host authorization and consent boundary; implementations must fail closed."""

    async def authorize(self, token: str, session_id: str) -> SessionGrant:
        """Return current membership/consent; raise FeatureError for denied access."""
        ...

    async def participants(self, session_id: str) -> list[Participation]:
        """Return current authoritative consent/attendance for aggregation only."""
        ...


class FeatureError(Exception):
    """A safe public error; its message must never contain inputs or provider details."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        """Initialize stable error code, safe message and HTTP status."""
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ErrorDetail(StrictModel):
    """Stable error fields without echoed input, tokens, or transcript text."""

    code: str
    message: str
    request_id: str


class ErrorResponse(StrictModel):
    """Standard repository error envelope."""

    error: ErrorDetail


class Receipt(StrictModel):
    """Batch result: accepted writes, exact retries, and current session revision."""

    accepted: int
    duplicates: int
    revision: int


class EventEnvelope(StrictModel):
    """Realtime envelope whose payload is validated by its concrete event model."""

    event_id: Identifier
    event_type: Literal["transcript.batch.accepted", "error.occurred"]
    schema_version: Literal["1.0.0"] = "1.0.0"
    session_id: Identifier
    occurred_at: datetime
    sequence_number: Annotated[int, Field(ge=0)]
    payload: Receipt | ErrorResponse


def require_interval(grant: SessionGrant, interval: Interval) -> None:
    """Raise FeatureError when an interval exceeds the trusted session duration."""
    if interval.end_ms > grant.duration_ms:
        raise FeatureError("invalid_time_range", "Interval exceeds the session duration.")


def overlaps(left: Interval, right: Interval) -> bool:
    """Return whether two half-open lecture intervals overlap."""
    return left.start_ms < right.end_ms and right.start_ms < left.end_ms
