"""Coverage-aware anonymous reporting from the professor dashboard plan."""

from collections.abc import Iterable
from typing import Literal

from app.auth.access import (
    SESSION_ROLE_COURSE_PROFESSOR,
    SESSION_ROLE_OWNER,
    SessionAccess,
)
from app.auth.tokens import AuthenticatedActor
from app.config import Settings
from app.contracts.learning import (
    BatchReceipt,
    CoverageBatch,
    DeliveryFinding,
    EvidenceCoverage,
    MetricsBucket,
    MetricsPolicy,
    ProfessorMetrics,
    ReleasedRatio,
)
from app.contracts.models import SessionStatus
from app.core.errors import AppError, ErrorCode
from app.learning.state import LearningState
from app.storage.in_memory import InMemoryStore

APPROVED_SIGNALS = {
    "face_absent",
    "head_away",
    "looking_down",
    "window_unfocused",
    "student_left_frame",
    "user_marked_confused",
    "possible_missed_window",
}
DELIVERY_ACTIONS = {
    "presenter_out_of_frame": "Check presenter framing or provide a verbal explanation.",
    "board_or_screen_occluded": "Check that the board or shared screen is visible.",
    "slide_text_low_legibility": "Consider larger text or a higher-contrast slide.",
}


def covered_duration(intervals: Iterable[tuple[int, int]], start: int, end: int) -> int:
    """Return union duration in milliseconds; overlaps and retries never inflate it."""
    ordered = sorted(
        (max(a, start), min(b, end)) for a, b in intervals if a < end and start < b
    )
    total, cursor = 0, start
    for left, right in ordered:
        total += max(0, right - max(cursor, left))
        cursor = max(cursor, right)
    return total


def released_ratio(numerator: int, denominator: int) -> ReleasedRatio:
    """Build a released ratio; caller must establish a safe positive denominator."""
    return ReleasedRatio(
        numerator=numerator, denominator=denominator, ratio=numerator / denominator
    )


class ProfessorMetricsService:
    """Derive reports from current consent, explicit coverage and corrected signals."""

    def __init__(
        self,
        store: InMemoryStore,
        state: LearningState,
        access: SessionAccess,
        settings: Settings,
        policy: MetricsPolicy | None,
    ) -> None:
        """Inject host state and policy; no provider, filesystem or network effects."""
        self.store, self.state, self.access = store, state, access
        self.settings, self.policy = settings, policy

    def ingest_coverage(
        self, actor: AuthenticatedActor, session_id: str, batch: CoverageBatch
    ) -> BatchReceipt:
        """Atomically record own coverage; reject identity claims, conflicts and capacity overflow."""
        membership = self.access.resolve_membership(actor, session_id)
        participant = self.store.participants.get(session_id, {}).get(actor.user_id)
        if (
            actor.role != "student"
            or not membership.is_opted_in
            or participant is None
            or not participant.is_opted_in
        ):
            raise AppError(
                ErrorCode.FORBIDDEN, "Coverage requires current aggregation consent."
            )
        if self.store.sessions[session_id].status == SessionStatus.ENDED:
            raise AppError(ErrorCode.VALIDATION_FAILED, "Coverage ingestion has ended.")
        with self.state.lock:
            pending: dict[tuple[str, str, str], EvidenceCoverage] = {}
            duplicates = 0
            for record in batch.records:
                key = (session_id, actor.user_id, record.coverage_id)
                previous = pending.get(key, self.state.coverage.get(key))
                if previous is not None:
                    if previous != record:
                        raise AppError(
                            ErrorCode.DUPLICATE,
                            "Coverage identifier conflicts with an existing record.",
                        )
                    duplicates += 1
                else:
                    pending[key] = record.model_copy(deep=True)
            if len(self.state.coverage) + len(pending) > self.state.maximum_records:
                raise AppError(ErrorCode.PAYLOAD_TOO_LARGE, "Coverage capacity reached.")
            self.state.coverage.update(pending)
        return BatchReceipt(accepted=len(pending), duplicates=duplicates)

    def report(self, actor: AuthenticatedActor, session_id: str) -> ProfessorMetrics:
        """Return fixed-bucket evidence, suppressing small or poorly observed groups.

        Raises:
            AppError: For unauthorized readers, active sessions, missing policy,
                or a policy not explicitly approved outside test/demo.
        """
        membership = self.access.resolve_membership(actor, session_id)
        session = self.store.sessions[session_id]
        if actor.role != "professor" or membership.session_role not in (
            SESSION_ROLE_OWNER,
            SESSION_ROLE_COURSE_PROFESSOR,
        ):
            raise AppError(ErrorCode.FORBIDDEN, "Course professor access is required.")
        if session.status != SessionStatus.ENDED:
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                "Reports are available after the session ends.",
            )
        policy = self.policy
        if policy is None or (
            not policy.is_approved and not self.settings.is_demo_or_test()
        ):
            raise AppError(
                ErrorCode.FORBIDDEN, "An approved aggregation policy is required."
            )
        participants = {
            key
            for key, record in self.store.participants.get(session_id, {}).items()
            if record.is_opted_in
        }
        chunks = [
            chunk
            for chunk in self.store.transcript_chunks.get(session_id, [])
            if chunk.is_final
        ]
        end_ms = min(28_800_000, max((chunk.end_ms for chunk in chunks), default=0))
        with self.state.lock:
            coverage = [
                (key[1], record.model_copy())
                for key, record in self.state.coverage.items()
                if key[0] == session_id and key[1] in participants
            ]
            deliveries = [
                event.model_copy(deep=True)
                for key, event in self.state.delivery.items()
                if key[0] == session_id
            ]
        buckets = []
        for start in range(0, end_ms, policy.bucket_ms):
            end = min(end_ms, start + policy.bucket_ms)
            bucket = MetricsBucket(start_ms=start, end_ms=end, status="suppressed")
            if len(participants) < policy.minimum_group_size:
                buckets.append(bucket)
                continue
            observed = set()
            for participant in participants:
                records = [record for owner, record in coverage if owner == participant]
                available_ms = covered_duration(
                    ((r.start_ms, r.end_ms) for r in records if r.is_available),
                    start,
                    end,
                )
                # An explicit unavailable interval wins over conflicting positive coverage.
                unavailable_ms = covered_duration(
                    ((r.start_ms, r.end_ms) for r in records if not r.is_available),
                    start,
                    end,
                )
                if unavailable_ms == 0 and available_ms == end - start:
                    observed.add(participant)
            if len(observed) < policy.minimum_group_size:
                bucket.status = "insufficient_evidence"
                buckets.append(bucket)
                continue
            bucket.coverage = released_ratio(len(observed), len(participants))
            if bucket.coverage.ratio < policy.minimum_coverage_ratio:
                bucket.status = "insufficient_evidence"
                buckets.append(bucket)
                continue
            affected = set()
            for owner in observed:
                intervals = []
                for record in self.store.events.get(session_id, []):
                    event = record.event
                    if record.submitted_by != owner or event.user_confirmed is False:
                        continue
                    if (
                        event.event_type not in APPROVED_SIGNALS
                        or "phone_visible" in event.signals
                    ):
                        continue
                    if event.event_type == "looking_down" and not event.user_confirmed:
                        continue
                    if (
                        event.confidence < policy.minimum_signal_confidence
                        and not event.user_confirmed
                    ):
                        continue
                    intervals.append((event.start_ms, event.end_ms))
                if covered_duration(intervals, start, end) >= min(
                    policy.minimum_signal_duration_ms, end - start
                ):
                    affected.add(owner)
            bucket.status = "available"
            bucket.possible_missed = released_ratio(len(affected), len(observed))
            bucket.is_hotspot = bucket.possible_missed.ratio >= policy.hotspot_ratio
            if bucket.is_hotspot:
                bucket.transcript_chunk_ids = [
                    c.chunk_id for c in chunks if c.start_ms < end and start < c.end_ms
                ][:100]
                bucket.suggested_action = "Some students may have missed context during this interval. Offer an optional recap."
            buckets.append(bucket)
        available = [bucket for bucket in buckets if bucket.status == "available"]
        findings = []
        for delivery_event in deliveries:
            # Delivery observations are separate; only release fully covered safe buckets.
            if (
                covered_duration(
                    ((b.start_ms, b.end_ms) for b in available),
                    delivery_event.start_ms,
                    delivery_event.end_ms,
                )
                == delivery_event.end_ms - delivery_event.start_ms
            ):
                findings.append(
                    DeliveryFinding(
                        start_ms=delivery_event.start_ms,
                        end_ms=delivery_event.end_ms,
                        signal_type=delivery_event.signal_type,
                        confidence=delivery_event.confidence,
                        suggested_action=DELIVERY_ACTIONS[delivery_event.signal_type],
                    )
                )
        status: Literal["available", "suppressed", "insufficient_evidence"] = (
            "available"
            if available
            else (
                "suppressed"
                if len(participants) < policy.minimum_group_size
                else "insufficient_evidence"
            )
        )
        return ProfessorMetrics(
            session_id=session_id,
            policy_version=policy.policy_version,
            status=status,
            minimum_group_size=policy.minimum_group_size,
            bucket_ms=policy.bucket_ms,
            buckets=buckets,
            continuity=released_ratio(
                sum(not b.is_hotspot for b in available), len(available)
            )
            if available
            else None,
            delivery_findings=findings[:100],
        )
