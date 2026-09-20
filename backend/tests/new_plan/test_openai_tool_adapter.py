"""SDK-shaped tool responses must normalize into bounded provider-neutral turns."""

from types import SimpleNamespace

import pytest
from app.core.errors import AppError
from app.integrations.openai.tools import OpenAIToolModel


class Responses:
    """Capture SDK calls and return a recorded synthetic response sequence."""

    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return next(self.outputs)


def response(output, text=""):
    """Return only SDK fields consumed by the adapter."""
    return SimpleNamespace(
        status="completed",
        output=output,
        output_text=text,
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


def test_all_output_items_and_tool_results_are_preserved_without_server_storage():
    reasoning = SimpleNamespace(type="reasoning", summary=[])
    call = SimpleNamespace(
        type="function_call",
        call_id="call1",
        name="get_transcript_window",
        arguments='{"start_ms":0,"end_ms":1000}',
    )
    api = Responses(
        [response([reasoning, call]), response([], '{"topic":"synthetic"}')]
    )
    model = OpenAIToolModel(
        SimpleNamespace(responses=api),
        "test-model",
        "Synthetic request",
        ("get_transcript_window",),
    )
    turn = model.next_turn([])
    assert turn.calls[0].name == "get_transcript_window"
    assert (
        model.next_turn([("call1", '{"sources":[]}')]).final_json
        == '{"topic":"synthetic"}'
    )
    assert reasoning in model.input and call in model.input
    assert any(
        isinstance(item, dict) and item.get("type") == "function_call_output"
        for item in model.input
    )
    assert all(request["store"] is False for request in api.requests)
    assert model.input_tokens == 20 and model.output_tokens == 10


@pytest.mark.parametrize(
    "name,arguments",
    [
        ("delete_file", "{}"),
        ("get_transcript_window", '{"start_ms":0,"end_ms":1000,"session_id":"other"}'),
        ("get_transcript_window", "not JSON"),
    ],
)
def test_unknown_tools_or_untrusted_arguments_fail_closed(name, arguments):
    call = SimpleNamespace(
        type="function_call", call_id="a", name=name, arguments=arguments
    )
    api = Responses([response([call])])
    model = OpenAIToolModel(
        SimpleNamespace(responses=api),
        "test-model",
        "Synthetic request",
        ("get_transcript_window",),
    )
    with pytest.raises(AppError):
        model.next_turn([])
