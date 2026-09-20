"""Coverage, deduplication, corrections and small-group inference boundaries."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

from .fixtures import cover_all, coverage, end, headers, report, setup, signal


def registered_professor_metrics_session() -> tuple[TestClient, str, str, str]:
    """Create an ended session owned by a registered professor."""

    client = TestClient(create_app(Settings(app_env="test", context_padding_ms=0)))
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "metrics-owner@example.edu",
            "password": "password-123",
            "display_name": "Metrics Owner",
            "role": "professor",
        },
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {token}"}
    course = client.post(
        "/api/v1/courses",
        headers=owner_headers,
        json={"code": "MET-101", "title": "Metrics"},
    )
    assert course.status_code == 201, course.text
    course_id = course.json()["course_id"]
    lecture = client.post(
        "/api/v1/lectures",
        headers=owner_headers,
        json={"course_id": course_id, "title": "Metrics lecture"},
    )
    assert lecture.status_code == 201, lecture.text
    session = client.post(
        "/api/v1/sessions",
        headers=owner_headers,
        json={
            "course_id": course_id,
            "lecture_id": lecture.json()["lecture_id"],
            "title": "Metrics lecture",
            "mode": "in_person",
        },
    )
    assert session.status_code == 201, session.text
    session_id = session.json()["session_id"]
    ended = client.post(f"/api/v1/sessions/{session_id}/end", headers=owner_headers)
    assert ended.status_code == 200, ended.text
    return client, session_id, token, course_id


def test_missing_coverage_never_becomes_healthy_continuity():
    client, _session, base = setup()
    end(client, base)
    body = report(client, base).json()
    assert body["status"] == "insufficient_evidence"
    assert body["continuity"] is None
    assert all(
        b["coverage"] is None and b["possible_missed"] is None for b in body["buckets"]
    )


def test_hotspots_count_unique_covered_participants_and_exclude_phones():
    client, session, base = setup()
    cover_all(client, base)
    assert signal(client, session, base).status_code < 300
    signal(client, session, base, event_id="e2")
    signal(client, session, base, user="s2", event_id="e3")
    signal(client, session, base, user="s3", kind="phone_visible", event_id="e4")
    signal(
        client,
        session,
        base,
        user="s4",
        signals=["phone_visible", "head_away"],
        event_id="e5",
    )
    end(client, base)
    response = report(client, base)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["buckets"][0]["possible_missed"] == {
        "numerator": 2,
        "denominator": 5,
        "ratio": 0.4,
    }
    assert body["buckets"][0]["is_hotspot"] is True
    assert body["continuity"]["ratio"] == 0.5
    for value in ["phone_visible", "owner", "s2", "event_id", "participant_key"]:
        assert value not in response.text


def test_consent_revocation_suppresses_all_counts_and_findings():
    client, session, base = setup()
    cover_all(client, base)
    end(client, base)
    client.app.state.store.participants[session]["s5"].is_opted_in = False
    body = report(client, base).json()
    assert body["status"] == "suppressed"
    assert body["continuity"] is None and body["delivery_findings"] == []
    assert all(
        b["coverage"] is None and b["possible_missed"] is None for b in body["buckets"]
    )


def test_overlap_cannot_hide_a_coverage_gap_or_unavailability():
    client, _session, base = setup()
    cover_all(client, base)
    coverage(client, base, "s5", False, "offline", start=10_000, end=20_000)
    end(client, base)
    buckets = report(client, base).json()["buckets"]
    assert buckets[0]["status"] == "insufficient_evidence"
    assert buckets[1]["status"] == "available"


def test_coverage_retry_conflict_atomicity_and_raw_media_rejection():
    client, _session, base = setup()
    assert coverage(client, base).json()["accepted"] == 1
    assert coverage(client, base).json()["duplicates"] == 1
    response = client.post(
        base + "/coverage/batch",
        headers=headers(),
        json={
            "records": [
                {
                    "coverage_id": "new",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "is_available": True,
                },
                {
                    "coverage_id": "coverage1",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "is_available": False,
                },
            ]
        },
    )
    assert response.status_code == 409
    assert len(client.app.state.learning_state.coverage) == 1
    assert (
        client.post(
            base + "/coverage/batch",
            headers=headers(),
            json={"records": [], "raw_frame": "forbidden"},
        ).status_code
        == 422
    )


def test_authorization_and_explicit_policy_required():
    client, _session, base = setup()
    assert client.get(base + "/professor-metrics", headers=headers()).status_code == 403
    assert report(client, base).status_code == 422
    end(client, base)
    client.app.state.professor_metrics.policy = None
    assert report(client, base).status_code == 403


def test_registered_professor_can_read_own_metrics_and_other_professor_is_forbidden():
    """Membership, not a JWT course claim, authorizes the metrics report."""

    client, session_id, owner_token, _course_id = registered_professor_metrics_session()
    own_report = client.get(
        f"/api/v1/sessions/{session_id}/professor-metrics",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert own_report.status_code == 200, own_report.text
    assert own_report.json()["status"] in {"suppressed", "insufficient_evidence"}

    other = client.post(
        "/api/v1/auth/register",
        json={
            "email": "metrics-other@example.edu",
            "password": "password-123",
            "display_name": "Other Professor",
            "role": "professor",
        },
    )
    assert other.status_code == 201, other.text
    other_report = client.get(
        f"/api/v1/sessions/{session_id}/professor-metrics",
        headers={"Authorization": f"Bearer {other.json()['access_token']}"},
    )
    assert other_report.status_code == 403
