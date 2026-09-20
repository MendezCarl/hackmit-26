"""Private event audiences are narrower than session membership."""

from app.ws.publisher import WebSocketEventPublisher


def test_private_events_require_explicit_actor_and_do_not_reach_other_members():
    publisher = WebSocketEventPublisher()
    own = publisher.subscribe("session", "s1")
    other = publisher.subscribe("session", "s2")
    event = publisher.build_envelope(
        "session", "recovery_card.completed", {"card_id": "card"}
    )
    publisher.publish(event)
    assert own.empty() and other.empty()
    publisher.publish(event, audience_user_id="s1")
    assert own.get_nowait() == event and other.empty()


def test_ingested_signal_notification_reaches_only_its_submitter():
    """Real ingestion supplies an explicit audience rather than dropping or broadcasting."""
    from .fixtures import setup, signal

    client, session, base = setup()
    publisher = client.app.state.event_publisher
    own = publisher.subscribe(session, "owner")
    other = publisher.subscribe(session, "s2")
    assert signal(client, session, base).status_code == 202
    assert own.get_nowait().payload["accepted_event_ids"] == ["e1"]
    assert other.empty()
