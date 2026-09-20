"""Structured SDK adapter refuses fabricated source evidence without live calls."""

from types import SimpleNamespace

import pytest

from app.contracts.learning import RecoveryDraft
from app.contracts.models import ContextWindow
from app.core.errors import AppError
from app.integrations.openai.recovery import OpenAIRecoveryGenerator

from .support import fixture


def test_invalid_evidence_is_not_a_successful_card():
    store, _, _, _ = fixture()
    draft = RecoveryDraft.model_validate(
        {
            "topic": "Stacks",
            "explanation": "Synthetic explanation",
            "facts": [
                {
                    "text": "Invented",
                    "chunk_id": "source_0",
                    "evidence_quote": "not in transcript",
                }
            ],
            "follow_up_question": "An example?",
        }
    )

    class Responses:
        def parse(self, **kwargs):
            assert kwargs["store"] is False and "student1" not in kwargs["input"]
            return SimpleNamespace(
                status="completed",
                output=[],
                output_parsed=draft,
                usage=SimpleNamespace(input_tokens=10, output_tokens=10),
            )

    window = ContextWindow(
        session_id="s",
        requested_start_ms=0,
        requested_end_ms=30000,
        effective_start_ms=0,
        effective_end_ms=30000,
        transcript_revision=1,
        chunk_ids=["chunk"],
        chunks=store.transcript_chunks["s"],
    )
    with pytest.raises(AppError):
        OpenAIRecoveryGenerator(
            SimpleNamespace(responses=Responses()), "synthetic-model"
        ).generate(store.sessions["s"], window)
