"""Additive contracts implementing the three reviewed planning documents.

All intervals share the lecture clock. These derived payloads cannot carry media.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_LECTURE_MS = 28_800_000
Identifier = Annotated[
    str, Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
]
Millis = Annotated[int, Field(strict=True, ge=0, le=MAX_LECTURE_MS)]
Ratio = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class StrictPayload(BaseModel):
    """Reject unknown keys and non-finite numbers at derived-data boundaries."""

    model_config = ConfigDict(
        extra="forbid", strict=True, allow_inf_nan=False, revalidate_instances="always"
    )


class LectureInterval(StrictPayload):
    """Half-open lecture-relative interval, in integer milliseconds."""

    start_ms: Millis
    end_ms: Millis

    @model_validator(mode="after")
    def ordered(self) -> Self:
        """Return a valid interval; raise ValueError for empty/reversed ranges."""
        if self.start_ms >= self.end_ms:
            raise ValueError("end_ms must exceed start_ms")
        return self


class EvidenceCoverage(LectureInterval):
    """A local observation interval, including detector-unavailable periods.

    Identity is resolved from JWT. Available means observations ran, not attention.
    """

    coverage_id: Identifier
    is_available: bool


class CoverageBatch(StrictPayload):
    """Atomic coverage ingestion; no more than 100 interval records."""

    records: list[EvidenceCoverage] = Field(min_length=1, max_length=100)


class BatchReceipt(StrictPayload):
    """Accepted records and exact retries; conflicting identifiers fail atomically."""

    accepted: int = Field(ge=0)
    duplicates: int = Field(ge=0)


class DeliveryEvidence(StrictPayload):
    """Bounded derived observations; boxes, frame paths and identities are forbidden."""

    sample_count: int = Field(strict=True, ge=1, le=100_000)
    positive_sample_count: int = Field(strict=True, ge=1, le=100_000)
    performance_profile: Literal["low_power", "balanced", "performance"]

    @model_validator(mode="after")
    def bounded_samples(self) -> Self:
        """Reject evidence with more positives than samples."""
        if self.positive_sample_count > self.sample_count:
            raise ValueError("positive samples exceed sample count")
        return self


DeliveryKind = Literal[
    "presenter_out_of_frame", "board_or_screen_occluded", "slide_text_low_legibility"
]


class DeliveryEvent(LectureInterval):
    """Derived lecture-delivery issue, separate from student recovery observations."""

    event_id: Identifier
    signal_type: DeliveryKind
    confidence: Ratio
    detector_version: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    evidence: DeliveryEvidence


class DeliveryBatch(StrictPayload):
    """Bounded delivery events; the URL and verified actor define session scope."""

    events: list[DeliveryEvent] = Field(min_length=1, max_length=50)


class MetricsPolicy(StrictPayload):
    """Explicit reporting policy. Synthetic defaults are never production approval."""

    policy_version: Identifier
    minimum_group_size: int = Field(ge=3, le=1000)
    bucket_ms: int = Field(ge=10_000, le=300_000)
    minimum_coverage_ratio: Ratio = 0.6
    hotspot_ratio: Ratio = 0.4
    minimum_signal_duration_ms: int = Field(ge=1, le=300_000, default=10_000)
    minimum_signal_confidence: Ratio = 0.5
    is_approved: bool = False


class ReleasedRatio(StrictPayload):
    """A ratio with its denominator; absent means insufficient or suppressed evidence."""

    numerator: int = Field(ge=0)
    denominator: int = Field(gt=0)
    ratio: Ratio


class MetricsBucket(LectureInterval):
    """One fixed bucket; suppression hides counts, ratios and evidence alike."""

    status: Literal["available", "suppressed", "insufficient_evidence"]
    coverage: ReleasedRatio | None = None
    possible_missed: ReleasedRatio | None = None
    is_hotspot: bool | None = None
    transcript_chunk_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    suggested_action: str | None = None


class DeliveryFinding(LectureInterval):
    """Professor-visible delivery evidence contains no detector identity or student data."""

    signal_type: DeliveryKind
    confidence: Ratio
    suggested_action: str


class ProfessorMetrics(StrictPayload):
    """Coverage-aware teaching report; missing learning outcomes are never invented."""

    session_id: Identifier
    policy_version: Identifier
    status: Literal["available", "suppressed", "insufficient_evidence"]
    minimum_group_size: int
    bucket_ms: int
    buckets: list[MetricsBucket]
    continuity: ReleasedRatio | None = None
    delivery_findings: list[DeliveryFinding] = Field(default_factory=list)
    recovery_outcomes_status: Literal["not_collected"] = "not_collected"


class ExternalTextConsent(StrictPayload):
    """Separate, revocable permission for bounded text to the chosen AI provider."""

    provider: Literal["openai", "meta_muse"] = "openai"
    is_allowed: bool


class GroundedFact(StrictPayload):
    """A claim and an exact evidence quote from a selected transcript chunk."""

    text: str = Field(min_length=1, max_length=600)
    chunk_id: Identifier
    evidence_quote: str = Field(min_length=1, max_length=1000)


class RecoveryDraft(StrictPayload):
    """Provider output; trusted IDs, timestamps and metadata are supplied by backend."""

    topic: str = Field(min_length=1, max_length=160)
    explanation: str = Field(min_length=1, max_length=3000)
    facts: list[GroundedFact] = Field(min_length=1, max_length=5)
    follow_up_question: str = Field(min_length=1, max_length=400)


RecommendationMedium = Literal["explanation", "pace", "example", "terminology"]
RecommendationEvidenceScope = Literal["intervals_only", "lecture_transcript"]


class Recommendation(StrictPayload):
    """Teaching suggestion tied to a released report bucket; never a student diagnosis.

    ``topic``, ``medium`` and ``evidence`` are present only when the lecture
    transcript for the interval was analyzed; every evidence quote must occur in
    a supplied transcript chunk, so the professor can verify the observation.
    """

    start_ms: Millis
    end_ms: Millis
    observation: str = Field(min_length=1, max_length=600)
    suggested_action: str = Field(min_length=1, max_length=600)
    topic: str | None = Field(default=None, min_length=1, max_length=160)
    medium: RecommendationMedium | None = None
    evidence: list[GroundedFact] = Field(default_factory=list, max_length=3)


class RecommendationDraft(StrictPayload):
    """Bounded AI suggestions from approved aggregate and lecture-transcript context."""

    recommendations: list[Recommendation] = Field(max_length=5)


class RecommendationReview(StrictPayload):
    """Professor feedback on a revision-bound suggestion."""

    report_revision: str = Field(min_length=64, max_length=64)
    recommendation_index: int = Field(ge=0, le=4)
    status: Literal["reviewed", "dismissed", "resolved"]


class RecommendationReport(StrictPayload):
    """Recommendations retain report revision, provider provenance and uncertainty."""

    session_id: Identifier
    report_revision: str
    status: Literal["available", "insufficient_evidence"]
    provider_mode: Literal["mock", "live"]
    evidence_scope: RecommendationEvidenceScope = "intervals_only"
    evidence_note: str | None = Field(default=None, max_length=400)
    recommendations: list[Recommendation]
    reviews: list[RecommendationReview] = Field(default_factory=list, max_length=5)


class AggregationConsent(StrictPayload):
    """Current participant's revocable anonymous reporting permission."""

    is_allowed: bool
