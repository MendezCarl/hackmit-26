"""Student course enrollment and discovery of live lectures to join.

Enrollment is the persistent link between a student and a course. It lets the
desktop app detect that an enrolled course has an active lecture session and
offer a one-click join instead of requiring a fresh join code each lecture.
Enrollment stores only the student id and course id; no media or signals.
"""

from __future__ import annotations

from uuid import uuid4

from app.auth.tokens import ROLE_STUDENT, AuthenticatedActor
from app.contracts.models import (
    AvailableLectureSession,
    Course,
    CourseEnrollment,
    EnrollCourseRequest,
    SessionMatchSource,
    SessionStatus,
    UpdateEnrollmentRequest,
)
from app.core.clock import utc_now_iso
from app.core.errors import AppError, ErrorCode
from app.sessions.join_codes import normalize_join_code
from app.storage.in_memory import InMemoryStore


class EnrollmentService:
    """Student-scoped course enrollment and active-session matching."""

    def __init__(self, store: InMemoryStore) -> None:
        """Bind the service to shared storage.

        Args:
            store: Injected storage connections.
        """

        self._store = store

    def _find_enrollment(
        self, actor: AuthenticatedActor, course_id: str
    ) -> CourseEnrollment | None:
        """Return the actor's enrollment in one course, if any."""

        for enrollment in self._store.enrollments.values():
            if enrollment.user_id == actor.user_id and enrollment.course_id == course_id:
                return enrollment
        return None

    def _require_owned_enrollment(
        self, actor: AuthenticatedActor, enrollment_id: str
    ) -> CourseEnrollment:
        """Return one enrollment belonging to the actor.

        Raises:
            AppError: ``not_found`` when the enrollment does not exist or
                belongs to another student; existence is not leaked.
        """

        enrollment = self._store.enrollments.get(enrollment_id)
        if enrollment is None or enrollment.user_id != actor.user_id:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "Enrollment was not found.",
                details={"enrollment_id": enrollment_id},
            )
        return enrollment

    def _create_enrollment(
        self, actor: AuthenticatedActor, course: Course
    ) -> CourseEnrollment:
        """Store a new enrollment for the actor in ``course``."""

        enrollment = CourseEnrollment(
            enrollment_id=f"enrollment_{uuid4().hex}",
            course_id=course.course_id,
            user_id=actor.user_id,
            course_title=course.title,
            course_code=course.code,
            is_auto_join_enabled=False,
            enrolled_at=utc_now_iso(),
        )
        self._store.enrollments[enrollment.enrollment_id] = enrollment
        return enrollment

    def enroll_by_course_code(
        self, actor: AuthenticatedActor, request: EnrollCourseRequest
    ) -> CourseEnrollment:
        """Enroll the authenticated student in the course matching a code.

        Enrolling twice in the same course is idempotent and returns the
        existing record.

        Args:
            actor: Authenticated account; must hold the student role.
            request: Validated enrollment payload.

        Returns:
            The stored enrollment record.

        Raises:
            AppError: ``forbidden`` for non-student accounts, ``not_found``
                when no course has the code, and ``duplicate`` when several
                professors use the same code so the student must join one
                lecture by join code instead.
        """

        if actor.role != ROLE_STUDENT:
            raise AppError(ErrorCode.FORBIDDEN, "Only students can enroll in courses.")
        normalized_code = normalize_join_code(request.course_code)
        matches = [
            course
            for course in self._store.courses.values()
            if normalize_join_code(course.code) == normalized_code
        ]
        if not matches:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "No course uses that code.",
                details={"course_code": normalized_code},
            )
        if len(matches) > 1:
            raise AppError(
                ErrorCode.DUPLICATE,
                "Several courses use that code; join one of its lectures with a "
                "lecture join code to enroll instead.",
                details={"course_code": normalized_code},
            )
        course = matches[0]
        return self._find_enrollment(actor, course.course_id) or self._create_enrollment(
            actor, course
        )

    def enroll_from_session(
        self, actor: AuthenticatedActor, session_id: str
    ) -> CourseEnrollment | None:
        """Enroll a student in the course of a session they just joined.

        Joining once by join code is enough for Bloom to detect that course's
        future lectures. Non-students and sessions whose course record no
        longer exists are ignored so joining never fails because of enrollment.

        Args:
            actor: Authenticated user who registered as a participant.
            session_id: Session that was joined.

        Returns:
            The existing or newly created enrollment, or ``None`` when no
            enrollment applies.
        """

        if actor.role != ROLE_STUDENT:
            return None
        session = self._store.sessions.get(session_id)
        if session is None:
            return None
        course = self._store.courses.get(session.course_id)
        if course is None:
            return None
        return self._find_enrollment(actor, course.course_id) or self._create_enrollment(
            actor, course
        )

    def list_enrollments(self, actor: AuthenticatedActor) -> list[CourseEnrollment]:
        """List the authenticated student's enrollments, newest first.

        Args:
            actor: Authenticated account.

        Returns:
            Enrollments owned by the actor ordered by ``enrolled_at`` descending.
        """

        return sorted(
            (
                enrollment
                for enrollment in self._store.enrollments.values()
                if enrollment.user_id == actor.user_id
            ),
            key=lambda enrollment: enrollment.enrolled_at,
            reverse=True,
        )

    def update_enrollment(
        self,
        actor: AuthenticatedActor,
        enrollment_id: str,
        request: UpdateEnrollmentRequest,
    ) -> CourseEnrollment:
        """Change the auto-join preference of one owned enrollment.

        Args:
            actor: Authenticated student owning the enrollment.
            enrollment_id: Enrollment to update.
            request: Validated preference payload.

        Returns:
            The updated enrollment record.

        Raises:
            AppError: ``not_found`` for unknown or foreign enrollments.
        """

        enrollment = self._require_owned_enrollment(actor, enrollment_id)
        updated = enrollment.model_copy(
            update={"is_auto_join_enabled": request.is_auto_join_enabled}
        )
        self._store.enrollments[enrollment_id] = updated
        return updated

    def delete_enrollment(self, actor: AuthenticatedActor, enrollment_id: str) -> None:
        """Remove one owned enrollment so its lectures are no longer detected.

        Args:
            actor: Authenticated student owning the enrollment.
            enrollment_id: Enrollment to delete.

        Raises:
            AppError: ``not_found`` for unknown or foreign enrollments.
        """

        self._require_owned_enrollment(actor, enrollment_id)
        del self._store.enrollments[enrollment_id]

    def list_available_sessions(
        self,
        actor: AuthenticatedActor,
        zoom_meeting_id: str | None = None,
    ) -> list[AvailableLectureSession]:
        """List active sessions the student can join without a join code.

        A session matches when its course is one of the actor's enrollments,
        or when ``zoom_meeting_id`` equals the session's Zoom meeting id (the
        student is visibly in that meeting, so the code is redundant).
        Sessions owned by the actor are excluded. Only the session's own
        contract fields are returned; no other participants are exposed.

        Args:
            actor: Authenticated account.
            zoom_meeting_id: Optional Zoom meeting id detected on the device.

        Returns:
            Matches ordered newest first by session start time.
        """

        enrollments_by_course = {
            enrollment.course_id: enrollment
            for enrollment in self._store.enrollments.values()
            if enrollment.user_id == actor.user_id
        }
        normalized_meeting_id = (zoom_meeting_id or "").strip() or None
        matches: list[AvailableLectureSession] = []
        for session in self._store.sessions.values():
            if session.status != SessionStatus.ACTIVE or session.owner_id == actor.user_id:
                continue
            enrollment = enrollments_by_course.get(session.course_id)
            is_zoom_match = (
                normalized_meeting_id is not None
                and session.zoom_meeting_id == normalized_meeting_id
            )
            if enrollment is None and not is_zoom_match:
                continue
            participants = self._store.participants.get(session.session_id, {})
            matches.append(
                AvailableLectureSession(
                    session=session,
                    matched_by=(
                        SessionMatchSource.ZOOM_MEETING
                        if enrollment is None
                        else SessionMatchSource.ENROLLMENT
                    ),
                    is_joined=actor.user_id in participants,
                    is_auto_join_enabled=bool(
                        enrollment is not None and enrollment.is_auto_join_enabled
                    ),
                )
            )
        matches.sort(key=lambda match: match.session.started_at, reverse=True)
        return matches
