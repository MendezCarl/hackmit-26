"""Typed feature routes; authentication and contract rules follow ADR 0002."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.auth.dependencies import get_current_actor
from app.auth.tokens import AuthenticatedActor
from app.contracts.learning import (
    RecommendationReport,
    RecommendationReview,
)
from app.contracts.models import ErrorResponse

Actor = Annotated[AuthenticatedActor, Depends(get_current_actor)]
router = APIRouter(
    prefix="/api/v1/sessions/{session_id}",
    tags=["learning"],
    responses={
        code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 413, 422, 502)
    },
)


@router.post(
    "/professor-recommendations",
    response_model=RecommendationReport,
    description="Course-professor JWT and released evidence required; generated only on request, never automatically. Recommendations cite approved aggregate intervals; raw and individual signals never reach the provider. Bounded lecture-transcript excerpts for hotspot intervals are analyzed when `evidence_scope` is `lecture_transcript`: in mock mode locally, in live mode only after this professor's external-text consent for the provider. Without that consent the response stays `intervals_only` with an `evidence_note` and no text leaves the service. Evidence quotes are verified against the cited chunk before release.",
)
def generate_recommendations(
    session_id: str, actor: Actor, request: Request, response: Response
) -> RecommendationReport:
    """Generate bounded suggestions from the current report and consented excerpts."""
    response.headers["Cache-Control"] = "no-store"
    return request.app.state.recommendation_service.generate(actor, session_id)


@router.put(
    "/professor-recommendations/reviews",
    response_model=RecommendationReview,
    description="Course-professor JWT required. Store reviewed/dismissed/resolved state against a current report revision. Stale evidence returns a conflict.",
)
def review_recommendation(
    session_id: str, body: RecommendationReview, actor: Actor, request: Request
) -> RecommendationReview:
    """Save professor feedback without exposing any student requesters."""
    return request.app.state.recommendation_service.review(actor, session_id, body)
