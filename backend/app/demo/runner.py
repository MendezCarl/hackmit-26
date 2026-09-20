"""Deterministic demo orchestration covering the first-backend-MVP test.

The runner composes the real services, routing, validation, and
authorization boundaries; only external providers and storage are faked.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.auth.tokens import AuthenticatedActor
from app.contracts.models import (
    CreateRecoveryJobRequest,
    CreateSessionRequest,
    IngestEventsRequest,
    IngestTranscriptRequest,
    LectureSession,
    ProfessorSummary,
    RecoveryCard,
    RecoveryJob,
    SessionMode,
    SignalEvent,
)
from app.demo.synthetic_lecture import (
    DEMO_COURSE_ID,
    DEMO_LECTURE_ID,
    DEMO_SESSION_TITLE,
    MISSED_WINDOW_END_MS,
    MISSED_WINDOW_START_MS,
    PARTICIPANT_COUNT,
    build_synthetic_missed_event,
    build_synthetic_transcript_chunks,
)
from app.professor.service import ProfessorService
from app.recovery.service import RecoveryService
from app.sessions.service import SessionService
from app.signals.service import SignalService
from app.transcript.service import TranscriptService


class DemoRunResult(BaseModel):
    """Summary of one fully synthetic demo run."""

    session: LectureSession = Field(description="Created synthetic lecture session.")
    transcript_chunk_ids: list[str] = Field(
        description="Ingested synthetic transcript chunk ids."
    )
    submitted_event_ids: list[str] = Field(
        description="Synthetic missed-window events submitted by participants."
    )
    recovery_job: RecoveryJob = Field(description="First recovery job result.")
    recovery_card: RecoveryCard = Field(description="Generated recovery card.")
    cached_recovery_job: RecoveryJob = Field(
        description="Repeated recovery job demonstrating cache reuse."
    )
    professor_summary: ProfessorSummary = Field(
        description="Anonymous professor summary for the run."
    )
    professor_summary_suppressed: ProfessorSummary = Field(
        description="Summary demonstrating small-group suppression."
    )


class DemoRunner:
    """Orchestrates the end-to-end synthetic demo through real services."""

    def __init__(
        self,
        session_service: SessionService,
        signal_service: SignalService,
        transcript_service: TranscriptService,
        recovery_service: RecoveryService,
        professor_service: ProfessorService,
    ) -> None:
        """Bind the runner to the composed feature services.

        Args:
            session_service: Session lifecycle service.
            signal_service: Signal ingestion service.
            transcript_service: Transcript ingestion service.
            recovery_service: Recovery orchestration service.
            professor_service: Anonymous summary service.
        """

        self._session_service = session_service
        self._signal_service = signal_service
        self._transcript_service = transcript_service
        self._recovery_service = recovery_service
        self._professor_service = professor_service

    def run(self) -> DemoRunResult:
        """Execute the full synthetic demo run.

        Returns:
            The IDs and artifacts produced by each acceptance-flow step.
        """

        student = AuthenticatedActor(user_id="demo-student-1", role="student")
        professor = AuthenticatedActor(
            user_id="demo-professor-1",
            role="professor",
            course_id=DEMO_COURSE_ID,
        )

        session = self._session_service.create_session(
            student,
            CreateSessionRequest(
                lecture_id=DEMO_LECTURE_ID,
                course_id=DEMO_COURSE_ID,
                title=DEMO_SESSION_TITLE,
                mode=SessionMode.IN_PERSON,
            ),
        )
        session_id = session.session_id

        # Synthetic participants opt in; the primary student requests recovery.
        for index in range(1, PARTICIPANT_COUNT + 1):
            participant = AuthenticatedActor(
                user_id=f"demo-student-{index}", role="student"
            )
            self._signal_service.register_participant(participant, session_id)

        transcript = self._transcript_service.ingest_batch(
            student,
            session_id,
            IngestTranscriptRequest(
                lecture_id=DEMO_LECTURE_ID,
                chunks=build_synthetic_transcript_chunks(session_id),
            ),
        )

        submitted_event_ids: list[str] = []
        for index in range(1, PARTICIPANT_COUNT + 1):
            participant = AuthenticatedActor(
                user_id=f"demo-student-{index}", role="student"
            )
            events: list[SignalEvent] = [
                build_synthetic_missed_event(session_id, f"demo-event-{index:03d}")
            ]
            batch = self._signal_service.ingest_batch(
                participant,
                session_id,
                IngestEventsRequest(lecture_id=DEMO_LECTURE_ID, events=events),
            )
            submitted_event_ids.extend(batch.accepted_event_ids)

        recovery_request = CreateRecoveryJobRequest(
            start_ms=MISSED_WINDOW_START_MS,
            end_ms=MISSED_WINDOW_END_MS,
            source_event_ids=["demo-event-001"],
        )
        recovery_job = self._recovery_service.create_job(
            student, session_id, recovery_request
        )
        if recovery_job.card_id is None:
            raise RuntimeError("Demo recovery job did not produce a card.")
        recovery_card = self._recovery_service.get_card(
            student, session_id, recovery_job.card_id
        )
        cached_recovery_job = self._recovery_service.create_job(
            student, session_id, recovery_request
        )

        professor_summary = self._professor_service.build_summary(
            professor, session_id
        )

        # Demonstrate suppression with a second, too-small synthetic session.
        small_session = self._session_service.create_session(
            student,
            CreateSessionRequest(
                lecture_id="demo-lecture-0002",
                course_id=DEMO_COURSE_ID,
                title="Synthetic Lecture: Small Group",
                mode=SessionMode.IN_PERSON,
            ),
        )
        small_student = AuthenticatedActor(
            user_id="demo-student-1", role="student"
        )
        self._signal_service.register_participant(
            small_student, small_session.session_id
        )
        small_events = [
            build_synthetic_missed_event(small_session.session_id, "demo-small-001")
        ]
        self._signal_service.ingest_batch(
            small_student,
            small_session.session_id,
            IngestEventsRequest(lecture_id="demo-lecture-0002", events=small_events),
        )
        suppressed_summary = self._professor_service.build_summary(
            professor, small_session.session_id
        )

        return DemoRunResult(
            session=session,
            transcript_chunk_ids=transcript.accepted_chunk_ids,
            submitted_event_ids=submitted_event_ids,
            recovery_job=recovery_job,
            recovery_card=recovery_card,
            cached_recovery_job=cached_recovery_job,
            professor_summary=professor_summary,
            professor_summary_suppressed=suppressed_summary,
        )