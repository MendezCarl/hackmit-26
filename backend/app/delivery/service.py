"""Authorized ingestion of local derived delivery events."""

from app.auth.access import SessionAccess
from app.auth.tokens import AuthenticatedActor
from app.contracts.learning import BatchReceipt, DeliveryBatch, DeliveryEvent
from app.contracts.models import SessionStatus
from app.core.errors import AppError, ErrorCode
from app.learning.state import LearningState
from app.storage.in_memory import InMemoryStore


class DeliveryService:
    """Persist bounded derived events from the course professor's local worker."""

    def __init__(
        self, store: InMemoryStore, state: LearningState, access: SessionAccess
    ) -> None:
        """Inject storage and host membership; no media or provider I/O."""
        self.store, self.state, self.access = store, state, access

    def ingest(
        self, actor: AuthenticatedActor, session_id: str, batch: DeliveryBatch
    ) -> BatchReceipt:
        """Atomically ingest professor-authorized observations or reject the whole batch."""
        self.access.resolve_membership(actor, session_id)
        session = self.store.sessions[session_id]
        if actor.role != "professor" or actor.course_id != session.course_id:
            raise AppError(
                ErrorCode.FORBIDDEN, "Delivery ingestion requires the course professor."
            )
        if session.status == SessionStatus.ENDED:
            raise AppError(ErrorCode.VALIDATION_FAILED, "Delivery ingestion has ended.")
        with self.state.lock:
            pending: dict[tuple[str, str], DeliveryEvent] = {}
            duplicates = 0
            for event in batch.events:
                key = (session_id, event.event_id)
                previous = pending.get(key, self.state.delivery.get(key))
                if previous is not None:
                    if previous != event:
                        raise AppError(
                            ErrorCode.DUPLICATE,
                            "Delivery identifier conflicts with an existing event.",
                        )
                    duplicates += 1
                else:
                    pending[key] = event.model_copy(deep=True)
            if len(self.state.delivery) + len(pending) > self.state.maximum_records:
                raise AppError(
                    ErrorCode.PAYLOAD_TOO_LARGE, "Delivery capacity reached."
                )
            self.state.delivery.update(pending)
        return BatchReceipt(accepted=len(pending), duplicates=duplicates)
