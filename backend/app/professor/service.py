"""Pure deduplicated aggregation; authorization and consent remain host responsibilities."""

from app.professor.models import AggregationPolicy, ProfessorSummary, SummaryBucket
from app.signals.models import StoredSignal
from app.timeline.contracts import (
    FeatureError,
    Participation,
    SessionAccess,
    SessionGrant,
    overlaps,
)
from app.timeline.repository import SessionRepository


def aggregate_signals(
    grant: SessionGrant,
    signals: list[StoredSignal],
    participants: list[Participation],
    policy: AggregationPolicy,
) -> ProfessorSummary:
    """Count unique consenting participants in fixed buckets and suppress small groups.

    Only participants present for an entire bucket enter its denominator. Multiple
    events count once; dismissed, phone-related and return-marker events never
    contribute. Phone observations are for private recovery only. No identities leave this
    function. The host supplies the current roster, including consent withdrawal.
    """
    buckets: list[SummaryBucket] = []
    for start_ms in range(0, grant.duration_ms, policy.aggregation_window_ms):
        end_ms = min(grant.duration_ms, start_ms + policy.aggregation_window_ms)
        eligible = {
            member.participant_key
            for member in participants
            if member.has_aggregate_consent
            and member.start_ms <= start_ms
            and member.end_ms >= end_ms
        }
        bucket = SummaryBucket(start_ms=start_ms, end_ms=end_ms, is_suppressed=True)
        if len(eligible) >= policy.minimum_group_size:
            affected = {
                stored.participant_key
                for stored in signals
                if stored.participant_key in eligible
                and stored.event.user_confirmed is not False
                and stored.event.event_type not in {"phone_visible", "student_returned"}
                and "phone_visible" not in stored.event.signals
                and set(stored.event.signals) != {"student_returned"}
                and overlaps(stored.event, bucket)
            }
            bucket.is_suppressed = False
            bucket.participant_count = len(eligible)
            bucket.possible_missed_ratio = round(len(affected) / len(eligible), 3)
        buckets.append(bucket)
    ranked = sorted(
        (
            bucket
            for bucket in buckets
            if bucket.possible_missed_ratio is not None
            and bucket.possible_missed_ratio > 0
        ),
        key=lambda bucket: (-(bucket.possible_missed_ratio or 0), bucket.start_ms),
    )[:3]
    return ProfessorSummary(
        session_id=grant.session_id,
        status="available"
        if any(not bucket.is_suppressed for bucket in buckets)
        else "suppressed",
        minimum_group_size=policy.minimum_group_size,
        aggregation_window_ms=policy.aggregation_window_ms,
        policy_version=policy.policy_version,
        timeline_buckets=buckets,
        highest_signal_intervals=ranked,
        suggested_actions=[
            f"Offer an optional recap of {bucket.start_ms // 1000}–{bucket.end_ms // 1000} seconds; some students may have missed context."
            for bucket in ranked
        ],
    )


class ProfessorService:
    """Authorize post-lecture reads and recompute against current consent/corrections."""

    def __init__(
        self,
        repository: SessionRepository,
        access: SessionAccess,
        policy: AggregationPolicy | None,
    ) -> None:
        """Inject storage, trusted membership access, and an explicitly approved policy."""
        self.repository = repository
        self.access = access
        self.policy = policy

    async def summarize(self, grant: SessionGrant) -> ProfessorSummary:
        """Return a safe report; deny students, active sessions, or unconfigured policy."""
        if grant.role != "professor":
            raise FeatureError("forbidden", "Professor access is required.", 403)
        if not grant.is_ended:
            raise FeatureError(
                "session_active", "The report is available after the lecture ends.", 409
            )
        if self.policy is None:
            raise FeatureError(
                "aggregation_policy_required",
                "An approved aggregation policy is required.",
                503,
            )
        state = await self.repository.load(grant.session_id)
        participants = await self.access.participants(grant.session_id)
        return aggregate_signals(grant, state.signals, participants, self.policy)
