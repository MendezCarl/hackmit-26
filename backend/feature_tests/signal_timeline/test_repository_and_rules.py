"""Atomic repository adapters, deterministic signal rules and safe feature registration."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from app.signals.models import SignalEvent, SignalRules
from app.signals.service import build_missed_windows
from app.timeline.application import create_app, register_features
from app.timeline.contracts import FeatureError
from app.timeline.demo import build_demo_services
from app.timeline.repository import (
    MemorySessionRepository,
    MongoSessionRepository,
    SessionState,
    mutate_session,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from .factories import signal


def test_rule_merging_and_explicit_feedback() -> None:
    """Merge overlapping candidates; explicit confirmation overrides demo heuristics."""
    events = [
        SignalEvent.model_validate(signal("one")),
        SignalEvent.model_validate(
            signal("two", start_ms=10000, end_ms=17000, signals=["head_away"])
        ),
        SignalEvent.model_validate(
            signal("dismissed", start_ms=20000, end_ms=28000, user_confirmed=False)
        ),
        SignalEvent.model_validate(
            signal(
                "confirmed",
                start_ms=30000,
                end_ms=30100,
                confidence=0.1,
                user_confirmed=True,
            )
        ),
    ]
    windows = build_missed_windows(events, SignalRules())
    assert [(window.start_ms, window.end_ms) for window in windows] == [
        (5000, 17000),
        (30000, 30100),
    ]
    assert windows[0].source_event_ids == ["one", "two"]
    assert windows[0].signals == ["face_absent", "head_away"]


def test_memory_compare_and_swap_and_delete() -> None:
    """Detached snapshots prevent accidental changes; stale writes cannot win."""

    async def exercise() -> None:
        repository = MemorySessionRepository()
        first = await repository.load("session")
        first.revision = 1
        assert await repository.replace(first, 0)
        stale = SessionState(session_id="session", revision=2)
        assert not await repository.replace(stale, 0)
        first.revision = 999
        assert (await repository.load("session")).revision == 1
        await repository.delete("session")
        assert (await repository.load("session")).revision == 0

    asyncio.run(exercise())


def test_mongo_compare_and_swap_contract() -> None:
    """Use actual Motor method shapes; duplicate _id races are retryable conflicts."""
    collection = Mock()
    collection.find_one = AsyncMock(
        return_value={"_id": "session", "session_id": "session", "revision": 1}
    )
    collection.replace_one = AsyncMock(
        return_value=Mock(matched_count=1, upserted_id=None)
    )
    collection.delete_one = AsyncMock()
    repository = MongoSessionRepository(collection)
    state = asyncio.run(repository.load("session"))
    assert state.revision == 1
    state.revision = 2
    assert asyncio.run(repository.replace(state, 1))
    assert collection.replace_one.call_args.args[0] == {"_id": "session", "revision": 1}
    assert collection.replace_one.call_args.kwargs["upsert"] is False
    collection.replace_one.side_effect = DuplicateKeyError("synthetic race")
    assert not asyncio.run(repository.replace(state, 0))
    asyncio.run(repository.delete("session"))
    collection.delete_one.assert_awaited_once_with({"_id": "session"})


def test_conflict_retries_are_bounded() -> None:
    """Repeated storage conflicts produce a typed error rather than hanging."""
    repository = Mock()
    repository.load = AsyncMock(
        side_effect=lambda session: SessionState(session_id=session)
    )
    repository.replace = AsyncMock(return_value=False)
    with pytest.raises(FeatureError) as caught:
        asyncio.run(mutate_session(repository, "session", lambda state: (True, True)))
    assert caught.value.code == "write_conflict"
    assert repository.replace.await_count == 5


def test_production_registration_excludes_demo_and_simulation() -> None:
    """Registration alone never adds fixture lifecycle or fake Zoom transport routes."""
    app = FastAPI()
    register_features(app, build_demo_services())
    with TestClient(app) as client:
        assert client.post("/api/v1/sessions/demo-session/demo/end").status_code == 404
        assert (
            client.post(
                "/api/v1/sessions/demo-session/zoom/simulated-transcript-chunks"
            ).status_code
            == 404
        )
    with pytest.raises(RuntimeError, match="already registered"):
        register_features(app, build_demo_services())


def test_factory_requires_explicit_demo_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default startup must not accidentally serve known demo credentials."""
    monkeypatch.delenv("LUMINA_DEMO", raising=False)
    with pytest.raises(RuntimeError, match="LUMINA_DEMO"):
        create_app()
