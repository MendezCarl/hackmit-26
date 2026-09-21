"""Reviewable teaching suggestions from released aggregates and lecture excerpts.

Student-derived signals reach the generator only as anonymous hotspot buckets.
Lecture transcript excerpts are added solely when the requesting professor has
granted external-text consent for the live provider; in mock mode the local
deterministic generator analyzes them without any network call.
"""

import hashlib
import logging
import re
from typing import Literal, Protocol

from app.auth.tokens import AuthenticatedActor
from app.contracts.learning import (
    GroundedFact,
    ProfessorMetrics,
    Recommendation,
    RecommendationDraft,
    RecommendationEvidenceScope,
    RecommendationReport,
    RecommendationReview,
)
from app.core.errors import AppError, ErrorCode
from app.learning.state import LearningState
from app.professor.excerpts import HotspotExcerpt, TranscriptExcerptReader
from app.professor.ports import MetricsReader
from app.recovery.evidence_matching import is_quote_grounded

logger = logging.getLogger(__name__)

LIVE_PROVIDER = "openai"
INTERVAL_ONLY_OBSERVATION = "Some students may have missed context during this interval."
INTERVAL_ONLY_ACTION = "Offer an optional recap and invite clarification."
CONSENT_REQUIRED_NOTE = (
    "Lecture transcript analysis is off. Allow AI review of your lecture transcript "
    "to see what was taught during each hotspot."
)
NO_TRANSCRIPT_NOTE = (
    "No lecture transcript overlaps these intervals, so suggestions cite timing only."
)
TOPIC_WORD_LIMIT = 8

# Recommendations must describe lecture delivery, never students' inner states.
FORBIDDEN_INFERENCE_PATTERN = re.compile(
    r"\b(attention|attentive|inattentive|distract\w*|bored?|boring|engag\w*|"
    r"disengag\w*|motivat\w*|lazy|confus\w*|understood|understand\w*|comprehen\w*|"
    r"disab\w*|adhd|anxi\w*|frustrat\w*|emotion\w*|feel\w*|caused|because)\b",
    re.IGNORECASE,
)


class RecommendationGenerator(Protocol):
    """Generate bounded recommendations from a privacy-filtered report."""

    mode: str

    def generate(
        self, report: ProfessorMetrics, excerpts: list[HotspotExcerpt]
    ) -> RecommendationDraft:
        """Return suggestions citing released intervals, or raise a safe provider error.

        Args:
            report: Privacy-filtered professor metrics.
            excerpts: Lecture excerpts per released hotspot; empty when the
                caller has not authorized lecture-content analysis.
        """
        ...


def summarize_excerpt_topic(excerpt: HotspotExcerpt) -> str | None:
    """Derive a short, quote-based topic label from the first excerpt sentence.

    Args:
        excerpt: Hotspot excerpt containing ordered lecture text.

    Returns:
        The first sentence truncated to ``TOPIC_WORD_LIMIT`` words, or ``None``
        when the excerpt has no text.
    """
    text = " ".join(chunk.text for chunk in excerpt.chunks).strip()
    if not text:
        return None
    sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    words = sentence.split()[:TOPIC_WORD_LIMIT]
    return " ".join(words).rstrip(".!?,;:") or None


class DeterministicRecommendations:
    """Synthetic suggestions for integration tests; no model or savings claim."""

    mode = "mock"

    def generate(
        self, report: ProfessorMetrics, excerpts: list[HotspotExcerpt]
    ) -> RecommendationDraft:
        """Turn released hotspots into compassionate, evidence-bound suggestions.

        With excerpts, each suggestion cites the interval's first chunk alias and
        an exact quote so the same grounding validation as live output applies.
        """
        by_interval = {(e.start_ms, e.end_ms): e for e in excerpts}
        recommendations = []
        for bucket in report.buckets:
            if bucket.status != "available" or not bucket.is_hotspot:
                continue
            excerpt = by_interval.get((bucket.start_ms, bucket.end_ms))
            if excerpt is None or not excerpt.chunks:
                recommendations.append(
                    Recommendation(
                        start_ms=bucket.start_ms,
                        end_ms=bucket.end_ms,
                        observation=INTERVAL_ONLY_OBSERVATION,
                        suggested_action=INTERVAL_ONLY_ACTION,
                    )
                )
                continue
            first = excerpt.chunks[0]
            quote = " ".join(first.text.split()[:12])
            recommendations.append(
                Recommendation(
                    start_ms=bucket.start_ms,
                    end_ms=bucket.end_ms,
                    topic=summarize_excerpt_topic(excerpt),
                    medium="explanation",
                    observation=(
                        "The lecture covered this topic while some students may have "
                        "missed context."
                    ),
                    suggested_action=(
                        "Offer an optional recap of this passage and invite questions."
                    ),
                    evidence=[
                        GroundedFact(
                            text="Transcript excerpt from this interval.",
                            chunk_id=first.alias,
                            evidence_quote=quote,
                        )
                    ],
                )
            )
        return RecommendationDraft(recommendations=recommendations[:5])


def _log_recommendation_rejection(**counts: str | int) -> None:
    """Emit a text-free diagnostic; never log quotes, topics or transcript text."""
    logger.warning(
        "recommendation_rejected %s",
        " ".join(f"{key}={value}" for key, value in counts.items()),
        extra=counts,
    )


def validate_recommendation_draft(
    draft: RecommendationDraft,
    report: ProfessorMetrics,
    excerpts: list[HotspotExcerpt],
) -> list[Recommendation]:
    """Keep only suggestions bound to released intervals and grounded excerpt quotes.

    Args:
        draft: Provider or deterministic output containing alias-cited evidence.
        report: Report whose released hotspots define the allowed intervals.
        excerpts: Excerpts supplied to the generator, keyed by interval.

    Returns:
        Validated recommendations with evidence aliases replaced by real chunk IDs.
        Suggestions containing forbidden student-state inference, unknown aliases,
        ungrounded quotes, or content claims without surviving evidence are dropped.

    Raises:
        AppError: If any suggestion references an interval that was not released.
    """
    allowed = {
        (b.start_ms, b.end_ms)
        for b in report.buckets
        if b.status == "available" and b.is_hotspot
    }
    by_interval = {(e.start_ms, e.end_ms): e for e in excerpts}
    kept: list[Recommendation] = []
    dropped_inference = dropped_evidence = 0
    for item in draft.recommendations:
        interval = (item.start_ms, item.end_ms)
        if interval not in allowed:
            raise AppError(
                ErrorCode.PROVIDER_MALFORMED_OUTPUT,
                "Suggestion references unavailable evidence.",
            )
        wording = " ".join(
            filter(None, (item.observation, item.suggested_action, item.topic))
        )
        if FORBIDDEN_INFERENCE_PATTERN.search(wording):
            dropped_inference += 1
            continue
        excerpt = by_interval.get(interval)
        aliases = excerpt.chunk_by_alias() if excerpt else {}
        grounded = [
            fact.model_copy(update={"chunk_id": aliases[fact.chunk_id].chunk_id})
            for fact in item.evidence
            if fact.chunk_id in aliases
            and is_quote_grounded(fact.evidence_quote, aliases[fact.chunk_id].text)
        ]
        has_content_claim = bool(item.topic or item.medium or item.evidence)
        if has_content_claim and not grounded:
            dropped_evidence += 1
            continue
        if not has_content_claim:
            kept.append(item)
            continue
        kept.append(item.model_copy(update={"evidence": grounded}))
    if dropped_inference or dropped_evidence:
        _log_recommendation_rejection(
            reason="draft_validation",
            total=len(draft.recommendations),
            kept=len(kept),
            dropped_inference=dropped_inference,
            dropped_evidence=dropped_evidence,
        )
    return kept


class RecommendationService:
    """Recheck current policy/consent for generation and professor feedback."""

    def __init__(
        self,
        metrics: MetricsReader,
        state: LearningState,
        generator: RecommendationGenerator,
        excerpts: TranscriptExcerptReader | None = None,
    ) -> None:
        """Inject report generation, feedback storage and the replaceable AI boundary.

        Args:
            metrics: Authorized, policy-filtered report reader.
            state: Bounded feature state holding consent, runs and reviews.
            generator: Mock or live recommendation generator.
            excerpts: Lecture excerpt reader; ``None`` disables transcript analysis.
        """
        self.metrics, self.state, self.generator = metrics, state, generator
        self.excerpts = excerpts

    def generate(self, actor: AuthenticatedActor, session_id: str) -> RecommendationReport:
        """Serialize consent/report snapshot and provider submission against revocation."""
        with self.state.lock:
            return self._generate(actor, session_id)

    def _has_live_consent(self, actor: AuthenticatedActor, session_id: str) -> bool:
        """Return whether this professor allowed bounded text to reach the live provider."""
        return (session_id, actor.user_id, LIVE_PROVIDER) in self.state.external_consent

    def _resolve_scope(
        self, actor: AuthenticatedActor, report: ProfessorMetrics
    ) -> tuple[RecommendationEvidenceScope, list[HotspotExcerpt], str | None]:
        """Decide whether lecture excerpts may be analyzed and build them if so.

        Live mode requires the professor's own external-text consent before any
        lecture content leaves the service; without it, suggestions stay local
        and interval-only. Mock mode never contacts a provider.
        """
        if self.excerpts is None:
            return "intervals_only", [], None
        if self.generator.mode == "live" and not self._has_live_consent(
            actor, report.session_id
        ):
            return "intervals_only", [], CONSENT_REQUIRED_NOTE
        excerpts = self.excerpts.excerpts(report)
        if not any(excerpt.chunks for excerpt in excerpts):
            return "intervals_only", [], NO_TRANSCRIPT_NOTE
        return "lecture_transcript", excerpts, None

    def _generate(self, actor: AuthenticatedActor, session_id: str) -> RecommendationReport:
        """Generate from safe aggregates plus consented lecture excerpts."""
        report = self.metrics.report(actor, session_id)
        revision = hashlib.sha256(report.model_dump_json().encode()).hexdigest()
        provider_mode: Literal["mock", "live"] = (
            "mock" if self.generator.mode == "mock" else "live"
        )
        if report.status != "available":
            return RecommendationReport(
                session_id=session_id,
                report_revision=revision,
                status="insufficient_evidence",
                provider_mode=provider_mode,
                recommendations=[],
            )
        scope, excerpts, note = self._resolve_scope(actor, report)
        run_key = (session_id, actor.user_id, revision)
        cached = self.state.recommendation_runs.get(run_key)
        if cached is not None and (
            cached.evidence_scope == scope or scope == "intervals_only"
        ):
            result = cached.model_copy(deep=True)
            result.reviews = [
                review.model_copy(deep=True)
                for key, review in self.state.reviews.items()
                if key[:3] == run_key
            ]
            return result
        if (
            cached is None
            and len(self.state.recommendation_runs) >= self.state.maximum_records
        ):
            raise AppError(ErrorCode.PAYLOAD_TOO_LARGE, "Recommendation capacity reached.")
        if scope == "intervals_only" and self.generator.mode == "live":
            # Without consent nothing leaves the service, so suggestions are local.
            draft = DeterministicRecommendations().generate(report, [])
            provider_mode = "mock"
        else:
            draft = self.generator.generate(report, excerpts)
        recommendations = validate_recommendation_draft(draft, report, excerpts)
        result = RecommendationReport(
            session_id=session_id,
            report_revision=revision,
            status="available",
            provider_mode=provider_mode,
            evidence_scope=scope,
            evidence_note=note,
            recommendations=recommendations,
        )
        # A regenerated run replaces earlier suggestions, so their reviews no longer apply.
        self.state.reviews = {
            key: review for key, review in self.state.reviews.items() if key[:3] != run_key
        }
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
                raise AppError(ErrorCode.PAYLOAD_TOO_LARGE, "Feedback capacity reached.")
            self.state.reviews[
                (session_id, actor.user_id, revision, review.recommendation_index)
            ] = review
        return review
