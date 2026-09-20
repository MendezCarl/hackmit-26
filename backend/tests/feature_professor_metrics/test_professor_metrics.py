"""No observation coverage must never become healthy lecture continuity."""

from app.contracts.learning import CoverageBatch, EvidenceCoverage, MetricsPolicy
from app.contracts.models import SessionStatus
from app.professor.metrics import ProfessorMetricsService

from .support import actor, fixture


def test_missing_coverage_and_revocation_suppress_evidence():
    store, state, access, settings = fixture()
    service = ProfessorMetricsService(
        store,
        state,
        access,
        settings,
        MetricsPolicy(
            policy_version="synthetic", minimum_group_size=5, bucket_ms=30_000
        ),
    )
    store.sessions["s"].status = SessionStatus.ENDED
    assert service.report(actor("prof", "professor"), "s").continuity is None
    store.sessions["s"].status = SessionStatus.ACTIVE
    for i in range(1, 6):
        service.ingest_coverage(
            actor(f"student{i}"),
            "s",
            CoverageBatch(
                records=[
                    EvidenceCoverage(
                        coverage_id="c", start_ms=0, end_ms=30_000, is_available=True
                    )
                ]
            ),
        )
    store.sessions["s"].status = SessionStatus.ENDED
    assert service.report(actor("prof", "professor"), "s").continuity.ratio == 1
    store.participants["s"]["student5"].is_opted_in = False
    result = service.report(actor("prof", "professor"), "s")
    assert result.status == "suppressed" and result.buckets[0].coverage is None
