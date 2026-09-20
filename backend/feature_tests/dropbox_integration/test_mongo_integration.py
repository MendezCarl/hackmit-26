"""Explicit opt-in local Mongo contract test; never accesses a live provider account."""

import asyncio
import os
from uuid import uuid4

import pytest

from app.timeline.repository import MongoSessionRepository, SessionState


@pytest.mark.skipif(
    not os.environ.get("LUMINA_TEST_MONGO_URI"),
    reason="Opt-in: set LUMINA_TEST_MONGO_URI for a disposable local Mongo server.",
)
def test_real_mongo_atomic_updates_and_deletion() -> None:
    """Exercise insert, CAS races, validated reads and cleanup in a fresh test database."""
    from motor.motor_asyncio import AsyncIOMotorClient

    async def exercise() -> None:
        client = AsyncIOMotorClient(
            os.environ["LUMINA_TEST_MONGO_URI"], serverSelectionTimeoutMS=3000
        )
        database_name = "lumina_lecture_features_test_" + uuid4().hex
        try:
            repository = MongoSessionRepository(client[database_name]["sessions"])
            state = SessionState(session_id="synthetic-session", revision=1)
            outcomes = await asyncio.gather(
                repository.replace(state, 0), repository.replace(state, 0)
            )
            assert sorted(outcomes) == [False, True]
            assert (await repository.load("synthetic-session")).revision == 1
            updated = state.model_copy(update={"revision": 2})
            assert await repository.replace(updated, 1)
            assert not await repository.replace(updated, 1)
            await repository.delete("synthetic-session")
            assert (await repository.load("synthetic-session")).revision == 0
        finally:
            await client.drop_database(database_name)
            client.close()

    asyncio.run(exercise())
