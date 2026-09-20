"""WebSocket authorization, envelope delivery, and audience-isolation tests."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.auth.tokens import AuthenticatedActor, issue_access_token
from app.config import Settings
from app.main import create_app

SETTINGS = Settings(app_env="test")
LECTURE_ID = "lecture-1"


def token_for(user_id: str) -> str:
    """Mint a synthetic student token."""

    return issue_access_token(SETTINGS, AuthenticatedActor(user_id=user_id, role="student"))


def build_test_client() -> TestClient:
    """Create an isolated client with explicit test settings."""

    return TestClient(create_app(SETTINGS))


def create_session(client: TestClient, lecture_id: str = LECTURE_ID) -> str:
    """Create a synthetic session and return its id."""

    return client.post(
        "/api/v1/sessions",
        json={
            "lecture_id": lecture_id,
            "course_id": "course-1",
            "title": "Synthetic Lecture",
            "mode": "in_person",
        },
        headers={"Authorization": f"Bearer {token_for('owner-1')}"},
    ).json()["session_id"]


def ws_url(session_id: str, token: str) -> str:
    """Build a WebSocket URL with the token query parameter."""

    return f"/ws/v1/sessions/{session_id}?token={token}"


def test_unauthorized_connection_is_closed_before_delivery() -> None:
    """Invalid tokens must be rejected before any session data is sent."""

    client = build_test_client()
    session_id = create_session(client)
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(ws_url(session_id, "not-a-jwt")) as websocket,
    ):
        websocket.receive_json()


def test_non_member_connection_is_closed() -> None:
    """Members of other sessions must not subscribe to this session."""

    client = build_test_client()
    session_id = create_session(client)
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(ws_url(session_id, token_for("stranger-1"))),
    ):
        pass


def test_authorized_connection_receives_welcome_envelope() -> None:
    """The owner must receive the typed connection envelope first."""

    client = build_test_client()
    session_id = create_session(client)
    with client.websocket_connect(ws_url(session_id, token_for("owner-1"))) as websocket:
        welcome = websocket.receive_json()
        assert welcome["event_type"] == "session.connected"
        assert welcome["session_id"] == session_id
        assert welcome["schema_version"] == "1.0.0"
        assert welcome["payload"]["user_id"] == "owner-1"


def test_published_envelopes_reach_only_their_session() -> None:
    """Envelopes published for one session must not leak to another."""

    client = build_test_client()
    session_one = create_session(client, lecture_id="lecture-1")
    session_two = create_session(client, lecture_id="lecture-2")

    with client.websocket_connect(ws_url(session_one, token_for("owner-1"))) as socket_one:
        socket_one.receive_json()  # welcome
        with client.websocket_connect(
            ws_url(session_two, token_for("owner-1"))
        ) as socket_two:
            socket_two.receive_json()  # welcome

            publisher = client.app.state.event_publisher
            leaked_probe = publisher.build_envelope(
                session_one, "recovery_card.completed", {"card_id": "card-one"}
            )
            publisher.publish(leaked_probe, audience_user_id="owner-1")
            own_probe = publisher.build_envelope(
                session_two, "recovery_card.completed", {"card_id": "card-two"}
            )
            publisher.publish(own_probe, audience_user_id="owner-1")

            received = socket_two.receive_json()
            assert received["payload"]["card_id"] == "card-two"
            assert received["session_id"] == session_two
