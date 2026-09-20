"""Recovery boundary checks shared by mock and live providers."""

import hashlib
import json
from threading import RLock

from app.auth.tokens import AuthenticatedActor
from app.contracts.learning import MAX_LECTURE_MS
from app.contracts.models import (
    ContextWindow,
    CreateRecoveryJobRequest,
    LectureSession,
    ModelMetadata,
    RecoveryCard,
    RecoveryJob,
)
from app.core.errors import AppError, ErrorCode
from app.learning.state import LearningState
from app.recovery.generator import RecoveryGenerator
from app.recovery.service import RecoveryService
from app.ws.publisher import ACTIVE_ACTOR

MAX_CONTEXT_CHARACTERS = 24_000
MAX_RECOVERY_INTERVAL_MS = 600_000


class ValidatedGenerator:
    """Validate injected provider cards before any storage, cache or notification."""

    def __init__(self, delegate: RecoveryGenerator) -> None:
        """Wrap one provider; preserve provider identity for cache separation."""
        self.delegate = delegate
        self.provider, self.model = delegate.provider, delegate.model
        self.prompt_version, self.output_schema_version = (
            delegate.prompt_version,
            delegate.output_schema_version,
        )

    def generate(
        self, session: LectureSession, window: ContextWindow
    ) -> tuple[RecoveryCard, ModelMetadata]:
        """Validate source scope and exact timestamps; never echo provider errors."""
        card, metadata = self.delegate.generate(session, window)
        card = RecoveryCard.model_validate(card.model_dump())
        sources = {chunk.chunk_id: chunk for chunk in window.chunks}
        valid = card.session_id == window.session_id and bool(card.source_timestamps)
        for reference in card.source_timestamps:
            chunk = sources.get(reference.chunk_id or "")
            valid = valid and chunk is not None
            if chunk is not None:
                valid = valid and (reference.start_ms, reference.end_ms) == (
                    chunk.start_ms,
                    chunk.end_ms,
                )
        if not valid:
            raise AppError(
                ErrorCode.PROVIDER_MALFORMED_OUTPUT,
                "The generated card could not be linked to its sources.",
            )
        return card, metadata


class PrivateRecoveryService(RecoveryService):
    """Extend the baseline with source ownership, consent and content-based caching."""

    def configure_privacy(self, state: LearningState) -> None:
        """Bind feature consent and create per-service job ownership and serialization."""
        self.learning_state = state
        self.job_owners: dict[str, str] = {}
        self.execution_lock = RLock()

    def create_job(
        self,
        actor: AuthenticatedActor,
        session_id: str,
        request: CreateRecoveryJobRequest,
    ) -> RecoveryJob:
        """Generate only within current membership, own events and external consent."""
        self._session_access.resolve_membership(actor, session_id)
        if actor.role != "student":
            raise AppError(
                ErrorCode.FORBIDDEN, "Personal recovery requires a student account."
            )
        if (
            request.end_ms > MAX_LECTURE_MS
            or request.end_ms - request.start_ms > MAX_RECOVERY_INTERVAL_MS
        ):
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                "Select no more than ten minutes within the lecture clock.",
            )
        own = {
            record.event.event_id
            for record in self._store.events.get(session_id, [])
            if record.submitted_by == actor.user_id
            and record.event.user_confirmed is not False
        }
        if not set(request.source_event_ids) <= own:
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                "Recovery source events must belong to the requesting student.",
            )
        with self.execution_lock, self.learning_state.lock:
            if (
                self._generator.provider != "mock"
                and (session_id, actor.user_id, self._generator.provider)
                not in self.learning_state.external_consent
            ):
                raise AppError(
                    ErrorCode.FORBIDDEN,
                    "External text processing requires separate provider consent.",
                )
            token = ACTIVE_ACTOR.set(actor.user_id)
            try:
                job = super().create_job(actor, session_id, request)
                self.job_owners[job.job_id] = actor.user_id
                return job
            finally:
                ACTIVE_ACTOR.reset(token)

    def _build_context_window(
        self, session_id: str, start_ms: int, end_ms: int
    ) -> ContextWindow:
        """Bound context by the known transcript horizon and total selected text size."""
        window = super()._build_context_window(session_id, start_ms, end_ms)
        horizon = max(
            (
                chunk.end_ms
                for chunk in self._store.transcript_chunks.get(session_id, [])
            ),
            default=end_ms,
        )
        window.effective_end_ms = min(window.effective_end_ms, horizon, MAX_LECTURE_MS)
        if (
            len(window.chunks) > 100
            or sum(len(c.text) for c in window.chunks) > MAX_CONTEXT_CHARACTERS
        ):
            raise AppError(
                ErrorCode.PAYLOAD_TOO_LARGE,
                "Selected context exceeds the recovery limit.",
            )
        return window

    def _build_cache_key(self, actor: AuthenticatedActor, window: ContextWindow) -> str:
        """Hash scoped context contents, so same-max-revision corrections invalidate reuse."""
        payload = {
            "scope": actor.user_id,
            "provider": self._generator.provider,
            "base": super()._build_cache_key(actor, window),
            "window": window.model_dump(mode="json"),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def get_job(
        self, actor: AuthenticatedActor, session_id: str, job_id: str
    ) -> RecoveryJob:
        """Return own jobs only; session membership alone never authorizes a job read."""
        job = super().get_job(actor, session_id, job_id)
        if self.job_owners.get(job_id) != actor.user_id:
            raise AppError(
                ErrorCode.FORBIDDEN, "Recovery jobs are private to their requester."
            )
        return job

    def get_card(
        self, actor: AuthenticatedActor, session_id: str, card_id: str
    ) -> RecoveryCard:
        """Read only one's own card, including when the requester owns the session."""
        self._session_access.resolve_membership(actor, session_id)
        record = self._store.recovery_cards.get(card_id)
        if record is None or record.card.session_id != session_id:
            raise AppError(ErrorCode.NOT_FOUND, "Recovery card was not found.")
        if record.owner_user_id != actor.user_id:
            raise AppError(
                ErrorCode.FORBIDDEN, "Recovery cards are private to their requester."
            )
        return record.card
