"""Phone observations support private recovery only when independently corroborated."""

import pytest
from app.signals.models import SignalEvent, SignalRules
from app.signals.service import build_missed_windows
from fastapi.testclient import TestClient

from .factories import BASE, authorization, signal


def observation(
    event_type: str, start_ms: int = 0, end_ms: int = 20_000, **changes: object
) -> SignalEvent:
    """Build a synthetic local observation with a matching label and unique type ID."""
    return SignalEvent.model_validate(
        signal(
            event_type,
            event_type=event_type,
            signals=[event_type],
            start_ms=start_ms,
            end_ms=end_ms,
            source="local_yolo",
            **changes,
        )
    )


@pytest.mark.parametrize("duration_ms", [3000, 20_000, 60_000])
@pytest.mark.parametrize("is_confirmed", [None, True, False])
def test_phone_alone_never_automatically_becomes_missed_content(
    duration_ms: int, is_confirmed: bool | None
) -> None:
    """A confident phone observation is not evidence of comprehension or distraction."""
    event = observation(
        "phone_visible",
        end_ms=duration_ms,
        confidence=0.99,
        user_confirmed=is_confirmed,
    )
    assert build_missed_windows([event], SignalRules()) == []
    event.event_type = "possible_missed_window"
    assert build_missed_windows([event], SignalRules()) == []


@pytest.mark.parametrize(
    "duration_ms, expected", [(19_999, False), (20_000, True), (20_001, True)]
)
def test_looking_down_requires_continuous_phone_overlap(
    duration_ms: int, expected: bool
) -> None:
    """Candidate timing follows overlap, never the full phone observation interval."""
    events = [
        observation("phone_visible", end_ms=60_000),
        observation("looking_down", 10_000, 10_000 + duration_ms),
    ]
    windows = build_missed_windows(events, SignalRules())
    assert bool(windows) is expected
    if expected:
        assert (windows[0].start_ms, windows[0].end_ms) == (
            10_000,
            10_000 + duration_ms,
        )
        assert windows[0].source_event_ids == ["looking_down", "phone_visible"]
        assert windows[0].confidence == 0.5
        assert events[0].confidence == 0.8


@pytest.mark.parametrize(
    "duration_ms, supports_phone", [(14_999, False), (15_000, True)]
)
def test_phone_unfocused_absent_rule(duration_ms: int, supports_phone: bool) -> None:
    """Independent signals keep existing rules; phone attribution needs 15s overlap."""
    events = [
        observation(kind, end_ms=duration_ms)
        for kind in ("phone_visible", "window_unfocused", "face_absent")
    ]
    windows = build_missed_windows(events, SignalRules())
    assert (
        any("phone_visible" in window.source_event_ids for window in windows)
        is supports_phone
    )


def test_gaps_duplicates_and_out_of_order_inputs_do_not_inflate_support() -> None:
    """Two short overlaps cannot reach 20 seconds by summing or bridging a gap."""
    phone = observation("phone_visible", end_ms=60_000)
    first = observation("looking_down", 0, 10_000)
    second = observation("looking_down", 10_001, 20_001).model_copy(
        update={"event_id": "second"}
    )
    assert build_missed_windows([second, phone, first, first], SignalRules()) == []
    second.start_ms = 10_000
    windows = build_missed_windows([second, phone, first, first], SignalRules())
    assert len(windows) == 1
    assert windows[0].source_event_ids == ["looking_down", "phone_visible", "second"]


def test_dismissal_low_confidence_and_nonoverlap_remove_corroboration() -> None:
    """Missing, dismissed or unreliable evidence cannot corroborate phone presence."""
    phone = observation("phone_visible")
    for looking in (
        observation("looking_down", 20_000, 40_000),
        observation("looking_down", user_confirmed=False),
        observation("looking_down", confidence=0.49),
    ):
        assert build_missed_windows([phone, looking], SignalRules()) == []
    assert (
        build_missed_windows(
            [
                phone.model_copy(update={"user_confirmed": False}),
                observation("looking_down"),
            ],
            SignalRules(),
        )
        == []
    )


def test_bundled_observations_and_configurable_threshold() -> None:
    """The same rules apply to bundled inputs; settings change exact thresholds."""
    event = observation("phone_visible", end_ms=3000)
    event.signals = ["looking_down"]  # Event type must still imply phone presence.
    assert build_missed_windows([event], SignalRules()) == []
    windows = build_missed_windows(
        [event],
        SignalRules(
            phone_looking_down_duration_ms=3000, phone_candidate_confidence_cap=0.3
        ),
    )
    assert windows[0].signals == ["looking_down", "phone_visible"]
    assert windows[0].confidence == 0.3


def test_return_and_looking_down_are_passive_but_self_report_is_explicit() -> None:
    """Returning and note-taking are not automatic recovery requests."""
    for kind in ("student_returned", "looking_down"):
        assert build_missed_windows([observation(kind)], SignalRules()) == []
    for kind in ("student_left_frame", "head_away", "window_unfocused", "face_absent"):
        assert build_missed_windows([observation(kind)], SignalRules())
    assert build_missed_windows(
        [observation("user_marked_confused", end_ms=1, confidence=0)], SignalRules()
    )


def test_phone_ingestion_is_private_correctable_and_identity_is_authenticated(
    client: TestClient,
) -> None:
    """REST ingestion and timeline fusion respect participant boundaries and correction."""
    path = f"{BASE}/events/batch"
    phone = observation("phone_visible").model_dump()
    looking = observation("looking_down").model_dump()
    assert (
        client.post(path, headers=authorization(), json={"events": [phone]}).status_code
        == 200
    )
    assert (
        client.post(
            path, headers=authorization("student-2"), json={"events": [looking]}
        ).status_code
        == 200
    )
    timeline_path = f"{BASE}/timeline?start_ms=0&end_ms=60000"
    result = client.get(timeline_path, headers=authorization()).json()
    assert result["missed_windows"] == []
    assert result["events"][0]["source"] == "local_yolo"
    assert (
        client.post(
            path, headers=authorization(), json={"events": [looking]}
        ).status_code
        == 200
    )
    assert client.get(timeline_path, headers=authorization()).json()["missed_windows"]
    assert (
        client.patch(
            f"{BASE}/events/looking_down",
            headers=authorization(),
            json={"user_confirmed": False},
        ).status_code
        == 200
    )
    assert (
        client.get(timeline_path, headers=authorization()).json()["missed_windows"]
        == []
    )
    for extra in (
        {"student_id": "student-2"},
        {"frame": "raw-camera"},
        {"source": "untrusted_provider"},
    ):
        response = client.post(
            path, headers=authorization(), json={"events": [{**phone, **extra}]}
        )
        assert response.status_code == 422
    assert (
        client.get(timeline_path, headers=authorization("professor")).json()["events"]
        == []
    )


def test_openapi_describes_optional_phone_source_and_all_observation_types(
    client: TestClient,
) -> None:
    """Wire metadata includes the new types without requiring source on older clients."""
    schema = client.get("/openapi.json").json()["components"]["schemas"]["SignalEvent"]
    assert "source" not in schema["required"]
    assert "phone_visible" in schema["properties"]["event_type"]["enum"]
    assert "local_yolo" in str(schema["properties"]["source"])
    assert "student_id" not in schema["properties"]
