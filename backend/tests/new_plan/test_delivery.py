"""Delivery observations are authorized, derived and separate from student signals."""

import pytest

from .fixtures import cover_all, end, headers, report, setup


def event():
    """One synthetic local detector output."""
    return {
        "event_id": "d1",
        "signal_type": "presenter_out_of_frame",
        "start_ms": 0,
        "end_ms": 15_000,
        "confidence": 0.5,
        "detector_version": "test-v1",
        "evidence": {
            "sample_count": 16,
            "positive_sample_count": 15,
            "performance_profile": "low_power",
        },
    }


def test_delivery_requires_professor_and_safe_coverage_before_release():
    client, session, base = setup()
    payload = {"events": [event()]}
    assert (
        client.post(
            base + "/delivery-events/batch", headers=headers(), json=payload
        ).status_code
        == 403
    )
    assert (
        client.post(
            base + "/delivery-events/batch",
            headers=headers("prof", "professor"),
            json=payload,
        ).json()["accepted"]
        == 1
    )
    assert (
        client.post(
            base + "/delivery-events/batch",
            headers=headers("prof", "professor"),
            json=payload,
        ).json()["duplicates"]
        == 1
    )
    assert client.app.state.store.events.get(session, []) == []
    cover_all(client, base)
    end(client, base)
    findings = report(client, base).json()["delivery_findings"]
    assert len(findings) == 1 and findings[0]["signal_type"] == "presenter_out_of_frame"
    assert "evidence" not in findings[0]


@pytest.mark.parametrize(
    "field",
    ["frame", "frame_url", "bounding_boxes", "student_id", "device_id", "local_path"],
)
def test_prohibited_delivery_fields_rejected(field):
    client, _session, base = setup()
    value = event()
    value[field] = "forbidden"
    assert (
        client.post(
            base + "/delivery-events/batch",
            headers=headers("prof", "professor"),
            json={"events": [value]},
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "change",
    [
        {"start_ms": True},
        {"end_ms": 0},
        {"confidence": 1.5},
        {"signal_type": "phone_visible"},
    ],
)
def test_invalid_delivery_semantics_rejected(change):
    client, _session, base = setup()
    value = event()
    value.update(change)
    assert (
        client.post(
            base + "/delivery-events/batch",
            headers=headers("prof", "professor"),
            json={"events": [value]},
        ).status_code
        == 422
    )
