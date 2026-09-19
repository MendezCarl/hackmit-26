"""Atomic, bounded session documents with interchangeable memory and Mongo storage."""

from collections.abc import Callable
from typing import Any, Protocol

from pydantic import Field

from app.dropbox.models import FolderLink
from app.signals.models import StoredSignal
from app.timeline.contracts import FeatureError, Identifier, StrictModel
from app.transcript.models import TranscriptChunk

MAX_SESSION_SIGNALS = 5000
MAX_SESSION_CHUNKS = 1000
MAX_WRITE_ATTEMPTS = 5


class SessionState(StrictModel):
    """Private feature document, bounded to stay below Mongo's document-size limit."""

    session_id: Identifier
    revision: int = 0
    transcript_revision: int = 0
    signals: list[StoredSignal] = Field(default_factory=list)
    chunks: list[TranscriptChunk] = Field(default_factory=list)
    folder_links: list[FolderLink] = Field(default_factory=list)


class SessionRepository(Protocol):
    """Compare-and-swap storage keeps concurrent REST/WS batches atomic."""

    async def load(self, session_id: str) -> SessionState:
        """Return a detached validated snapshot, or an empty initial document."""
        ...

    async def replace(self, state: SessionState, expected_revision: int) -> bool:
        """Commit iff revision matches; return False on a concurrent change."""
        ...

    async def delete(self, session_id: str) -> None:
        """Delete private feature content when the host authorizes session deletion."""
        ...


class MemorySessionRepository:
    """Single-process test/demo repository, with copy isolation and no persistence."""

    def __init__(self) -> None:
        """Create an empty per-application store, never shared as a global."""
        self._sessions: dict[str, SessionState] = {}

    async def load(self, session_id: str) -> SessionState:
        """Return an isolated snapshot for a session."""
        state = self._sessions.get(session_id, SessionState(session_id=session_id))
        return state.model_copy(deep=True)

    async def replace(self, state: SessionState, expected_revision: int) -> bool:
        """Atomically compare and replace within the single event loop."""
        current = self._sessions.get(state.session_id)
        if (current.revision if current else 0) != expected_revision:
            return False
        self._sessions[state.session_id] = state.model_copy(deep=True)
        return True

    async def delete(self, session_id: str) -> None:
        """Remove a session's derived content."""
        self._sessions.pop(session_id, None)


class MongoSessionRepository:
    """Motor collection adapter; connection lifecycle belongs to Person A."""

    def __init__(self, collection: Any) -> None:
        """Accept an injected Motor collection; all documents are validated on read."""
        self._collection = collection

    async def load(self, session_id: str) -> SessionState:
        """Fetch a typed document; database exceptions are handled by the host."""
        document = await self._collection.find_one({"_id": session_id})
        if document is None:
            return SessionState(session_id=session_id)
        document.pop("_id", None)
        return SessionState.model_validate(document)

    async def replace(self, state: SessionState, expected_revision: int) -> bool:
        """Use unique _id plus revision matching to prevent lost updates."""
        from pymongo.errors import DuplicateKeyError

        document = state.model_dump(mode="json")
        document["_id"] = state.session_id
        try:
            result = await self._collection.replace_one(
                {"_id": state.session_id, "revision": expected_revision},
                document,
                upsert=expected_revision == 0,
            )
        except DuplicateKeyError:
            return False
        return bool(result.matched_count or result.upserted_id is not None)

    async def delete(self, session_id: str) -> None:
        """Delete the authorized session's entire derived-data document."""
        await self._collection.delete_one({"_id": session_id})


async def mutate_session[Result](
    repository: SessionRepository,
    session_id: str,
    change: Callable[[SessionState], tuple[Result, bool]],
) -> Result:
    """Apply a pure mutation atomically; retry conflicts or raise a safe 409.

    Args:
        repository: Injected atomic storage.
        session_id: Already-authorized session identifier.
        change: Pure mutation returning a typed result and whether state changed.

    Returns:
        The mutation's result after commit, or an idempotent no-op result.

    Raises:
        FeatureError: If repeated concurrent writes exhaust the bounded retry limit.
    """
    for _ in range(MAX_WRITE_ATTEMPTS):
        state = await repository.load(session_id)
        revision = state.revision
        result, has_changed = change(state)
        if not has_changed:
            return result
        state.revision += 1
        if await repository.replace(state, revision):
            return result
    raise FeatureError("write_conflict", "Please retry the concurrent update.", 409)
