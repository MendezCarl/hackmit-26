"""REST routes for lecture-record CRUD."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.auth.dependencies import get_current_actor
from app.auth.tokens import AuthenticatedActor
from app.contracts.models import CreateLectureRequest, Lecture
from app.lectures.service import LectureService

router = APIRouter(prefix="/api/v1/lectures", tags=["lectures"])


def get_lecture_service(request: Request) -> LectureService:
    """Resolve the lecture service from application state."""

    return request.app.state.lecture_service


@router.post(
    "",
    response_model=Lecture,
    status_code=status.HTTP_201_CREATED,
    summary="Create a lecture record",
)
def create_lecture(
    request_body: CreateLectureRequest,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[LectureService, Depends(get_lecture_service)],
) -> Lecture:
    """Create one lecture record inside a course the professor owns."""

    return service.create_lecture(actor, request_body)


@router.get(
    "",
    response_model=list[Lecture],
    summary="List lectures for one course",
)
def list_lectures(
    response: Response,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[LectureService, Depends(get_lecture_service)],
    course_id: Annotated[str, Query(description="Owning course identifier.")],
) -> list[Lecture]:
    """List lecture records for one course the professor owns."""

    response.headers["Cache-Control"] = "no-store"
    return service.list_lectures(actor, course_id)


@router.get(
    "/{lecture_id}",
    response_model=Lecture,
    summary="Read an owned lecture record",
)
def get_lecture(
    lecture_id: str,
    response: Response,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[LectureService, Depends(get_lecture_service)],
) -> Lecture:
    """Return one lecture record for its owner."""

    response.headers["Cache-Control"] = "no-store"
    return service.get_lecture(actor, lecture_id)


@router.delete(
    "/{lecture_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an owned lecture record",
)
def delete_lecture(
    lecture_id: str,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[LectureService, Depends(get_lecture_service)],
) -> None:
    """Delete one owned lecture record."""

    service.delete_lecture(actor, lecture_id)
