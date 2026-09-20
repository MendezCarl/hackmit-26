"""OpenAI adapter tests using an injected fake client.

No live provider is contacted; the fake client returns canned structured
responses so grounding validation and measured usage stay testable offline.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import pytest  # noqa: E402

from app.contracts.models import (  # noqa: E402
    ContextWindow,
    LectureSession,
    SessionMode,
    SessionStatus,
    TranscriptChunk,
    TranscriptSource,
)
from app.core.errors import AppError, ErrorCode  # noqa: E402
from app.integrations.openai.adapter import OpenAIRecoveryGenerator  # noqa: E402


class FakeChatCompletions:
    """Fake completions endpoint returning one canned response or error."""

    def __init__(self, payload: object, error: Exception | None = None) -> None:
        self._payload = payload
        self._error = error
        self.last_request_kwargs: dict | None = None

    def create(self, **kwargs) -> object:
        """Record the request and return the canned response."""

        self.last_request_kwargs = kwargs
        if self._error is not None:
            raise self._error
        return self._payload


def fake_response(payload: dict, input_tokens: int = 321, output_tokens: int = 87):
    """Build a fake completion response carrying one payload."""

    content = json.dumps(payload)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=input_tokens, completion_tokens=output_tokens),
    )


def _client_of(completions: FakeChatCompletions) -> object:
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def build_window(session_id: str) -> ContextWindow:
    """Build a two-chunk context window for grounding tests."""

    chunks = [
        TranscriptChunk(
            chunk_id="chunk-1",
            session_id=session_id,
            start_ms=900_000,
            end_ms=960_000,
            text="Queries measure similarity against keys.",
            source=TranscriptSource.LOCAL_TRANSCRIPTION,
            is_final=True,
            revision=1,
        ),
        TranscriptChunk(
            chunk_id="chunk-2",
            session_id=session_id,
            start_ms=960_000,
            end_ms=1_020_000,
            text="Softmax turns scores into weights.",
            source=TranscriptSource.LOCAL_TRANSCRIPTION,
            is_final=True,
            revision=1,
        ),
    ]
    return ContextWindow(
        session_id=session_id,
        requested_start_ms=931_200,
        requested_end_ms=978_700,
        effective_start_ms=901_200,
        effective_end_ms=1_008_700,
        transcript_revision=1,
        chunk_ids=["chunk-1", "chunk-2"],
        chunks=chunks,
    )


def build_session(session_id: str) -> LectureSession:
    """Build a synthetic lecture session."""

    return LectureSession(
        session_id=session_id,
        lecture_id="lecture-1",
        owner_id="owner-1",
        course_id="course-1",
        title="Attention",
        mode=SessionMode.IN_PERSON,
        status=SessionStatus.ACTIVE,
        started_at="2026-01-01T00:00:00.000Z",
        session_clock_origin="2026-01-01T00:00:00.000Z",
    )


def valid_payload() -> dict:
    """Build one fully grounded provider payload."""

    return {
        "topic": "Attention scoring",
        "what_you_missed": "You missed how queries and keys form scores.",
        "key_facts": ["Scores come from query-key similarity."],
        "example_from_lecture": "Queries measure similarity against keys.",
        "follow_up_question": "Could you re-explain the softmax step?",
        "source_timestamps": [
            {"start_ms": 900_000, "end_ms": 960_000, "chunk_id": "chunk-1"}
        ],
    }


def test_grounded_payload_produces_card_with_measured_usage() -> None:
    """A grounded response must become a card with measured token usage."""

    completions = FakeChatCompletions(fake_response(valid_payload()))
    generator = OpenAIRecoveryGenerator("test-key", client=_client_of(completions))
    card, metadata = generator.generate(
        build_session("session-1"), build_window("session-1")
    )

    assert card.topic == "Attention scoring"
    assert card.source_timestamps[0].chunk_id == "chunk-1"
    assert metadata.data_label == "measured"
    assert metadata.provider_mode == "live"
    assert metadata.input_token_count == 321
    assert metadata.output_token_count == 87
    # The request must use strict JSON-schema structured output.
    request_format = completions.last_request_kwargs["response_format"]
    assert request_format["json_schema"]["strict"] is True


def test_ungrounded_chunk_reference_is_rejected() -> None:
    """Citations outside the retrieved window must be rejected."""

    payload = valid_payload()
    payload["source_timestamps"] = [
        {"start_ms": 900_000, "end_ms": 960_000, "chunk_id": "chunk-not-in-window"}
    ]
    completions = FakeChatCompletions(fake_response(payload))
    generator = OpenAIRecoveryGenerator("test-key", client=_client_of(completions))
    with pytest.raises(AppError) as excinfo:
        generator.generate(build_session("session-1"), build_window("session-1"))
    assert excinfo.value.code == ErrorCode.PROVIDER_MALFORMED_OUTPUT


def test_timestamps_outside_chunk_bounds_are_rejected() -> None:
    """Citations must stay within the chunk's own interval."""

    payload = valid_payload()
    payload["source_timestamps"] = [
        {"start_ms": 100, "end_ms": 999_999, "chunk_id": "chunk-1"}
    ]
    completions = FakeChatCompletions(fake_response(payload))
    generator = OpenAIRecoveryGenerator("test-key", client=_client_of(completions))
    with pytest.raises(AppError) as excinfo:
        generator.generate(build_session("session-1"), build_window("session-1"))
    assert excinfo.value.code == ErrorCode.PROVIDER_MALFORMED_OUTPUT


def test_invalid_json_is_a_typed_malformed_output() -> None:
    """Non-JSON provider content must fail as malformed output."""

    raw = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))],
        usage=None,
    )
    completions = FakeChatCompletions(raw)
    generator = OpenAIRecoveryGenerator("test-key", client=_client_of(completions))
    with pytest.raises(AppError) as excinfo:
        generator.generate(build_session("session-1"), build_window("session-1"))
    assert excinfo.value.code == ErrorCode.PROVIDER_MALFORMED_OUTPUT


def test_provider_timeout_is_typed() -> None:
    """Timeout-class exceptions must map to provider_timeout."""

    class APITimeoutError(Exception):
        """Simulated provider timeout."""

    completions = FakeChatCompletions(None, error=APITimeoutError("slow"))
    generator = OpenAIRecoveryGenerator("test-key", client=_client_of(completions))
    with pytest.raises(AppError) as excinfo:
        generator.generate(build_session("session-1"), build_window("session-1"))
    assert excinfo.value.code == ErrorCode.PROVIDER_TIMEOUT


def test_provider_refusal_is_typed() -> None:
    """Other provider errors must map to provider_refused."""

    class APIConnectionError(Exception):
        """Simulated provider failure."""

    completions = FakeChatCompletions(None, error=APIConnectionError("down"))
    generator = OpenAIRecoveryGenerator("test-key", client=_client_of(completions))
    with pytest.raises(AppError) as excinfo:
        generator.generate(build_session("session-1"), build_window("session-1"))
    assert excinfo.value.code == ErrorCode.PROVIDER_REFUSED
