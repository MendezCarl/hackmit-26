"""Reviewable teaching suggestions consume only already-released aggregates."""

import hashlib
from typing import Protocol

from app.auth.tokens import AuthenticatedActor
from app.contracts.learning import (
    ProfessorMetrics,
    Recommendation,
    RecommendationDraft,
    RecommendationReport,
    RecommendationReview,
)
from app.core.errors import AppError, ErrorCode
from app.learning.state import LearningState
from app.professor.ports import MetricsReader


class RecommendationGenerator(Protocol):
    """Generate bounded recommendations from a privacy-filtered report."""

    mode: str

    def generate(self, report: ProfessorMetrics) -> RecommendationDraft:
        """Return suggestions citing released intervals, or raise a safe provider error."""
        ...


class DeterministicRecommendations:
    """Synthetic suggestions for integration tests; no model or savings claim."""

    mode = "mock"

    def generate(self, report: ProfessorMetrics) -> RecommendationDraft:
        """Turn released hotspots into compassionate, evidence-bound suggestions."""
        return RecommendationDraft(
            recommendations=[
                Recommendation(
                    start_ms=b.start_ms,
                    end_ms=b.end_ms,
                    observation="Some students may have missed context during this interval.",
                    suggested_action="Offer an optional recap and invite clarification.",
                )
                for b in report.buckets
                if b.status == "available" and b.is_hotspot
            ][:5]
        )


class RecommendationService:
    """Recheck current policy/consent for generation and professor feedback."""

    def __init__(
        self,
        metrics: MetricsReader,
        state: LearningState,
        generator: RecommendationGenerator,
    ) -> None:
        """Inject report generation, feedback storage and the replaceable AI boundary."""
        self.metrics, self.state, self.generator = metrics, state, generator

    def generate(
        self, actor: AuthenticatedActor, session_id: str
    ) -> RecommendationReport:
        """Serialize consent/report snapshot and provider submission against revocation."""
        with self.state.lock:
            return self._generate(actor, session_id)

    def _generate(
        self, actor: AuthenticatedActor, session_id: str
    ) -> RecommendationReport:
        """Generate from safe aggregates; deny live processing without separate consent."""
        report = self.metrics.report(actor, session_id)
        revision = hashlib.sha256(report.model_dump_json().encode()).hexdigest()
        if report.status != "available":
            return RecommendationReport(
                session_id=session_id,
                report_revision=revision,
                status="insufficient_evidence",
                provider_mode="mock" if self.generator.mode == "mock" else "live",
                recommendations=[],
            )
        if (
            self.generator.mode == "live"
            and (session_id, actor.user_id, "openai") not in self.state.external_consent
        ):
            raise AppError(
                ErrorCode.FORBIDDEN,
                "External aggregate processing requires provider consent.",
            )
        run_key = (session_id, actor.user_id, revision)
        with self.state.lock:
            if run_key in self.state.recommendation_runs:
                cached = self.state.recommendation_runs[run_key].model_copy(deep=True)
                cached.reviews = [
                    review.model_copy(deep=True)
                    for key, review in self.state.reviews.items()
                    if key[:3] == (session_id, actor.user_id, revision)
                ]
                return cached
            if len(self.state.recommendation_runs) >= self.state.maximum_records:
                raise AppError(
                    ErrorCode.PAYLOAD_TOO_LARGE, "Recommendation capacity reached."
                )
            draft = self.generator.generate(report)
        allowed = {
            (b.start_ms, b.end_ms)
            for b in report.buckets
            if b.status == "available" and b.is_hotspot
        }
        for item in draft.recommendations:
            if (item.start_ms, item.end_ms) not in allowed:
                raise AppError(
                    ErrorCode.PROVIDER_MALFORMED_OUTPUT,
                    "Suggestion references unavailable evidence.",
                )
        result = RecommendationReport(
            session_id=session_id,
            report_revision=revision,
            status="available",
            provider_mode="mock" if self.generator.mode == "mock" else "live",
            recommendations=draft.recommendations,
        )

        with self.state.lock:
            self.state.recommendation_runs[run_key] = result.model_copy(deep=True)
        return result

    def review(
        self, actor: AuthenticatedActor, session_id: str, review: RecommendationReview
    ) -> RecommendationReview:
        """Store feedback only for a current report revision; reject stale feedback."""
        report = self.metrics.report(actor, session_id)
        revision = hashlib.sha256(report.model_dump_json().encode()).hexdigest()
        if revision != review.report_revision:
            raise AppError(
                ErrorCode.DUPLICATE,
                "Report evidence changed; refresh before reviewing.",
            )
        generated = self.state.recommendation_runs.get(
            (session_id, actor.user_id, revision)
        )
        if generated is None or review.recommendation_index >= len(
            generated.recommendations
        ):
            raise AppError(
                ErrorCode.NOT_FOUND, "Recommendation was not generated for this report."
            )
        with self.state.lock:
            if len(self.state.reviews) >= self.state.maximum_records:
                raise AppError(
                    ErrorCode.PAYLOAD_TOO_LARGE, "Feedback capacity reached."
                )
            self.state.reviews[
                (session_id, actor.user_id, revision, review.recommendation_index)
            ] = review
        return review
