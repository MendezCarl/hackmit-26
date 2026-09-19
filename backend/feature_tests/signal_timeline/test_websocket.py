"""WebSocket producer authorization, bounded input and safe acknowledgment tests."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from .factories import BASE, authorization, chunk

SOCKET = "/ws/v1/sessions/demo-session"


def test_websocket_ingests_and_acknowledges(client: TestClient) -> None:
    """WebSocket and REST share storage/revision semantics; retries do not duplicate."""
    with client.websocket_connect(
        SOCKET, headers=authorization("transcriber")
    ) as socket:
        payload = {
            "event_type": "transcript.batch.submitted",
            "payload": {"chunks": [chunk()]},
        }
        socket.send_json(payload)
        first = socket.receive_json()
        assert first["event_type"] == "transcript.batch.accepted"
        assert first["payload"]["accepted"] == 1
        assert first["sequence_number"] == 1
        socket.send_json(payload)
        second = socket.receive_json()
        assert second["payload"]["duplicates"] == 1
        assert second["sequence_number"] == 2
    assert (
        client.get(
            f"{BASE}/transcript?start_ms=0&end_ms=15000", headers=authorization()
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "headers", [{}, authorization(), {"Authorization": "Bearer unknown"}]
)
def test_websocket_rejects_unauthorized_producers(
    client: TestClient, headers: dict[str, str]
) -> None:
    """Do not accept a connection without host-authorized producer credentials."""
    with (
        pytest.raises(WebSocketDisconnect) as caught,
        client.websocket_connect(SOCKET, headers=headers),
    ):
        pass
    assert caught.value.code == 1008


def test_query_tokens_rejected(client: TestClient) -> None:
    """Never accept credentials in access-log-prone query strings."""
    with (
        pytest.raises(WebSocketDisconnect) as caught,
        client.websocket_connect(
            SOCKET + "?access_token=demo-transcriber",
            headers=authorization("transcriber"),
        ),
    ):
        pass
    assert caught.value.code == 1008


def test_websocket_validation_redacts_input_and_stays_usable(
    client: TestClient,
) -> None:
    """Malformed payloads yield safe errors without echoing private text."""
    with client.websocket_connect(
        SOCKET, headers=authorization("transcriber")
    ) as socket:
        socket.send_json({"raw_audio": "PRIVATE-MARKER"})
        error = socket.receive_json()
        assert error["event_type"] == "error.occurred"
        assert "PRIVATE-MARKER" not in str(error)
        socket.send_json(
            {
                "event_type": "transcript.batch.submitted",
                "payload": {"chunks": [chunk()]},
            }
        )
        assert socket.receive_json()["payload"]["accepted"] == 1


@pytest.mark.parametrize("binary, expected", [(True, 1003), (False, 1009)])
def test_websocket_binary_and_size_limits(
    client: TestClient, binary: bool, expected: int
) -> None:
    """Raw binary and oversized text frames close with documented codes."""
    with client.websocket_connect(
        SOCKET, headers=authorization("transcriber")
    ) as socket:
        if binary:
            socket.send_bytes(b"RIFF")
        else:
            socket.send_text("x" * 256001)
        with pytest.raises(WebSocketDisconnect) as caught:
            socket.receive_json()
        assert caught.value.code == expected


def test_websocket_reauthorizes_after_revocation(client: TestClient) -> None:
    """An already-open socket cannot ingest after the host revokes its credential."""
    with client.websocket_connect(
        SOCKET, headers=authorization("transcriber")
    ) as socket:
        client.app.state.lecture_feature_services.access.revoked_tokens.add(
            "demo-transcriber"
        )
        socket.send_json(
            {
                "event_type": "transcript.batch.submitted",
                "payload": {"chunks": [chunk()]},
            }
        )
        with pytest.raises(WebSocketDisconnect) as caught:
            socket.receive_json()
        assert caught.value.code == 1008
