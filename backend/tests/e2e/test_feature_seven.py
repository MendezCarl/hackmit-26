"""Judge scenario checks: isolation, grounded recovery and truthful cost accounting."""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Keep focused runs independent of which older test module Pytest collects first.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.errors import AppError, ErrorCode
from app.demo.cost_comparison import compare_context_cost, estimate_transcript_tokens
from app.demo.runtime import build_demo_runner
from app.demo.synthetic_lecture import build_full_lecture_chunks
from app.main import create_app
from app.recovery.generator import DeterministicRecoveryGenerator


@pytest.mark.parametrize("mode", ["development", "test", "production", "demo"])
def test_health_is_liveness_without_provider_calls(mode, monkeypatch):
    """Health never generates a card or exposes credentials, dependencies or identities."""

    def forbidden_call(*args, **kwargs):
        raise AssertionError("Health must not call a generator")

    monkeypatch.setattr(DeterministicRecoveryGenerator, "generate", forbidden_call)
    client = TestClient(create_app(Settings(app_env=mode)))
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("mode", ["development", "test", "production"])
def test_demo_requires_explicit_demo_environment(mode):
    """Synthetic helpers are not enabled by a production/test host accidentally."""
    client = TestClient(create_app(Settings(app_env=mode)))
    response = client.post("/api/v1/demo/runs")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "demo_unavailable"
    assert client.app.state.store.sessions == {}


@pytest.mark.parametrize(
    "field", ["audio", "webcam_frame", "screenshot", "student_id", "provider_mode"]
)
def test_demo_rejects_external_inputs(field):
    """The judge scenario cannot be used as a media upload or arbitrary user-data path."""
    client = TestClient(create_app(Settings(app_env="demo")))
    response = client.post("/api/v1/demo/runs", json={field: "private-marker"})
    assert response.status_code == 422
    assert "private-marker" not in response.text
    assert client.app.state.store.sessions == {}


def test_demo_ignores_live_host_generator_and_releases_no_host_state(monkeypatch):
    """Even a live-configured host cannot spend credits or retain demo sessions."""

    class HostGenerator(DeterministicRecoveryGenerator):
        def generate(self, *args):
            raise AssertionError("Demo must not use the host generator")

    app = create_app(Settings(app_env="demo", provider_mode="live"), HostGenerator())
    client = TestClient(app)
    # Detect network access without disrupting the in-process ASGI test client.
    import socket

    def no_network(*args, **kwargs):
        raise AssertionError("No network calls are allowed in the demo")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post("/api/v1/demo/runs"), range(2)))
    assert all(response.status_code == 201 for response in results)
    assert all(response.headers["cache-control"] == "no-store" for response in results)
    assert (
        results[0].json()["session"]["session_id"]
        != results[1].json()["session"]["session_id"]
    )
    assert app.state.store.sessions == {}
    assert app.state.store.recovery_cards == {}
    assert app.state.learning_state.coverage == {}


def test_card_is_grounded_in_selected_context_with_compassionate_language():
    """Fixture reference answers and exact timestamps catch irrelevant or invented facts."""
    result = build_demo_runner().run()
    card = result.recovery_card
    chunks = {
        chunk.chunk_id: chunk
        for chunk in build_full_lecture_chunks(result.session.session_id)
    }
    assert {source.chunk_id for source in card.source_timestamps} == {
        f"demo-chunk-{i}" for i in range(1, 5)
    }
    for source in card.source_timestamps:
        assert (source.start_ms, source.end_ms) == (
            chunks[source.chunk_id].start_ms,
            chunks[source.chunk_id].end_ms,
        )
    selected_text = " ".join(
        chunks[source.chunk_id].text for source in card.source_timestamps
    )
    assert all(fact in selected_text for fact in card.key_facts)
    assert "query vector" in " ".join(card.key_facts)
    assert "Multi-head attention" in " ".join(card.key_facts)
    assert card.example_from_lecture in selected_text
    assert "may have missed" in card.what_you_missed
    assert not any(
        word in card.what_you_missed.lower()
        for word in ("distracted", "inattentive", "lazy")
    )


def test_token_costs_are_input_only_estimates_and_cache_skips_generation(monkeypatch):
    """Count actual mock invocations separately from zero external calls and null measured tokens."""
    calls = []
    original = DeterministicRecoveryGenerator.generate

    def counted(self, session, window):
        calls.append(window)
        return original(self, session, window)

    monkeypatch.setattr(DeterministicRecoveryGenerator, "generate", counted)
    result = build_demo_runner().run()
    comparison = result.token_cost_comparison
    assert len(calls) == comparison.mock_generation_calls == 1
    assert comparison.cache_hits == comparison.generation_calls_avoided == 1
    assert comparison.provider_api_calls == 0
    assert (
        comparison.measured_input_tokens
        is comparison.measured_output_tokens
        is comparison.measured_savings_usd
        is None
    )
    assert comparison.selected_context_characters == sum(
        len(c.text) for c in calls[0].chunks
    )
    assert comparison.full_transcript_characters > comparison.selected_context_characters
    assert (
        comparison.full_transcript_estimated_tokens
        == (comparison.full_transcript_characters + 3) // 4
    )
    assert (
        comparison.selected_context_estimated_tokens
        == (comparison.selected_context_characters + 3) // 4
    )
    assert (
        comparison.full_transcript_illustrative_input_usd
        == comparison.full_transcript_estimated_tokens / 1_000_000
    )
    assert (
        comparison.selected_context_illustrative_input_usd
        == comparison.selected_context_estimated_tokens / 1_000_000
    )
    assert comparison.pricing_basis == "hypothetical_not_provider_pricing"
    assert result.cached_recovery_job.card_id == result.recovery_card.card_id
    generated, cached = result.usage_records
    assert generated.input_usage["characters"] == comparison.selected_context_characters
    assert cached.input_usage == {"characters": 0}
    assert all(entry.data_label == "synthetic" for entry in result.usage_records)


@pytest.mark.parametrize(("characters", "expected"), [(0, 0), (1, 1), (4, 1), (5, 2)])
def test_estimation_rounding(characters, expected):
    """Heuristic units are documented and round upward at the token boundary."""
    assert estimate_transcript_tokens(characters) == expected


def test_comparison_rejects_live_usage_and_unknown_sources():
    """Synthetic comparison cannot relabel measured usage or invent a reference."""
    result = build_demo_runner().run()
    chunks = build_full_lecture_chunks(result.session.session_id)
    usage = [entry.model_copy(deep=True) for entry in result.usage_records]
    usage[0].data_label = "measured"
    with pytest.raises(ValueError):
        compare_context_cost(chunks, result.recovery_card, usage)
    with pytest.raises(ValueError):
        compare_context_cost([], result.recovery_card, result.usage_records)
    with pytest.raises(ValueError):
        estimate_transcript_tokens(-1)


@pytest.mark.parametrize(
    ("participants", "expected"),
    [(4, "suppressed"), (5, "available"), (6, "available")],
)
def test_professor_thresholds_and_no_individual_observations(
    participants, expected, monkeypatch
):
    """Exactly k releases aggregates; below k hides counts, sources and ratios."""
    monkeypatch.setattr("app.demo.runner.PARTICIPANT_COUNT", participants)
    result = build_demo_runner().run()
    report = result.professor_metrics
    assert report.status == expected
    encoded = report.model_dump_json()
    assert all(
        word not in encoded
        for word in ("demo-student", "phone_visible", "confidence", "submitted_by")
    )
    if expected == "suppressed":
        assert report.continuity is None
        assert all(
            bucket.possible_missed is None
            and bucket.coverage is None
            and not bucket.transcript_chunk_ids
            for bucket in report.buckets
        )
    else:
        hotspots = [bucket for bucket in report.buckets if bucket.is_hotspot]
        assert hotspots
        assert all(
            bucket.possible_missed.denominator == participants for bucket in hotspots
        )
    assert result.professor_metrics_suppressed.status == "suppressed"


def test_invalid_generation_returns_sanitized_standard_failure(monkeypatch):
    """A broken generator cannot return a false-success demo or leak exception text."""

    def fail(*args):
        raise AppError(ErrorCode.PROVIDER_MALFORMED_OUTPUT, "private-provider-detail")

    monkeypatch.setattr(DeterministicRecoveryGenerator, "generate", fail)
    client = TestClient(create_app(Settings(app_env="demo")))
    response = client.post("/api/v1/demo/runs")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_failure"
    assert "private-provider-detail" not in response.text
    assert client.app.state.store.sessions == {}


def test_demo_contract_artifacts_and_serialized_response():
    """JSON schemas, generated handoff types and real endpoint payload stay aligned."""
    import json

    from jsonschema import Draft202012Validator

    from app.demo.runner import DemoRunResult
    from scripts.generate_demo_contracts import artifacts

    for path, content in artifacts().items():
        assert path.read_text() == content, str(path)
        if path.suffix == ".json":
            Draft202012Validator.check_schema(json.loads(content))
        if path.suffix == ".ts":
            assert "input_usage: Record<string, number>" in content
            assert "output_usage: Record<string, number>" in content
    client = TestClient(create_app(Settings(app_env="demo")))
    response = client.post("/api/v1/demo/runs", json={})
    assert response.status_code == 201
    Draft202012Validator(DemoRunResult.model_json_schema()).validate(response.json())
    schema = client.get("/openapi.json").json()
    route = schema["paths"]["/api/v1/demo/runs"]["post"]
    assert "requestBody" in route
    assert all(str(code) in route["responses"] for code in (201, 404, 413, 415, 422, 502))


def test_judge_script_uses_real_demo_endpoint():
    """The documented no-server command presents the same verified scenario."""
    from scripts.demo_feature_seven import run_demo

    result = run_demo()
    assert result["cache_status"] == "hit"
    assert result["small_group_status"] == "suppressed"
    assert result["professor_status"] == "available"
    assert result["token_cost_comparison"]["measured_savings_usd"] is None
