"""No AI recommendation is generated from suppressed evidence."""

from app.contracts.learning import ProfessorMetrics
from app.professor.recommendations import (
    DeterministicRecommendations,
    RecommendationService,
)

from .support import actor, fixture


class SuppressedMetrics:
    def report(self, actor, session_id):
        return ProfessorMetrics(
            session_id=session_id,
            policy_version="synthetic",
            status="suppressed",
            minimum_group_size=5,
            bucket_ms=30000,
            buckets=[],
        )


def test_suppressed_report_has_no_recommendations():
    _, state, _, _ = fixture()
    service = RecommendationService(
        SuppressedMetrics(), state, DeterministicRecommendations()
    )
    assert service.generate(actor("prof", "professor"), "s").recommendations == []
