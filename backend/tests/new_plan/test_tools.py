"""Bounded tool execution reauthorizes every call and refuses arbitrary access."""

import pytest

from app.ai.tools import ToolArguments, ToolCall, ToolRegistry, ToolRunner, ToolTurn
from app.contracts.learning import LectureInterval
from app.core.errors import AppError
from app.transcript.repository import InMemoryTimelineReader

from .fixtures import actor, setup


def registry():
    """Build a student-scoped synthetic tool registry."""
    client, session, _base = setup()
    state = client.app.state
    return ToolRegistry(
        actor(),
        session,
        LectureInterval(start_ms=0, end_ms=30_000),
        state.session_access,
        state.store,
        InMemoryTimelineReader(state.store),
        state.professor_metrics,
    )


class Model:
    """Provider-neutral recorded turn sequence."""

    def __init__(self, turns):
        self.turns = iter(turns)

    def next_turn(self, results):
        return next(self.turns)


def call(name="get_transcript_window", start=0, end=30_000):
    """Create one normalized read-only call."""
    return ToolCall(
        call_id="call1", name=name, arguments=ToolArguments(start_ms=start, end_ms=end)
    )


def test_bounded_read_and_final_output():
    selected = registry()
    model = Model([ToolTurn(calls=[call()]), ToolTurn(final_json='{"result":"synthetic"}')])
    assert ToolRunner().run(model, selected) == '{"result":"synthetic"}'


@pytest.mark.parametrize(
    "name", ["get_session_metrics", "get_course_context", "get_recovery_history"]
)
def test_non_interval_tools_reject_filter_arguments(name):
    with pytest.raises(AppError):
        registry().execute(call(name))


def test_student_cannot_read_professor_aggregates_through_tool():
    with pytest.raises(AppError):
        registry().execute(
            ToolCall(call_id="a", name="get_session_metrics", arguments=ToolArguments())
        )


def test_request_interval_cannot_expand_and_output_is_bounded():
    selected = registry()
    with pytest.raises(AppError):
        selected.execute(call(end=60_000))
    selected.maximum_output_characters = 10
    with pytest.raises(AppError):
        selected.execute(call())


def test_duplicate_calls_and_round_limits_fail_closed():
    with pytest.raises(AppError):
        ToolRunner().run(
            Model([ToolTurn(calls=[call()]), ToolTurn(calls=[call()])]), registry()
        )
    with pytest.raises(AppError):
        ToolRunner(maximum_rounds=1).run(
            Model([ToolTurn(calls=[call()]), ToolTurn(calls=[call(end=1000)])]),
            registry(),
        )


def test_membership_revocation_is_checked_after_tool_turn():
    selected = registry()

    class RevokingModel:
        def next_turn(self, results):
            selected.store.sessions.clear()
            return ToolTurn(calls=[call()])

    with pytest.raises(AppError):
        ToolRunner().run(RevokingModel(), selected)
