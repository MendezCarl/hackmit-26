"""REST routes for student course enrollment."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.auth.dependencies import get_current_actor
from app.auth.tokens import AuthenticatedActor
from app.contracts.models import (
    CourseEnrollment,
    EnrollCourseRequest,
    UpdateEnrollmentRequest,
)
from app.enrollments.service import EnrollmentService

router = APIRouter(prefix="/api/v1/enrollments", tags=["enrollments"])


def get_enrollment_service(request: Request) -> EnrollmentService:
    """Resolve the enrollment service from application state."""

    return request.app.state.enrollment_service


@router.post(
    "",
    response_model=CourseEnrollment,
    status_code=status.HTTP_201_CREATED,
    summary="Enroll in a course by course code",
)
def enroll_in_course(
    request_body: EnrollCourseRequest,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[EnrollmentService, Depends(get_enrollment_service)],
) -> CourseEnrollment:
    """Enroll the authenticated student in the course using the shared code.

    Enrollment lets the desktop app detect the course's future live lectures
    and offer a one-click join. Students only; re-enrolling is idempotent.
    Returns ``not_found`` for unknown codes and ``duplicate`` when the code is
    ambiguous across professors.
    """

    return service.enroll_by_course_code(actor, request_body)


@router.get(
    "",
    response_model=list[CourseEnrollment],
    summary="List my enrollments",
)
def list_enrollments(
    response: Response,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[EnrollmentService, Depends(get_enrollment_service)],
) -> list[CourseEnrollment]:
    """List the authenticated user's course enrollments, newest first."""

    response.headers["Cache-Control"] = "no-store"
    return service.list_enrollments(actor)


@router.patch(
    "/{enrollment_id}",
    response_model=CourseEnrollment,
    summary="Update an enrollment's auto-join preference",
)
def update_enrollment(
    enrollment_id: str,
    request_body: UpdateEnrollmentRequest,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[EnrollmentService, Depends(get_enrollment_service)],
) -> CourseEnrollment:
    """Toggle whether live lectures for the course join without a prompt.

    Auto-join is off by default because joining also opts the student into
    anonymous aggregation; the student must enable it explicitly.
    """

    return service.update_enrollment(actor, enrollment_id, request_body)


@router.delete(
    "/{enrollment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Leave a course",
)
def delete_enrollment(
    enrollment_id: str,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    service: Annotated[EnrollmentService, Depends(get_enrollment_service)],
) -> None:
    """Remove one owned enrollment so its lectures are no longer detected."""

    service.delete_enrollment(actor, enrollment_id)
