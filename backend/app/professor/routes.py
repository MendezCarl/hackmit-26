"""Professor-only post-lecture aggregate endpoint."""

from fastapi import APIRouter

from app.professor.models import ProfessorSummary
from app.timeline.dependencies import AuthorizedSession, Services
from app.timeline.http import ERROR_RESPONSES, FeatureRoute

router = APIRouter(
    prefix="/api/v1/sessions/{session_id}",
    tags=["professor"],
    route_class=FeatureRoute,
    responses=ERROR_RESPONSES,
)


@router.get(
    "/professor-summary",
    response_model=ProfessorSummary,
    summary="Read an anonymous post-lecture summary",
    description="Professor bearer membership required. Only ended sessions and approved aggregation policies are supported. Fixed small-group buckets return null counts/ratios. No student identity or individual history appears. Returns 403/409/503 for denied role, active lecture, or missing policy.",
)
async def read_summary(
    grant: AuthorizedSession, services: Services
) -> ProfessorSummary:
    """Return threshold-protected anonymous metrics and optional recap suggestions."""
    return await services.professor.summarize(grant)
