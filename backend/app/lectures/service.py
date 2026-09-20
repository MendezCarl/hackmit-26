"""Lecture-record lifecycle scoped to professor-owned courses.

A ``lecture_id`` identifies the lecture record; a ``session_id`` identifies
one running occurrence created through the sessions feature.
"""

from __future__ import annotations

from uuid import uuid4

from app.auth.tokens import ROLE_PROFESSOR, AuthenticatedActor
from app.contracts.models import CreateLectureRequest, Lecture
from app.core.clock import utc_now_iso
from app.core.errors import AppError, ErrorCode
from app.storage.in_memory import InMemoryStore


class LectureService:
    """Ownership-scoped lecture-record CRUD."""

    def __init__(self, store: InMemoryStore) -> None:
        """Bind the service to shared storage.

        Args:
            store: Injected storage connections.
        """

        self._store = store

    def _require_owned_lecture(
        self, actor: AuthenticatedActor, lecture_id: str
    ) -> Lecture:
        """Return one lecture the actor owns.

        Args:
            actor: Authenticated professor.
            lecture_id: Lecture record to retrieve.

        Returns:
            The stored lecture record.

        Raises:
            AppError: ``not_found`` for unknown lectures and ``forbidden``
                for lectures owned by someone else.
        """

        lecture = self._store.lectures.get(lecture_id)
        if lecture is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "Lecture was not found.",
                details={"lecture_id": lecture_id},
            )
        if lecture.owner_id != actor.user_id:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Only the lecture owner can access this lecture.",
                details={"lecture_id": lecture_id},
            )
        return lecture

    def create_lecture(
        self, actor: AuthenticatedActor, request: CreateLectureRequest
    ) -> Lecture:
        """Create one lecture record inside a course the actor owns.

        Args:
            actor: Authenticated professor owning the course.
            request: Validated lecture-creation payload.

        Returns:
            The created lecture record.

        Raises:
            AppError: ``forbidden`` for students or foreign courses and
                ``not_found`` for unknown courses.
        """

        if actor.role != ROLE_PROFESSOR:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Only professors can create lectures.",
            )
        course = self._store.courses.get(request.course_id)
        if course is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "Course was not found.",
                details={"course_id": request.course_id},
            )
        if course.owner_id != actor.user_id:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Only the course owner can create lectures in it.",
                details={"course_id": request.course_id},
            )
        lecture = Lecture(
            lecture_id=f"lecture_{uuid4().hex}",
            course_id=request.course_id,
            owner_id=actor.user_id,
            title=request.title,
            created_at=utc_now_iso(),
        )
        self._store.lectures[lecture.lecture_id] = lecture
        return lecture

    def list_lectures(
        self, actor: AuthenticatedActor, course_id: str
    ) -> list[Lecture]:
        """List lecture records for one owned course.

        Args:
            actor: Authenticated professor owning the course.
            course_id: Course whose lectures are listed.

        Returns:
            The course's lecture records.
        """

        self._require_owned_course(actor, course_id)
        return [
            lecture
            for lecture in self._store.lectures.values()
            if lecture.course_id == course_id
        ]

    def get_lecture(
        self, actor: AuthenticatedActor, lecture_id: str
    ) -> Lecture:
        """Return one owned lecture record.

        Args:
            actor: Authenticated professor owning the lecture.
            lecture_id: Lecture record to retrieve.

        Returns:
            The stored lecture record.
        """

        return self._require_owned_lecture(actor, lecture_id)

    def delete_lecture(
        self, actor: AuthenticatedActor, lecture_id: str
    ) -> None:
        """Delete one owned lecture record.

        Args:
            actor: Authenticated professor owning the lecture.
            lecture_id: Lecture record to delete.
        """

        self._require_owned_lecture(actor, lecture_id)
        del self._store.lectures[lecture_id]

    def _require_owned_course(
        self, actor: AuthenticatedActor, course_id: str
    ) -> None:
        """Ensure the actor owns the referenced course.

        Args:
            actor: Authenticated professor.
            course_id: Course to check.

        Raises:
            AppError: ``not_found`` or ``forbidden`` via the same rules as
                course reads.
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
                "Only the course owner can list its lectures.",
                details={"course_id": course_id},
            )
