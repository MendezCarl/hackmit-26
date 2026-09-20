"""Shared Pydantic contracts for the lecture recovery backend.

These models are the canonical typed source of truth for REST and WebSocket
payloads. They mirror the JSON Schemas in ``shared/contracts/`` and the
schema summaries in ``docs/api/unified_api_contracts.md``.
"""

from __future__ import annotations

import math
import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0.0"


class SessionMode(str, Enum):
    """How a lecture session is held."""

    ZOOM = "zoom"
    IN_PERSON = "in_person"


class SessionStatus(str, Enum):
    """Lifecycle state of a lecture session."""

    CREATED = "created"
    ACTIVE = "active"
    ENDING = "ending"
    ENDED = "ended"
    FAILED = "failed"


class TranscriptSource(str, Enum):
    """Where a transcript chunk originated."""

    ZOOM_RTMS = "zoom_rtms"
    LOCAL_TRANSCRIPTION = "local_transcription"
    EXTERNAL_TRANSCRIPTION = "external_transcription"


class JobStatus(str, Enum):
    """Lifecycle state of a recovery job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobFailureReason(str, Enum):
    """Typed, recoverable failure reasons for recovery jobs."""

    MISSING_TRANSCRIPT_CONTEXT = "missing_transcript_context"
    PROVIDER_REFUSED = "provider_refused"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_MALFORMED_OUTPUT = "provider_malformed_output"
    VALIDATION_FAILED = "validation_failed"
    INTERNAL_ERROR = "internal_error"


class _StrictModel(BaseModel):
    """Base for request payloads that must reject unexpected fields."""

    model_config = ConfigDict(extra="forbid")


def _validate_interval(start_ms: int, end_ms: int) -> None:
    """Require the half-open interval ``0 <= start_ms < end_ms``.

    Raises:
        ValueError: When the interval is empty, reversed, or negative.
    """

    if start_ms < 0 or end_ms <= 0 or start_ms >= end_ms:
        raise ValueError(
            "Intervals are half-open [start_ms, end_ms) and require "
            "0 <= start_ms < end_ms."
        )


class CreateSessionRequest(_StrictModel):
    """Request to start one running occurrence of a lecture."""

    lecture_id: str = Field(min_length=1, max_length=128)
    course_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=256)
    mode: SessionMode
    zoom_meeting_id: str | None = Field(default=None, max_length=128)


class LectureSession(BaseModel):
    """One running occurrence of a lecture on the shared lecture clock."""

    session_id: str = Field(description="Unique identifier for this occurrence.")
    lecture_id: str = Field(description="Identifier of the underlying lecture record.")
    owner_id: str = Field(description="Authenticated user who started the session.")
    course_id: str = Field(description="Owning course identifier.")
    title: str = Field(description="Human-readable lecture-session title.")
    mode: SessionMode = Field(description="How the session is held.")
    status: SessionStatus = Field(description="Current lifecycle state.")
    started_at: str = Field(description="UTC ISO 8601 start time ending in Z.")
    ended_at: str | None = Field(default=None, description="UTC ISO 8601 end time.")
    session_clock_origin: str = Field(
        description="UTC ISO 8601 origin of the shared lecture clock."
    )
    zoom_meeting_id: str | None = Field(
        default=None, description="Zoom meeting identifier when authorized."
    )


class SignalEvent(BaseModel):
    """A coarse, privacy-preserving missed-content signal.

    Raw webcam frames, continuous raw audio, and screenshots never reach the
    server; only timestamped derived signals do.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    event_type: str = Field(
        min_length=1,
        max_length=64,
        description=(
            "possible_missed_window | face_absent | head_away | window_unfocused | ..."
        ),
    )
    start_ms: int = Field(ge=0, description="Half-open interval start in ms.")
    end_ms: int = Field(gt=0, description="Half-open interval end in ms.")
    signals: list[str] = Field(
        default_factory=list, description="Coarse signal names from the local client."
    )
    confidence: float = Field(
        description="Finite client confidence between 0 and 1, never an attention score."
    )
    user_confirmed: bool | None = Field(
        default=None,
        description="Student correction: confirmed or denied missed content.",
    )
    client_generated_at: str | None = Field(
        default=None, description="UTC ISO 8601 time the client generated the event."
    )

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        """Reject non-finite or out-of-range confidence values."""

        if not math.isfinite(value) or value < 0 or value > 1:
            raise ValueError("confidence must be a finite value between 0 and 1.")
        return value

    @model_validator(mode="after")
    def validate_interval_bounds(self) -> SignalEvent:
        """Require the half-open interval ``0 <= start_ms < end_ms``."""

        _validate_interval(self.start_ms, self.end_ms)
        return self


class IngestEventsRequest(_StrictModel):
    """Batch ingestion of timestamped signal events."""

    lecture_id: str = Field(
        min_length=1,
        max_length=128,
        description="Lecture record identifier; validated against the session.",
    )
    events: list[SignalEvent] = Field(min_length=1, description="Events to ingest.")


class ConfirmEventRequest(_StrictModel):
    """Student correction of a previously ingested signal event."""

    user_confirmed: bool = Field(
        description="True when the student confirms missed content."
    )


class RegisterParticipantRequest(_StrictModel):
    """Opt-in registration for aggregation; identity comes from authentication."""


class TranscriptChunk(BaseModel):
    """One timestamped transcript chunk on the shared lecture clock."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    start_ms: int = Field(ge=0, description="Half-open interval start in ms.")
    end_ms: int = Field(gt=0, description="Half-open interval end in ms.")
    text: str = Field(min_length=1, description="Transcript text for this chunk.")
    speaker_label: str | None = Field(
        default=None, description="Speaker label when permitted."
    )
    source: TranscriptSource = Field(description="Transcript origin.")
    is_final: bool = Field(
        default=True, description="False for provisional chunks awaiting correction."
    )
    revision: int = Field(
        default=1,
        ge=1,
        description="Version used to invalidate cached cards on correction.",
    )

    @model_validator(mode="after")
    def validate_interval_bounds(self) -> TranscriptChunk:
        """Require the half-open interval ``0 <= start_ms < end_ms``."""

        _validate_interval(self.start_ms, self.end_ms)
        return self


class IngestTranscriptRequest(_StrictModel):
    """Batch ingestion of timestamped transcript chunks."""

    lecture_id: str = Field(
        min_length=1,
        max_length=128,
        description="Lecture record identifier; validated against the session.",
    )
    chunks: list[TranscriptChunk] = Field(min_length=1, description="Chunks to ingest.")


class DerivedVisualContext(_StrictModel):
    """Bounded, user-selected derived text such as slide OCR.

    No screenshots or webcam frames are ever accepted; only derived text with
    timestamps and source references.
    """

    slide_number: int = Field(ge=1, description="Slide number within the lecture deck.")
    text_excerpt: str = Field(min_length=1, description="Bounded OCR text excerpt.")
    start_ms: int = Field(ge=0, description="Half-open interval start in ms.")
    end_ms: int = Field(gt=0, description="Half-open interval end in ms.")
    source_reference: str = Field(
        min_length=1,
        description="Source reference such as ``slide_ocr:lecture_1#slide_4``.",
    )


class ContextWindow(_StrictModel):
    """The retrieved context used to ground one recovery card."""

    session_id: str = Field(description="Authorized session scope for this window.")
    requested_start_ms: int = Field(ge=0, description="Requested interval start in ms.")
    requested_end_ms: int = Field(gt=0, description="Requested interval end in ms.")
    effective_start_ms: int = Field(ge=0, description="Clamped interval start in ms.")
    effective_end_ms: int = Field(gt=0, description="Clamped interval end in ms.")
    transcript_revision: int = Field(
        ge=0,
        description="Transcript revision used; invalidates cached cards on change.",
    )
    chunk_ids: list[str] = Field(description="Selected transcript chunk identifiers.")
    chunks: list[TranscriptChunk] = Field(
        description="Selected final transcript chunks."
    )
    derived_visual_context: list[DerivedVisualContext] = Field(
        default_factory=list, description="Permitted derived slide text, if any."
    )


class ModelMetadata(_StrictModel):
    """Provider metadata recorded with every generated card."""

    provider: str = Field(description="Provider name, e.g. ``mock`` or ``openai``.")
    model: str = Field(description="Model identifier used for generation.")
    provider_mode: Literal["mock", "live"] = Field(
        description="Execution mode; mock responses are labeled synthetic."
    )
    data_label: Literal["synthetic", "measured"] = Field(
        default="synthetic",
        description="Synthetic for mock usage; measured only for real provider calls.",
    )
    prompt_version: str = Field(description="Version of the recovery prompt.")
    output_schema_version: str = Field(description="Version of the output schema.")
    input_character_count: int = Field(ge=0, description="Bounded input size.")
    output_character_count: int = Field(ge=0, description="Generated output size.")
    latency_ms: int = Field(ge=0, description="Generation latency in milliseconds.")


class SourceTimestamp(_StrictModel):
    """A grounded source reference with lecture-relative timestamps."""

    start_ms: int = Field(ge=0, description="Half-open interval start in ms.")
    end_ms: int = Field(gt=0, description="Half-open interval end in ms.")
    chunk_id: str | None = Field(default=None, description="Source transcript chunk.")
    source: str | None = Field(default=None, description="Source system name.")


class RecoveryCard(BaseModel):
    """A grounded, compassionate explanation of missed lecture content."""

    card_id: str = Field(description="Unique recovery-card identifier.")
    session_id: str = Field(description="Session the card was generated for.")
    source_event_ids: list[str] = Field(
        description="Signal events that motivated this card."
    )
    topic: str = Field(description="Short topic label for what was missed.")
    what_you_missed: str = Field(
        description="Compassionate explanation of the missed content."
    )
    key_facts: list[str] = Field(description="Grounded facts from the lecture context.")
    example_from_lecture: str | None = Field(
        default=None, description="Closest lecture excerpt to the missed interval."
    )
    source_timestamps: list[SourceTimestamp] = Field(
        description="Source references and timestamps grounding the card."
    )
    follow_up_question: str = Field(description="Suggested follow-up for the student.")
    model_metadata: ModelMetadata = Field(description="Provider and usage metadata.")
    created_at: str = Field(description="UTC ISO 8601 creation time ending in Z.")


class CreateRecoveryJobRequest(_StrictModel):
    """Request to recover content for one lecture interval."""

    start_ms: int = Field(ge=0, description="Half-open interval start in ms.")
    end_ms: int = Field(gt=0, description="Half-open interval end in ms.")
    source_event_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Signal events that motivated this request; validated against the session."
        ),
    )

    @model_validator(mode="after")
    def validate_interval_bounds(self) -> CreateRecoveryJobRequest:
        """Require the half-open interval ``0 <= start_ms < end_ms``."""

        _validate_interval(self.start_ms, self.end_ms)
        return self


class JobFailure(BaseModel):
    """A typed, recoverable failure attached to a failed job."""

    reason: JobFailureReason = Field(description="Stable typed failure reason.")
    message: str = Field(
        description="Human-readable, compassionate failure explanation."
    )


class RecoveryJob(BaseModel):
    """Recovery generation job for one requested interval."""

    job_id: str = Field(description="Unique recovery-job identifier.")
    session_id: str = Field(description="Session the job belongs to.")
    status: JobStatus = Field(description="Current job status.")
    requested_start_ms: int = Field(ge=0, description="Requested interval start in ms.")
    requested_end_ms: int = Field(gt=0, description="Requested interval end in ms.")
    card_id: str | None = Field(
        default=None, description="Card reference when completed."
    )
    failure: JobFailure | None = Field(
        default=None, description="Typed failure when failed."
    )
    cache_status: Literal["miss", "hit"] | None = Field(
        default=None, description="Whether generation reused a cached card."
    )
    created_at: str = Field(description="UTC ISO 8601 creation time ending in Z.")
    completed_at: str | None = Field(
        default=None, description="UTC ISO 8601 completion time ending in Z."
    )


class CostMetrics(BaseModel):
    """Provider usage metrics for one recovery generation."""

    job_id: str = Field(description="Recovery job the metrics belong to.")
    session_id: str = Field(description="Session the job belongs to.")
    provider_mode: str = Field(description="Mock or live provider mode.")
    model: str = Field(description="Model identifier used.")
    input_usage: dict[str, int] = Field(
        description='Measured input usage, e.g. ``{"characters": 1200}``.'
    )
    output_usage: dict[str, int] = Field(description="Measured output usage.")
    cache_status: str = Field(description="``miss`` or ``hit`` for this generation.")
    latency_ms: int = Field(ge=0, description="Generation latency in milliseconds.")
    baseline_method: str = Field(
        description="Baseline comparison method; never implies fake responses save money."
    )
    data_label: str = Field(
        description="``synthetic`` for mock usage; ``measured`` for real provider calls."
    )


class TimelineBucket(BaseModel):
    """Anonymous aggregate event count for one fixed time bucket."""

    start_ms: int = Field(ge=0, description="Bucket start in ms.")
    end_ms: int = Field(gt=0, description="Bucket end in ms.")
    event_count: int = Field(ge=0, description="Anonymous event count in the bucket.")


class SignalIntervalAggregate(BaseModel):
    """Anonymous aggregate for one interval with high signal density."""

    start_ms: int = Field(ge=0, description="Interval start in ms.")
    end_ms: int = Field(gt=0, description="Interval end in ms.")
    event_count: int = Field(ge=0, description="Anonymous event count in the interval.")
    dominant_event_types: list[str] = Field(
        description="Most common event types; never individual confidence values."
    )


class ProfessorSummary(BaseModel):
    """Anonymous, aggregated, threshold-safe professor report.

    Never includes student IDs, names, device IDs, or individual confidence
    values. Small groups are suppressed.
    """

    summary_id: str = Field(description="Unique summary identifier.")
    session_id: str = Field(description="Session the summary describes.")
    participant_count: int = Field(
        ge=0,
        description="Unique participating, opted-in users, not events; deduplicated.",
    )
    minimum_group_size: int = Field(
        ge=1, description="Approved minimum group-size threshold."
    )
    aggregation_window_ms: int = Field(ge=1, description="Fixed bucket width in ms.")
    is_suppressed: bool = Field(
        description="True when the group is too small to release aggregates."
    )
    timeline_buckets: list[TimelineBucket] | None = Field(
        default=None, description="Anonymous buckets; null while suppressed."
    )
    highest_signal_intervals: list[SignalIntervalAggregate] | None = Field(
        default=None, description="Anonymous dense intervals; null while suppressed."
    )
    suggested_actions: list[str] | None = Field(
        default=None, description="Compassionate suggestions; null while suppressed."
    )
    generated_at: str = Field(description="UTC ISO 8601 generation time ending in Z.")


class EventEnvelope(BaseModel):
    """Typed WebSocket event envelope matching the AsyncAPI contract."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(description="Unique envelope identifier.")
    event_type: str = Field(
        description="Dotted past-tense event type, e.g. ``recovery_card.completed``."
    )
    schema_version: str = Field(
        default=SCHEMA_VERSION, description="Payload schema version."
    )
    session_id: str = Field(description="Session the event belongs to.")
    occurred_at: str = Field(description="UTC ISO 8601 occurrence time ending in Z.")
    sequence_number: int = Field(
        ge=0, description="Per-session monotonic sequence number."
    )
    payload: dict[str, Any] = Field(description="Typed event payload.")


class ErrorBody(_StrictModel):
    """Machine-readable error code and message."""

    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable error explanation.")
    details: dict[str, Any] | None = Field(
        default=None, description="Optional structured details; never secrets."
    )


class ErrorResponse(_StrictModel):
    """Repository-standard error envelope used by every endpoint."""

    error: ErrorBody = Field(description="The typed error body.")
EMAIL_ADDRESS_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
REGISTERED_ROLES: tuple[str, ...] = ("student", "professor")


class RegisterUserRequest(_StrictModel):
    """New-account registration; roles are chosen here, never in bodies later."""

    email: str = Field(min_length=3, max_length=254, description="Account email.")
    password: str = Field(
        min_length=8, max_length=128, description="Account password."
    )
    display_name: str = Field(min_length=1, max_length=128)
    role: Literal["student", "professor"] = Field(
        description="Requested account role."
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        """Reject malformed addresses without adding an email-parsing dependency."""

        if not EMAIL_ADDRESS_PATTERN.match(value):
            raise ValueError("email must be a valid email address.")
        return value.lower()


class LoginRequest(_StrictModel):
    """Existing-account login credentials."""

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """Normalize the address for lookup."""

        return value.lower()


class UserProfile(BaseModel):
    """Public profile of one account; password hashes are never exposed."""

    user_id: str = Field(description="Unique user identifier.")
    email: str = Field(description="Account email address.")
    role: str = Field(description="``student`` or ``professor``.")
    display_name: str = Field(description="Human-readable display name.")
    created_at: str = Field(description="UTC ISO 8601 creation time ending in Z.")


class AuthSession(BaseModel):
    """Issued credentials for one authenticated account."""

    user: UserProfile = Field(description="The authenticated account's profile.")
    access_token: str = Field(description="Signed JWT access token.")
    token_type: str = Field(default="bearer", description="Token type.")


class ConsentSettings(BaseModel):
    """Stored consent choices for one account."""

    analytics_opt_in: bool = Field(
        default=False,
        description="Whether the user opted into anonymous aggregated analytics.",
    )
    updated_at: str | None = Field(
        default=None, description="UTC ISO 8601 time the consent was last updated."
    )


class UpdateConsentRequest(_StrictModel):
    """Request updating one consent choice."""

    analytics_opt_in: bool = Field(description="New analytics opt-in value.")


class Course(BaseModel):
    """One course owned and taught by a professor."""

    course_id: str = Field(description="Unique course identifier.")
    owner_id: str = Field(description="Professor user who owns the course.")
    title: str = Field(description="Human-readable course title.")
    code: str = Field(description="Course catalog code.")
    created_at: str = Field(description="UTC ISO 8601 creation time ending in Z.")


class CreateCourseRequest(_StrictModel):
    """Request creating a course."""

    title: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=1, max_length=64)


class Lecture(BaseModel):
    """One lecture record belonging to a course."""

    lecture_id: str = Field(description="Unique lecture-record identifier.")
    course_id: str = Field(description="Owning course identifier.")
    owner_id: str = Field(description="Professor user who owns the lecture.")
    title: str = Field(description="Human-readable lecture title.")
    created_at: str = Field(description="UTC ISO 8601 creation time ending in Z.")


class CreateLectureRequest(_StrictModel):
    """Request creating a lecture record."""

    course_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=256)
