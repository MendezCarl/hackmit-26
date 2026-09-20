"""Course lifecycle: creation and ownership-scoped CRUD for professors."""

from __future__ import annotations

from uuid import uuid4

from app.auth.tokens import ROLE_PROFESSOR, AuthenticatedActor
from app.contracts.models import Course, CreateCourseRequest
from app.core.clock import utc_now_iso
from app.core.errors import AppError, ErrorCode
from app.storage.in_memory import InMemoryStore


class CourseService:
    """Ownership-scoped course CRUD."""

    def __init__(self, store: InMemoryStore) -> None:
        """Bind the service to shared storage.

        Args:
            store: Injected storage connections.
        """

        self._store = store

    def _require_owned_course(
        self, actor: AuthenticatedActor, course_id: str
    ) -> Course:
        """Return one course the actor owns.

        Args:
            actor: Authenticated professor.
            course_id: Course to retrieve.

        Returns:
            The stored course record.

        Raises:
            AppError: ``not_found`` for unknown courses and ``forbidden``
                for courses owned by someone else.
        """

        course = self._store.courses.get(course_id)
        if course is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "Course was not found.",
                details={"course_id": course_id},
            )
        if course.owner_id != actor.user_id:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Only the course owner can access this course.",
                details={"course_id": course_id},
            )
        return course

    def create_course(
        self, actor: AuthenticatedActor, request: CreateCourseRequest
    ) -> Course:
        """Create one course owned by the authenticated professor.

        Args:
            actor: Authenticated account; must hold the professor role.
            request: Validated course-creation payload.

        Returns:
            The created course record.

        Raises:
            AppError: ``forbidden`` for student accounts.
        """

        if actor.role != ROLE_PROFESSOR:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Only professors can create courses.",
            )
        course = Course(
            course_id=f"course_{uuid4().hex}",
            owner_id=actor.user_id,
            title=request.title,
            code=request.code,
            created_at=utc_now_iso(),
        )
        self._store.courses[course.course_id] = course
        return course

    def list_courses(self, actor: AuthenticatedActor) -> list[Course]:
        """List every course owned by the authenticated professor.

        Args:
            actor: Authenticated account.

        Returns:
            The account's owned courses, newest first.
        """

        return [
            course
            for course in self._store.courses.values()
            if course.owner_id == actor.user_id
        ]

    def get_course(self, actor: AuthenticatedActor, course_id: str) -> Course:
        """Return one owned course.

        Args:
            actor: Authenticated professor owning the course.
            course_id: Course to retrieve.

        Returns:
            The stored course record.
        """

        return self._require_owned_course(actor, course_id)

    def delete_course(self, actor: AuthenticatedActor, course_id: str) -> None:
        """Delete one owned course and its lecture records.

        Args:
            actor: Authenticated professor owning the course.
            course_id: Course to delete.
        """

        self._require_owned_course(actor, course_id)
        del self._store.courses[course_id]
        for lecture_id in [
            lecture.lecture_id
            for lecture in self._store.lectures.values()
            if lecture.course_id == course_id
        ]:
            del self._store.lectures[lecture_id]
