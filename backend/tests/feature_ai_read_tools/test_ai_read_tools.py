"""A model cannot expand a scoped transcript interval or repeat tool calls."""

import pytest

from app.ai.tools import ToolArguments, ToolCall, ToolRegistry, ToolRunner, ToolTurn
from app.contracts.learning import LectureInterval
from app.core.errors import AppError, ErrorCode
from app.transcript.repository import InMemoryTimelineReader

from .support import actor, fixture


class NoMetrics:
    def report(self, actor, session_id):
        raise AppError(ErrorCode.FORBIDDEN, "No professor report permitted.")


def test_tool_scope_and_cycle_limits():
    store, _, access, _ = fixture()
    registry = ToolRegistry(
        actor(),
        "s",
        LectureInterval(start_ms=0, end_ms=10000),
        access,
        store,
        InMemoryTimelineReader(store),
        NoMetrics(),
    )
    with pytest.raises(AppError):
        registry.execute(
            ToolCall(
                call_id="a",
                name="get_transcript_window",
                arguments=ToolArguments(start_ms=0, end_ms=20000),
            )
        )
    call = ToolCall(
        call_id="a",
        name="get_transcript_window",
        arguments=ToolArguments(start_ms=0, end_ms=10000),
    )

    class RepeatingModel:
        def next_turn(self, results):
            return ToolTurn(calls=[call])

    with pytest.raises(AppError):
        ToolRunner().run(RepeatingModel(), registry)
