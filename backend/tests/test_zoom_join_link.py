"""Zoom join-link validation and its exposure through the session contract."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import pytest
from fastapi.testclient import TestClient

from app.auth.tokens import AuthenticatedActor, issue_access_token
from app.config import Settings
from app.core.errors import AppError
from app.integrations.zoom.join_link import bind_zoom_meeting, parse_zoom_join_url
from app.main import create_app

SETTINGS = Settings(app_env="test")
RTMS_SETTINGS = Settings(
    app_env="test",
    zoom_client_id="client-1",
    zoom_client_secret="client-secret",
    zoom_webhook_secret_token="webhook-secret",
)
MEETING_ID = "123456789"
JOIN_URL = f"https://us02web.zoom.us/j/{MEETING_ID}?pwd=abcDEF123"


def auth_headers(user_id: str, role: str = "professor") -> dict[str, str]:
    """Bearer headers for a synthetic user."""

    token = issue_access_token(SETTINGS, AuthenticatedActor(user_id=user_id, role=role))
    return {"Authorization": f"Bearer {token}"}


def session_body(**overrides: object) -> dict[str, object]:
    """Minimal Zoom-mode session-creation payload."""

    body: dict[str, object] = {
        "lecture_id": "lecture-1",
        "course_id": "course-1",
        "title": "Synthetic Lecture",
        "mode": "zoom",
    }
    body.update(overrides)
    return body


@pytest.mark.parametrize(
    ("raw", "url", "meeting_number", "passcode"),
    [
        (JOIN_URL, JOIN_URL, MEETING_ID, "abcDEF123"),
        (
            "  https://zoom.us/j/12345678901/  ",
            "https://zoom.us/j/12345678901",
            "12345678901",
            None,
        ),
        (
            "https://ZOOM.COM/wc/join/123456789?uname=Alice&pwd=p-w_d.1#success",
            "https://zoom.com/wc/join/123456789?pwd=p-w_d.1",
            MEETING_ID,
            "p-w_d.1",
        ),
        (
            "https://school.zoomgov.com/my/prof.smith",
            "https://school.zoomgov.com/my/prof.smith",
            None,
            None,
        ),
    ],
)
def test_parse_zoom_join_url_normalises_valid_links(
    raw: str, url: str, meeting_number: str | None, passcode: str | None
) -> None:
    """Valid links keep only host, meeting path, and passcode."""

    link = parse_zoom_join_url(raw)
    assert link.url == url
    assert link.meeting_number == meeting_number
    assert link.passcode == passcode


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "http://zoom.us/j/123456789",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "zoommtg://zoom.us/join?confno=123456789",
        "https://evil.example/j/123456789",
        "https://zoom.us.evil.example/j/123456789",
        "https://notzoom.us/j/123456789",
        "https://user:pass@zoom.us/j/123456789",
        "https://zoom.us:8443/j/123456789",
        "https://zoom.us/j/12345",
        "https://zoom.us/rec/share/abc",
        "https://zoom.us/j/123456789?pwd=<script>",
        "https://zoom.us/j/123456789?pwd=a&pwd=b",
        "https://zoom.us/j/1234 56789",
        "https://zoom.us/j/123456789\n?pwd=x",
        "https://zoom.us/" + "j/" * 1100 + "123456789",
    ],
)
def test_parse_zoom_join_url_rejects_unsafe_links(raw: str) -> None:
    """Non-https schemes, foreign hosts, credentials, and odd paths are refused."""

    with pytest.raises(ValueError):
        parse_zoom_join_url(raw)


def test_bind_zoom_meeting_derives_id_and_detects_conflicts() -> None:
    """A link alone yields its meeting number; a conflicting id is rejected."""

    only_link = bind_zoom_meeting(None, JOIN_URL)
    assert only_link.zoom_meeting_id == MEETING_ID
    assert only_link.zoom_join_url == JOIN_URL

    with_uuid = bind_zoom_meeting("  abc==uuid  ", "https://zoom.us/my/prof")
    assert with_uuid.zoom_meeting_id == "abc==uuid"
    assert with_uuid.zoom_join_url == "https://zoom.us/my/prof"

    uuid_with_meeting_link = bind_zoom_meeting("abc==uuid", JOIN_URL)
    assert uuid_with_meeting_link.zoom_meeting_id == "abc==uuid"
    assert uuid_with_meeting_link.zoom_join_url == JOIN_URL

    neither = bind_zoom_meeting(None, "   ")
    assert neither.zoom_meeting_id is None and neither.zoom_join_url is None

    with pytest.raises(AppError) as conflict:
        bind_zoom_meeting("987654321", JOIN_URL)
    assert conflict.value.code.value == "validation_failed"

    with pytest.raises(AppError) as invalid:
        bind_zoom_meeting(None, "http://zoom.us/j/123456789")
    assert invalid.value.code.value == "validation_failed"
    assert "http://" not in invalid.value.message


def test_create_session_stores_join_link_for_members_only() -> None:
    """The link is returned to owner and joined students, never to strangers."""

    with TestClient(create_app(SETTINGS)) as client:
        created = client.post(
            "/api/v1/sessions",
            json=session_body(zoom_join_url=JOIN_URL),
            headers=auth_headers("owner-1"),
        )
        assert created.status_code == 201, created.text
        session = created.json()
        assert session["zoom_join_url"] == JOIN_URL
        assert session["zoom_meeting_id"] == MEETING_ID
        session_id = session["session_id"]

        stranger = client.get(
            f"/api/v1/sessions/{session_id}", headers=auth_headers("stranger-1", "student")
        )
        assert stranger.status_code == 403

        joined = client.post(
            f"/api/v1/sessions/{session_id}/participants",
            headers=auth_headers("student-1", "student"),
        )
        assert joined.status_code == 201, joined.text
        member = client.get(
            f"/api/v1/sessions/{session_id}", headers=auth_headers("student-1", "student")
        )
        assert member.status_code == 200
        assert member.json()["zoom_join_url"] == JOIN_URL

        rejected = client.post(
            "/api/v1/sessions",
            json=session_body(zoom_join_url="https://evil.example/j/123456789"),
            headers=auth_headers("owner-1"),
        )
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == "validation_failed"

        without_link = client.post(
            "/api/v1/sessions", json=session_body(), headers=auth_headers("owner-1")
        )
        assert without_link.json()["zoom_join_url"] is None


def test_rtms_start_accepts_join_link_and_keeps_meeting_id_in_sync() -> None:
    """Linking by URL binds the parsed meeting number for RTMS webhooks."""

    with TestClient(create_app(RTMS_SETTINGS)) as client:
        session_id = client.post(
            "/api/v1/sessions", json=session_body(), headers=auth_headers("owner-1")
        ).json()["session_id"]

        empty = client.post(
            f"/api/v1/sessions/{session_id}/zoom/rtms/start",
            json={},
            headers=auth_headers("owner-1"),
        )
        assert empty.status_code == 422

        personal_only = client.post(
            f"/api/v1/sessions/{session_id}/zoom/rtms/start",
            json={"zoom_join_url": "https://zoom.us/my/prof"},
            headers=auth_headers("owner-1"),
        )
        assert personal_only.status_code == 422
        assert personal_only.json()["error"]["code"] == "validation_failed"

        linked = client.post(
            f"/api/v1/sessions/{session_id}/zoom/rtms/start",
            json={"zoom_join_url": JOIN_URL},
            headers=auth_headers("owner-1"),
        )
        assert linked.status_code == 202, linked.text
        assert linked.json()["zoom_meeting_id"] == MEETING_ID
        assert linked.json()["status"] == "awaiting_stream"

        session = client.get(
            f"/api/v1/sessions/{session_id}", headers=auth_headers("owner-1")
        ).json()
        assert session["zoom_join_url"] == JOIN_URL
        assert session["zoom_meeting_id"] == MEETING_ID

        same_meeting = client.post(
            f"/api/v1/sessions/{session_id}/zoom/rtms/start",
            json={"zoom_meeting_id": MEETING_ID},
            headers=auth_headers("owner-1"),
        )
        assert same_meeting.status_code == 202
        session = client.get(
            f"/api/v1/sessions/{session_id}", headers=auth_headers("owner-1")
        ).json()
        assert session["zoom_join_url"] == JOIN_URL

        with_uuid = client.post(
            f"/api/v1/sessions/{session_id}/zoom/rtms/start",
            json={"zoom_meeting_id": "meeting-uuid==", "zoom_join_url": JOIN_URL},
            headers=auth_headers("owner-1"),
        )
        assert with_uuid.status_code == 202
        session = client.get(
            f"/api/v1/sessions/{session_id}", headers=auth_headers("owner-1")
        ).json()
        assert session["zoom_meeting_id"] == "meeting-uuid=="
        assert session["zoom_join_url"] == JOIN_URL

        # Pointing the session at a different meeting must not leave students
        # with a stale link to the old one.
        other_meeting = client.post(
            f"/api/v1/sessions/{session_id}/zoom/rtms/start",
            json={"zoom_meeting_id": "98765432101"},
            headers=auth_headers("owner-1"),
        )
        assert other_meeting.status_code == 202
        session = client.get(
            f"/api/v1/sessions/{session_id}", headers=auth_headers("owner-1")
        ).json()
        assert session["zoom_meeting_id"] == "98765432101"
        assert session["zoom_join_url"] is None
