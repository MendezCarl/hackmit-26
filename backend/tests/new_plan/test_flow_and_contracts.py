"""Repeatable synthetic full flow and generated-contract drift checks."""

import json

from jsonschema import Draft202012Validator
from scripts.demo_new_plan import run_demo
from scripts.generate_learning_contracts import artifacts

from .fixtures import headers, setup, signal


def test_new_plan_demo_runs_without_provider_calls():
    result = run_demo()
    assert result["mode"] == "synthetic_only"
    assert result["recovery_status"] == "completed"
    assert result["repeat_cache_status"] == "hit"
    assert result["export"]["provider_mode"] == "mock"
    assert result["metrics_status"] == "available"
    assert result["recommendation_count"] == 1
    assert result["after_revocation"] == "suppressed"


def test_shared_schemas_and_handoff_types_are_current():
    for path, content in artifacts().items():
        assert path.read_text() == content, str(path)
        if path.suffix == ".json":
            Draft202012Validator.check_schema(json.loads(content))


def test_no_duplicate_openapi_operation_ids_and_standard_error_models():
    client, _, _ = setup()
    schema = client.get("/openapi.json").json()
    ids = [
        operation["operationId"]
        for path in schema["paths"].values()
        for operation in path.values()
        if "operationId" in operation
    ]
    assert len(ids) == len(set(ids))
    entry = schema["paths"]["/api/v1/sessions/{session_id}/professor-metrics"]["get"]
    assert entry["responses"]["403"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/ErrorResponse")


def test_body_limits_reject_media_before_validation():
    client, _, base = setup()
    assert (
        client.post(
            base + "/delivery-events/batch",
            content=b"x" * 1_048_577,
            headers={**headers(), "Content-Type": "application/json"},
        ).status_code
        == 413
    )
    assert (
        client.post(
            base + "/delivery-events/batch",
            content=b"fake media",
            headers={**headers(), "Content-Type": "video/mp4"},
        ).status_code
        == 415
    )


def test_student_cannot_correct_another_students_event_or_request_its_recovery():
    client, session, base = setup()
    signal(client, session, base)
    response = client.post(
        base + "/events/e1/confirmation",
        headers=headers("s2"),
        json={"user_confirmed": False},
    )
    assert response.status_code == 403
    response = client.post(
        base + "/recovery-cards",
        headers=headers("s2"),
        json={"start_ms": 0, "end_ms": 30_000, "source_event_ids": ["e1"]},
    )
    assert response.status_code == 422


def test_phone_alone_is_not_recovery_eligible():
    client, session, base = setup()
    response = signal(client, session, base, kind="phone_visible")
    assert response.status_code == 202
    assert response.json()["recovery_eligible_event_ids"] == []


def test_mock_export_requires_selection_confirmation_and_card_ownership():
    client, _, base = setup()
    job = client.post(
        base + "/recovery-cards",
        headers=headers(),
        json={"start_ms": 0, "end_ms": 30_000},
    ).json()
    export = {"card_id": job["card_id"], "filename": "review.md", "is_confirmed": True}
    assert (
        client.post(
            base + "/artifacts/exports", headers=headers(), json=export
        ).status_code
        == 403
    )
    client.put(
        base + "/artifacts/folder",
        headers=headers(),
        json={"folder_id": "synthetic-course-folder"},
    )
    assert (
        client.post(
            base + "/artifacts/exports", headers=headers("s2"), json=export
        ).status_code
        == 403
    )
    assert (
        client.post(
            base + "/artifacts/exports",
            headers=headers(),
            json={**export, "is_confirmed": False},
        ).status_code
        == 403
    )
    assert (
        client.post(base + "/artifacts/exports", headers=headers(), json=export).json()[
            "provider_mode"
        ]
        == "mock"
    )
    assert (
        client.post(
            base + "/artifacts/exports", headers=headers(), json=export
        ).status_code
        == 409
    )


def test_signal_batch_conflicts_are_atomic_and_ended_sessions_reject_ingestion():
    """A late conflict cannot preserve the first write of a rejected signal batch."""
    client, session, base = setup()
    assert signal(client, session, base).status_code == 202
    existing = client.app.state.store.events[session][0].event.model_dump(mode="json")
    response = client.post(
        base + "/events/batch",
        headers=headers(),
        json={"lecture_id": "l", "events": [{**existing, "event_id": "new"}, existing]},
    )
    assert response.status_code == 409
    assert len(client.app.state.store.events[session]) == 1
    client.post(base + "/end", headers=headers())
    assert signal(client, session, base, event_id="late").status_code == 422
