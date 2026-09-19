"""Public aggregate contracts contain no student identifiers or private signal histories."""

from typing import Annotated, Literal

from pydantic import Field

from app.timeline.contracts import Interval, StrictModel


class AggregationPolicy(StrictModel):
    """Explicit host-approved policy; demo values are not production approval."""

    minimum_group_size: Annotated[int, Field(strict=True, ge=3)]
    aggregation_window_ms: Annotated[int, Field(strict=True, ge=10_000, le=300_000)]
    policy_version: Annotated[str, Field(min_length=1, max_length=50)]


class SummaryBucket(Interval):
    """Fixed bucket; suppressed buckets reveal neither counts nor signal ratios."""

    is_suppressed: bool
    participant_count: int | None = None
    possible_missed_ratio: float | None = None


class ProfessorSummary(StrictModel):
    """Post-lecture aggregates, not an attention/comprehension assessment."""

    session_id: str
    status: Literal["available", "suppressed"]
    minimum_group_size: int
    aggregation_window_ms: int
    policy_version: str
    timeline_buckets: list[SummaryBucket]
    highest_signal_intervals: list[SummaryBucket]
    suggested_actions: list[str]
