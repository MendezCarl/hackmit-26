"""REST routes for course CRUD."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.auth.dependencies import get_current_actor
from app.auth.tokens import AuthenticatedActor
from app.contracts.models import Course, CreateCourseRequest
from app.courses.service import CourseService

router = APIRouter(prefix="/api/v1/courses", tags=["courses"])


def get_course_service(request: Request) -> CourseService:
    """Resolve the course service from application state."""

    return request.app.state.course_service


@router.post(
    "",
    response_model=Course,
    status_code=status.HTTP_201_CREATED,
    summary="Create a course",
)
def create_course(
    request_body: CreateCourseRequest,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[CourseService, Depends(get_course_service)],
) -> Course:
    """Create one course owned by the authenticated professor."""

    return service.create_course(actor, request_body)


@router.get(
    "",
    response_model=list[Course],
    summary="List owned courses",
)
def list_courses(
    response: Response,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[CourseService, Depends(get_course_service)],
) -> list[Course]:
    """List every course the authenticated professor owns."""

    response.headers["Cache-Control"] = "no-store"
    return service.list_courses(actor)


@router.get(
    "/{course_id}",
    response_model=Course,
    summary="Read an owned course",
)
def get_course(
    course_id: str,
    response: Response,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[CourseService, Depends(get_course_service)],
) -> Course:
    """Return one course for its owner."""

    response.headers["Cache-Control"] = "no-store"
    return service.get_course(actor, course_id)


@router.delete(
    "/{course_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an owned course",
)
def delete_course(
    course_id: str,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[CourseService, Depends(get_course_service)],
) -> None:
    """Delete one owned course and its lecture records."""

    service.delete_course(actor, course_id)
