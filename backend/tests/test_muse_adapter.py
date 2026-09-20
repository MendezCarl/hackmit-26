"""Meta Muse adapter tests using an injected fake Responses client."""

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.contracts.learning import RecoveryDraft
from app.contracts.models import (
    ContextWindow,
    LectureSession,
    SessionMode,
    SessionStatus,
    TranscriptChunk,
    TranscriptSource,
)
from app.integrations.meta_muse.recovery import (
    MuseRecoveryGenerator,
    create_muse_generator,
)
from app.main import create_app


def build_session() -> LectureSession:
    """Build a synthetic lecture session for adapter tests."""
    return LectureSession(
        session_id="session-1",
        lecture_id="lecture-1",
        owner_id="owner-1",
        course_id="course-1",
        title="Synthetic stacks",
        mode=SessionMode.IN_PERSON,
        status=SessionStatus.ACTIVE,
        started_at="2026-01-01T00:00:00.000Z",
        session_clock_origin="2026-01-01T00:00:00.000Z",
    )


def build_window() -> ContextWindow:
    """Build a synthetic context window with one grounded transcript chunk."""
    chunk = TranscriptChunk(
        chunk_id="chunk-1",
        session_id="session-1",
        start_ms=0,
        end_ms=30_000,
        text="A stack uses last-in, first-out ordering.",
        source=TranscriptSource.LOCAL_TRANSCRIPTION,
        is_final=True,
        revision=1,
    )
    return ContextWindow(
        session_id="session-1",
        requested_start_ms=0,
        requested_end_ms=30_000,
        effective_start_ms=0,
        effective_end_ms=30_000,
        transcript_revision=1,
        chunk_ids=["chunk-1"],
        chunks=[chunk],
    )


class Responses:
    """SDK-shaped fake captures structured Responses requests offline."""

    def __init__(self, evidence_quote: str = "last-in, first-out") -> None:
        self.evidence_quote = evidence_quote
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs: object) -> SimpleNamespace:
        """Capture request kwargs and return one schema-valid response."""
        self.calls.append(kwargs)
        return SimpleNamespace(
            status="completed",
            output=[],
            output_parsed=RecoveryDraft(
                topic="Stacks",
                explanation="A stack uses last-in, first-out ordering.",
                facts=[
                    {
                        "text": "The last item is removed first.",
                        "chunk_id": "source_0",
                        "evidence_quote": self.evidence_quote,
                    }
                ],
                follow_up_question="Would a worked example help?",
            ),
            usage=SimpleNamespace(input_tokens=100, output_tokens=40),
        )


def test_muse_generator_records_provider_and_request_metadata() -> None:
    """Muse generation uses the OpenAI-compatible request and measured metadata."""
    responses = Responses()
    generator = MuseRecoveryGenerator(
        SimpleNamespace(responses=responses), "muse-spark-1.2"
    )

    card, _metadata = generator.generate(build_session(), build_window())

    assert card.model_metadata.provider == "meta_muse"
    assert card.model_metadata.model == "muse-spark-1.2"
    assert card.model_metadata.provider_mode == "live"
    assert card.model_metadata.data_label == "measured"
    assert responses.calls[0]["store"] is False
    assert responses.calls[0]["model"] == "muse-spark-1.2"


def test_muse_generator_accepts_normalized_grounding_quote() -> None:
    """Provider punctuation and whitespace normalization preserves grounding."""
    responses = Responses(" a student’s stack uses last-in - first-out ")
    generator = MuseRecoveryGenerator(
        SimpleNamespace(responses=responses), "muse-spark-1.2"
    )
    window = build_window()
    window.chunks[0].text = "A student's stack uses last-in – first-out ordering."

    card, _metadata = generator.generate(build_session(), window)

    assert card.key_facts == ["The last item is removed first."]


def test_create_muse_generator_requires_api_key() -> None:
    """Muse configuration fails without a provider API key."""
    with pytest.raises(RuntimeError, match="MUSE_API_KEY"):
        create_muse_generator(Settings(app_env="test", muse_api_key=None))


def test_create_app_builds_muse_live_generator() -> None:
    """Live Muse app composition constructs the optional SDK client offline."""
    app = create_app(
        Settings(
            app_env="test",
            provider_mode="live",
            live_provider="meta_muse",
            muse_api_key="k",
        )
    )

    assert app.state.recovery_generator.delegate.provider == "meta_muse"
