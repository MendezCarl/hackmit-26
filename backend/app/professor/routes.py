"""REST routes for anonymous professor summaries."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.auth.dependencies import get_current_actor
from app.auth.tokens import AuthenticatedActor
from app.contracts.models import ProfessorSummary
from app.professor.service import ProfessorService

router = APIRouter(prefix="/api/v1/sessions/{session_id}", tags=["professor"])


def get_professor_service(request: Request) -> ProfessorService:
    """Resolve the professor service from application state."""

    return request.app.state.professor_service


@router.get(
    "/professor/summary",
    response_model=ProfessorSummary,
    summary="Read the anonymous professor summary",
)
def read_professor_summary(
    session_id: str,
    response: Response,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[ProfessorService, Depends(get_professor_service)],
) -> ProfessorSummary:
    """Return an anonymous, aggregated summary for the course professor.

    Aggregates are suppressed below the configured minimum group size and
    never include student identifiers or individual confidence values.
    """

    response.headers["Cache-Control"] = "no-store"
    return service.build_summary(actor, session_id)
