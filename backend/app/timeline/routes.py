"""Bounded timeline and context endpoints backed by the same lecture clock."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.timeline.contracts import MAX_LECTURE_MS, Interval
from app.timeline.dependencies import AuthorizedSession, Services
from app.timeline.http import ERROR_RESPONSES, FeatureRoute
from app.timeline.service import ContextWindow, TimelinePage

router = APIRouter(
    prefix="/api/v1/sessions/{session_id}",
    tags=["timeline"],
    route_class=FeatureRoute,
    responses=ERROR_RESPONSES,
)
TimeQuery = Annotated[
    int,
    Query(
        ge=0, le=MAX_LECTURE_MS, description="Lecture-relative integer milliseconds."
    ),
]


@router.get(
    "/timeline",
    response_model=TimelinePage,
    summary="Read your synchronized timeline",
    description="Bearer session membership required. Returns final transcript and only the caller's signals. Queries are bounded to ten minutes; invalid ranges return 400.",
)
async def read_timeline(
    start_ms: TimeQuery, end_ms: TimeQuery, grant: AuthorizedSession, services: Services
) -> TimelinePage:
    """Return overlapping final chunks, private signals and possible missed windows."""
    return await services.timeline.read(
        grant, Interval(start_ms=start_ms, end_ms=end_ms)
    )


@router.get(
    "/transcript",
    response_model=ContextWindow,
    summary="Read a selected transcript context",
    description="Bearer session membership required. Returns final source chunks with original timestamps and revision. Padding is clamped to session bounds. Missing final text returns 409. No raw media is read or returned.",
)
async def read_context(
    start_ms: TimeQuery,
    end_ms: TimeQuery,
    grant: AuthorizedSession,
    services: Services,
    padding_ms: Annotated[int, Query(ge=0, le=30_000)] = 0,
) -> ContextWindow:
    """Return a bounded context window for recovery generation."""
    return await services.timeline.context(
        grant, Interval(start_ms=start_ms, end_ms=end_ms), padding_ms
    )
