"""Canonical synthetic lecture data used by the demo runner and e2e tests.

Everything in this module is synthetic; it contains no real student data,
transcripts, or media. The missed interval matches the timestamp model from
the product plan.
"""

from __future__ import annotations

from app.contracts.models import SignalEvent, TranscriptChunk, TranscriptSource

DEMO_LECTURE_ID = "demo-lecture-0001"
DEMO_COURSE_ID = "demo-course-101"
DEMO_SESSION_TITLE = "Synthetic Lecture: Attention and Transformers"

# The central timestamp model's example interval.
MISSED_WINDOW_START_MS = 931_200
MISSED_WINDOW_END_MS = 978_700
PARTICIPANT_COUNT = 5
SPEAKER_LABEL = "instructor"


def build_synthetic_transcript_chunks(session_id: str) -> list[TranscriptChunk]:
    """Build the canonical synthetic timestamped transcript.

    Args:
        session_id: Session the synthetic chunks belong to.

    Returns:
        Final synthetic transcript chunks covering the missed interval.
    """

    synthetic_lines = [
        (
            900_000,
            930_000,
            "Before we continue, recall that attention lets a model weigh how "
            "much each input token should influence every output token.",
        ),
        (
            930_000,
            960_000,
            "We compute attention scores by taking a query vector and "
            "measuring its similarity against every key vector. "
            "A softmax then turns those scores into weights that sum to one.",
        ),
        (
            960_000,
            990_000,
            "Multi-head attention runs several of these scoring passes in "
            "parallel so the model can track different relationships at once.",
        ),
        (
            990_000,
            1_020_000,
            "Finally, the weighted values are concatenated and projected back "
            "into the original embedding size before the next layer begins.",
        ),
    ]
    return [
        TranscriptChunk(
            chunk_id=f"demo-chunk-{index}",
            session_id=session_id,
            start_ms=start_ms,
            end_ms=end_ms,
            text=text,
            speaker_label=SPEAKER_LABEL,
            source=TranscriptSource.LOCAL_TRANSCRIPTION,
            is_final=True,
            revision=1,
        )
        for index, (start_ms, end_ms, text) in enumerate(synthetic_lines, start=1)
    ]


def build_synthetic_missed_event(
    session_id: str, event_id: str
) -> SignalEvent:
    """Build one synthetic possible-missed-window event.

    Args:
        session_id: Session the event belongs to.
        event_id: Unique synthetic event identifier.

    Returns:
        A synthetic coarse signal event matching the central timestamp model.
    """

    return SignalEvent(
        event_id=event_id,
        session_id=session_id,
        event_type="possible_missed_window",
        start_ms=MISSED_WINDOW_START_MS,
        end_ms=MISSED_WINDOW_END_MS,
        signals=["head_away", "window_unfocused"],
        confidence=0.76,
        user_confirmed=None,
        client_generated_at=None,
    )
