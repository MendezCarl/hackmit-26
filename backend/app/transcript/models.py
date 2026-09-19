"""Versioned transcript chunks on the shared lecture clock."""

from typing import Annotated, Literal

from pydantic import Field, field_validator

from app.timeline.contracts import Identifier, Interval, StrictModel

MAX_CHUNK_CHARACTERS = 2000


class TranscriptChunk(Interval):
    """Selected derived text; revision increases for corrections or finalization."""

    chunk_id: Identifier
    lecture_id: Identifier
    text: Annotated[str, Field(min_length=1, max_length=MAX_CHUNK_CHARACTERS)]
    source: Literal["zoom_rtms", "local_transcription", "external_transcription"]
    is_final: Annotated[bool, Field(strict=True)]
    revision: Annotated[int, Field(strict=True, ge=1)] = 1

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Return bounded text; reject empty content, binary controls and data URLs."""
        if not value.strip() or any(
            ord(char) < 32 and char not in "\n\r\t" for char in value
        ):
            raise ValueError("Transcript must contain plain text.")
        if "data:audio/" in value.lower() or "data:image/" in value.lower():
            raise ValueError("Media data URLs are forbidden.")
        return value


class TranscriptBatch(StrictModel):
    """A bounded batch of independently revisioned transcript chunks."""

    chunks: Annotated[list[TranscriptChunk], Field(min_length=1, max_length=100)]


class TranscriptMessage(StrictModel):
    """Client-to-server WebSocket message; identity and session come from transport."""

    event_type: Literal["transcript.batch.submitted"]
    payload: TranscriptBatch
