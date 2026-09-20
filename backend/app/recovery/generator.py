"""Recovery generators: converting bounded context into grounded cards.

``RecoveryGenerator`` is the frozen shared interface. The deterministic
generator is the default mock: it never calls a live provider and always
records its usage as ``synthetic``. Live OpenAI integration replaces this
adapter only after the provider integration gate is met.
"""

from __future__ import annotations

import time
from typing import Protocol

from app.contracts.models import (
    ContextWindow,
    LectureSession,
    ModelMetadata,
    RecoveryCard,
    SourceTimestamp,
)

DETERMINISTIC_PROVIDER = "mock"
DETERMINISTIC_MODEL = "deterministic-recovery-mock"
RECOVERY_PROMPT_VERSION = "recovery-v1"
RECOVERY_OUTPUT_SCHEMA_VERSION = "recovery_card-1"
MAX_KEY_FACTS = 5
TOPIC_MAX_CHARS = 60


class RecoveryGenerator(Protocol):
    """Frozen interface converting a context window into a grounded card."""

    provider: str
    model: str
    prompt_version: str
    output_schema_version: str

    def generate(
        self, session: LectureSession, window: ContextWindow
    ) -> tuple[RecoveryCard, ModelMetadata]:
        """Generate a validated card plus usage metadata.

        Args:
            session: Authorized lecture session providing scope.
            window: Bounded, padded context window with final chunks.

        Returns:
            A tuple of the generated card and provider usage metadata.
        """
        ...


def _first_sentence(text: str) -> str:
    """Extract the leading sentence of a transcript excerpt.

    Args:
        text: Transcript text for one chunk.

    Returns:
        The text up to the first sentence boundary, or the whole excerpt.
    """

    for boundary in (". ", "! ", "? "):
        position = text.find(boundary)
        if position != -1:
            return text[: position + 1].strip()
    return text.strip()


def _build_topic(window: ContextWindow) -> str:
    """Derive a short deterministic topic label from the window.

    Args:
        window: Bounded context window with at least one final chunk.

    Returns:
        A concise topic label for the missed interval.
    """

    first_chunk = window.chunks[0]
    topic = _first_sentence(first_chunk.text)
    if len(topic) > TOPIC_MAX_CHARS:
        topic = topic[: TOPIC_MAX_CHARS - 1].rstrip() + "…"
    return topic


class DeterministicRecoveryGenerator:
    """Mock provider building a grounded card deterministically.

    The card is grounded exclusively in the selected transcript chunks and
    their timestamps; it never invents lecture content. Usage is labeled
    ``synthetic`` because no live provider call occurs.
    """

    provider = DETERMINISTIC_PROVIDER
    model = DETERMINISTIC_MODEL
    prompt_version = RECOVERY_PROMPT_VERSION
    output_schema_version = RECOVERY_OUTPUT_SCHEMA_VERSION

    def generate(
        self, session: LectureSession, window: ContextWindow
    ) -> tuple[RecoveryCard, ModelMetadata]:
        """Build a compassionate, grounded card from the selected chunks.

        Args:
            session: Authorized lecture session providing scope.
            window: Bounded, padded context window with final chunks.

        Returns:
            A tuple of the generated card and synthetic usage metadata.
        """

        started = time.perf_counter()
        chunks = window.chunks
        if not chunks:
            raise ValueError("A context window must contain at least one final chunk.")

        topic = _build_topic(window)
        joined_text = " ".join(chunk.text.strip() for chunk in chunks)
        key_facts = [
            _first_sentence(chunk.text)
            for chunk in chunks[:MAX_KEY_FACTS]
            if chunk.text.strip()
        ]
        requested_center = (window.requested_start_ms + window.requested_end_ms) / 2
        closest_chunk = min(
            chunks,
            key=lambda chunk: abs((chunk.start_ms + chunk.end_ms) / 2 - requested_center),
        )
        source_timestamps = [
            SourceTimestamp(
                start_ms=chunk.start_ms,
                end_ms=chunk.end_ms,
                chunk_id=chunk.chunk_id,
                source=chunk.source.value,
            )
            for chunk in chunks
        ]
        latency_ms = int((time.perf_counter() - started) * 1000)

        card_text = (
            "It looks like you may have missed part of the lecture around this "
            f'moment of "{session.title}". Here is a focused recap of the '
            "content from that interval so you can pick the thread back up."
        )
        metadata = ModelMetadata(
            provider=self.provider,
            model=self.model,
            provider_mode="mock",
            data_label="synthetic",
            prompt_version=self.prompt_version,
            output_schema_version=self.output_schema_version,
            input_character_count=sum(len(chunk.text) for chunk in chunks),
            output_character_count=len(joined_text),
            latency_ms=latency_ms,
        )
        card = RecoveryCard(
            card_id="pending",
            session_id=session.session_id,
            source_event_ids=[],
            topic=topic,
            what_you_missed=card_text,
            key_facts=key_facts,
            example_from_lecture=closest_chunk.text.strip(),
            source_timestamps=source_timestamps,
            follow_up_question=(
                f'Could you explain how "{topic}" connects to what came '
                "next in this lecture?"
            ),
            model_metadata=metadata,
            created_at="",
        )
        return card, metadata
