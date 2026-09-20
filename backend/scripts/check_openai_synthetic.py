"""Explicit opt-in live check using only synthetic text; consumes API credits."""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.contracts.models import ContextWindow, LectureSession, TranscriptChunk
from app.integrations.openai.recovery import OpenAIRecoveryGenerator


def main() -> int:
    """Call OpenAI only with --live and configured server-side key/model; print usage only."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.parse_args()
    model = os.environ.get("OPENAI_MODEL")
    if not model or not os.environ.get("OPENAI_API_KEY"):
        parser.error("Set OPENAI_MODEL and OPENAI_API_KEY in the environment.")
    from openai import OpenAI

    session = LectureSession(
        session_id="synthetic-session",
        lecture_id="synthetic-lecture",
        owner_id="synthetic-user",
        course_id="synthetic-course",
        title="Synthetic stacks",
        mode="in_person",
        status="active",
        started_at="2026-09-19T00:00:00Z",
        session_clock_origin="2026-09-19T00:00:00Z",
    )
    chunk = TranscriptChunk(
        chunk_id="synthetic-chunk",
        session_id=session.session_id,
        start_ms=0,
        end_ms=10000,
        text="A stack follows last-in, first-out ordering.",
        source="local_transcription",
    )
    window = ContextWindow(
        session_id=session.session_id,
        requested_start_ms=0,
        requested_end_ms=10000,
        effective_start_ms=0,
        effective_end_ms=10000,
        transcript_revision=1,
        chunk_ids=[chunk.chunk_id],
        chunks=[chunk],
    )
    _, usage = OpenAIRecoveryGenerator(
        OpenAI(timeout=20, max_retries=1), model
    ).generate(session, window)
    print(usage.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
