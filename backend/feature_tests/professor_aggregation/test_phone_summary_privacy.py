"""Phone-related evidence is excluded from professor output and aggregate counts."""

import asyncio

import pytest
from app.signals.models import SignalEvent, StoredSignal
from fastapi.testclient import TestClient

from .factories import BASE, authorization, signal


@pytest.mark.parametrize(
    "event_type, labels",
    [
        ("phone_visible", ["phone_visible"]),
        ("phone_visible", ["face_absent"]),
        ("possible_missed_window", ["phone_visible", "looking_down"]),
        (
            "possible_missed_window",
            ["phone_visible", "window_unfocused", "face_absent"],
        ),
        ("student_returned", ["student_returned"]),
    ],
)
def test_phone_observations_never_affect_professor_report(
    client: TestClient, event_type: str, labels: list[str]
) -> None:
    """Even confirmed phone-related bundles remain outside professor counts and text."""
    event = SignalEvent.model_validate(
        signal(
            event_type=event_type,
            signals=labels,
            source="local_yolo",
            user_confirmed=True,
        )
    )

    async def seed() -> None:
        repository = client.app.state.lecture_feature_services.professor.repository
        state = await repository.load("demo-session")
        expected = state.revision
        state.signals.append(
            StoredSignal(participant_key="student-1", original=event, event=event)
        )
        state.revision += 1
        assert await repository.replace(state, expected)

    asyncio.run(seed())
    assert (
        client.post(f"{BASE}/demo/end", headers=authorization("professor")).status_code
        == 200
    )
    result = client.get(f"{BASE}/professor-summary", headers=authorization("professor"))
    assert result.status_code == 200
    report = result.json()
    assert all(
        bucket["possible_missed_ratio"] == 0 for bucket in report["timeline_buckets"]
    )
    assert report["highest_signal_intervals"] == report["suggested_actions"] == []
    for private in ("phone", "local_yolo", "student-1", "distracted", "confidence"):
        assert private not in result.text
