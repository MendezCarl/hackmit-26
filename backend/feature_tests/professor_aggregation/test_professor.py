"""Threshold privacy, unique participants, consent and post-lecture access tests."""

import asyncio

from app.signals.models import SignalEvent, StoredSignal
from fastapi.testclient import TestClient

from .factories import BASE, authorization, signal


def end_session(client: TestClient) -> None:
    """End only the synthetic fixture session through the demo professor route."""
    assert (
        client.post(f"{BASE}/demo/end", headers=authorization("professor")).status_code
        == 200
    )


def test_post_lecture_professor_authorization(client: TestClient) -> None:
    """Students cannot read aggregates and professors cannot read live reports."""
    path = f"{BASE}/professor-summary"
    assert client.get(path, headers=authorization()).status_code == 403
    assert client.get(path, headers=authorization("professor")).status_code == 409
    end_session(client)
    assert client.get(path, headers=authorization("professor")).status_code == 200


def test_unique_participants_not_event_counts(client: TestClient) -> None:
    """Two events from one person contribute once; no identities escape the summary."""
    seed_events(client, [signal(), signal("event-2")])
    end_session(client)
    result = client.get(f"{BASE}/professor-summary", headers=authorization("professor"))
    report = result.json()
    assert report["timeline_buckets"][0]["possible_missed_ratio"] == 0.2
    assert report["timeline_buckets"][0]["participant_count"] == 5
    assert report["timeline_buckets"][1]["possible_missed_ratio"] == 0
    for prohibited in (
        "student-1",
        "participant_key",
        "event-1",
        "confidence",
        "face_absent",
    ):
        assert prohibited not in result.text
    assert "may have missed context" in report["suggested_actions"][0]


def test_small_group_counts_and_ratios_suppressed(client: TestClient) -> None:
    """With four consenting students, every bucket hides both participation and ratio."""
    services = client.app.state.lecture_feature_services
    services.access.roster[-1].has_aggregate_consent = False
    end_session(client)
    report = client.get(
        f"{BASE}/professor-summary", headers=authorization("professor")
    ).json()
    assert report["status"] == "suppressed"
    assert report["highest_signal_intervals"] == report["suggested_actions"] == []
    assert all(
        bucket["participant_count"] is None and bucket["possible_missed_ratio"] is None
        for bucket in report["timeline_buckets"]
    )


def test_partial_attendance_suppresses_only_affected_buckets(
    client: TestClient,
) -> None:
    """A participant joining mid-bucket is not silently counted for the entire bucket."""
    client.app.state.lecture_feature_services.access.roster[-1].start_ms = 10_000
    end_session(client)
    report = client.get(
        f"{BASE}/professor-summary", headers=authorization("professor")
    ).json()
    assert report["timeline_buckets"][0]["is_suppressed"] is True
    assert report["timeline_buckets"][1]["participant_count"] == 5


def test_correction_and_current_consent_affect_summary(client: TestClient) -> None:
    """A dismissal changes the summary; consent withdrawal immediately suppresses it."""
    seed_events(client, [signal()])
    end_session(client)
    seed_events(client, [signal(user_confirmed=False)])
    assert (
        client.get(
            f"{BASE}/professor-summary", headers=authorization("professor")
        ).json()["highest_signal_intervals"]
        == []
    )
    client.app.state.lecture_feature_services.access.roster[
        0
    ].has_aggregate_consent = False
    assert (
        client.get(
            f"{BASE}/professor-summary", headers=authorization("professor")
        ).json()["status"]
        == "suppressed"
    )


def test_missing_approved_policy_fails_closed(client: TestClient) -> None:
    """An absent real policy cannot silently fall back to the demo threshold."""
    client.app.state.lecture_feature_services.professor.policy = None
    end_session(client)
    response = client.get(
        f"{BASE}/professor-summary", headers=authorization("professor")
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "aggregation_policy_required"


def seed_events(client: TestClient, events: list[dict]) -> None:
    """Simulate upstream stored signals without implementing ingestion on this branch."""

    async def write() -> None:
        repository = client.app.state.lecture_feature_services.repository
        state = await repository.load("demo-session")
        expected = state.revision
        state.signals = [
            StoredSignal(
                participant_key="student-1",
                original=SignalEvent.model_validate(event),
                event=SignalEvent.model_validate(event),
            )
            for event in events
        ]
        state.revision += 1
        assert await repository.replace(state, expected)

    asyncio.run(write())
