"""Typed event publishing to explicitly authorized WebSocket subscribers.

``EventPublisher`` is the frozen shared interface both workstreams consume.
Delivery is per-session and per-audience; no envelope reaches a client that
did not resolve membership for that session.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Protocol
from uuid import uuid4

from app.contracts.models import EventEnvelope, SCHEMA_VERSION
from app.core.clock import utc_now_iso

SESSION_AUDIENCE = "session"
MAX_QUEUE_DEPTH = 100


class EventPublisher(Protocol):
    """Frozen interface publishing typed events to an authorized audience."""

    def publish(self, envelope: EventEnvelope) -> None:
        """Publish one typed envelope to subscribers of its session.

        Args:
            envelope: Typed event envelope scoped to one session.
        """
        ...

    def build_envelope(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> EventEnvelope:
        """Build an envelope with a fresh id and per-session sequence number.

        Args:
            session_id: Session the event belongs to.
            event_type: Dotted past-tense event type.
            payload: JSON-serializable typed payload.

        Returns:
            The envelope ready to publish.
        """
        ...


class WebSocketEventPublisher:
    """In-process publisher delivering envelopes to per-session queues.

    The queue is bounded; when a subscriber falls behind, the oldest buffered
    envelopes are dropped instead of growing without limit. ``publish`` is
    synchronous and intended to be called from the server process only.
    """

    def __init__(self, max_queue_depth: int = MAX_QUEUE_DEPTH) -> None:
        """Create the publisher with a bounded buffer per subscriber.

        Args:
            max_queue_depth: Maximum buffered envelopes per subscriber.
        """

        self._max_queue_depth = max_queue_depth
        self._subscribers: dict[str, list[asyncio.Queue[EventEnvelope]]] = {}
        self._sequence_numbers: dict[str, int] = {}
        self._state_lock = threading.Lock()

    def subscribe(self, session_id: str) -> "asyncio.Queue[EventEnvelope]":
        """Register a bounded subscriber queue for one session.

        Args:
            session_id: Session whose events the subscriber should receive.

        Returns:
            A bounded queue the WebSocket route drains.
        """

        queue: "asyncio.Queue[EventEnvelope]" = asyncio.Queue(
            maxsize=self._max_queue_depth
        )
        with self._state_lock:
            self._subscribers.setdefault(session_id, []).append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: "asyncio.Queue[EventEnvelope]") -> None:
        """Remove a subscriber queue when its connection closes.

        Args:
            session_id: Session the subscriber was listening to.
            queue: Queue returned by ``subscribe``.
        """

        with self._state_lock:
            queues = self._subscribers.get(session_id, [])
            if queue in queues:
                queues.remove(queue)

    def build_envelope(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> EventEnvelope:
        """Build an envelope with a fresh id and per-session sequence number."""

        with self._state_lock:
            sequence = self._sequence_numbers.get(session_id, 0)
            self._sequence_numbers[session_id] = sequence + 1
        return EventEnvelope(
            event_id=f"event_{uuid4().hex}",
            event_type=event_type,
            schema_version=SCHEMA_VERSION,
            session_id=session_id,
            occurred_at=utc_now_iso(),
            sequence_number=sequence,
            payload=payload,
        )

    def publish(self, envelope: EventEnvelope) -> None:
        """Deliver one envelope to every subscriber of its session.

        Args:
            envelope: Typed event envelope scoped to one session.
        """

        with self._state_lock:
            queues = list(self._subscribers.get(envelope.session_id, []))
        for queue in queues:
            try:
                queue.put_nowait(envelope)
            except asyncio.QueueFull:
                # Bounded buffering: drop the oldest envelope and retry once.
                try:
                    queue.get_nowait()
                    queue.put_nowait(envelope)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass
