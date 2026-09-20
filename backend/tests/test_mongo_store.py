"""Mongo mapping tests using an in-process collection fake."""

from typing import Any

import pytest
from new_plan.fixtures import headers, setup

from app.config import Settings
from app.contracts.models import (
    ConsentSettings,
    Course,
    TranscriptChunk,
    TranscriptSource,
)
from app.main import create_app
from app.storage.in_memory import (
    InMemoryStore,
    ParticipantRecord,
    UserRecord,
)
from app.storage.mongo import MongoCollectionMapping, create_mongo_store


class DeleteResult:
    """Minimal delete result returned by the collection fake."""

    def __init__(self, deleted_count: int) -> None:
        self.deleted_count = deleted_count


class FakeCollection:
    """Small pymongo collection substitute backed by a dictionary."""

    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}

    def find_one(
        self, query: dict[str, object], projection: dict[str, int] | None = None
    ) -> dict[str, Any] | None:
        """Find one document by its Mongo identifier."""
        document = self.documents.get(query["_id"])
        if document is None:
            return None
        if projection is not None:
            return {"_id": document["_id"]}
        return document

    def replace_one(
        self,
        query: dict[str, object],
        document: dict[str, Any],
        *,
        upsert: bool,
    ) -> None:
        """Replace one document, honoring the mapping's upsert request."""
        assert upsert is True
        self.documents[query["_id"]] = document

    def delete_one(self, query: dict[str, object]) -> DeleteResult:
        """Delete one document by its Mongo identifier."""
        deleted = int(self.documents.pop(query["_id"], None) is not None)
        return DeleteResult(deleted)

    def find(
        self, _query: dict[str, object], projection: dict[str, int]
    ) -> list[dict[str, Any]]:
        """Return projected identifiers for iteration."""
        assert projection == {"_id": 1}
        return [{"_id": document["_id"]} for document in self.documents.values()]

    def count_documents(self, _query: dict[str, object]) -> int:
        """Return the number of stored documents."""
        return len(self.documents)


def test_mapping_roundtrips_models_dataclasses_lists_and_dicts() -> None:
    """Mappings encode and decode each supported nested value shape."""
    course_collection = FakeCollection()
    courses = MongoCollectionMapping(
        course_collection,
        lambda value: value.model_dump(mode="json"),
        Course.model_validate,
    )
    course = Course(
        course_id="course-1",
        owner_id="professor-1",
        title="Algorithms",
        code="CS101",
        created_at="now",
    )
    courses["course-1"] = course
    assert courses["course-1"] == course
    assert "course-1" in courses
    assert len(courses) == 1

    user_collection = FakeCollection()
    users = MongoCollectionMapping(
        user_collection,
        lambda value: {
            "user_id": value.user_id,
            "consent": value.consent.model_dump(mode="json"),
        },
        lambda value: UserRecord(
            user_id=value["user_id"],
            email="student@example.com",
            password_hash="hash",
            role="student",
            display_name="Student",
            created_at="now",
            consent=ConsentSettings.model_validate(value["consent"]),
        ),
    )
    user = UserRecord(
        user_id="user-1",
        email="student@example.com",
        password_hash="hash",
        role="student",
        display_name="Student",
        created_at="now",
        consent=ConsentSettings(analytics_opt_in=True),
    )
    users["user-1"] = user
    assert users["user-1"] == user

    chunk_collection = FakeCollection()
    chunks = MongoCollectionMapping(
        chunk_collection,
        lambda value: {"items": [chunk.model_dump(mode="json") for chunk in value]},
        lambda value: [TranscriptChunk.model_validate(chunk) for chunk in value["items"]],
    )
    chunk = TranscriptChunk(
        chunk_id="chunk-1",
        session_id="session-1",
        start_ms=0,
        end_ms=1000,
        text="Synthetic transcript.",
        source=TranscriptSource.LOCAL_TRANSCRIPTION,
    )
    chunks["session-1"] = [chunk]
    assert chunks["session-1"] == [chunk]

    participant_collection = FakeCollection()
    participants = MongoCollectionMapping(
        participant_collection,
        lambda value: {
            key: {
                "user_id": record.user_id,
                "is_opted_in": record.is_opted_in,
                "joined_at": record.joined_at,
            }
            for key, record in value.items()
        },
        lambda value: {key: ParticipantRecord(**record) for key, record in value.items()},
    )
    participant = ParticipantRecord(user_id="user-1", joined_at="now")
    participants["session-1"] = {"user-1": participant}
    assert participants["session-1"] == {"user-1": participant}


def test_mapping_container_methods_and_missing_keys() -> None:
    """MutableMapping defaults provide setdefault, values, and items."""
    collection = FakeCollection()
    mapping = MongoCollectionMapping(
        collection,
        lambda value: {"value": value},
        lambda value: value["value"],
    )
    assert mapping.setdefault("key", "first") == "first"
    assert mapping.setdefault("key", "second") == "first"
    assert list(mapping.values()) == ["first"]
    assert list(mapping.items()) == [("key", "first")]
    with pytest.raises(KeyError):
        mapping["missing"]
    with pytest.raises(KeyError):
        del mapping["missing"]
    del mapping["key"]
    assert "key" not in mapping


def test_create_app_without_mongodb_uri_uses_in_memory_store() -> None:
    """The default app composition remains process-local without a URI."""
    app = create_app(Settings(app_env="test", mongodb_uri=None))

    assert isinstance(app.state.store, InMemoryStore)


def test_invalid_mongodb_uri_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mongo connection failures do not expose the configured URI."""

    class FailingAdmin:
        def command(self, _name: str) -> None:
            raise RuntimeError("mongodb://secret.example.invalid")

    class FailingClient:
        admin = FailingAdmin()

        def __init__(self, _uri: str, *, serverSelectionTimeoutMS: int) -> None:
            assert serverSelectionTimeoutMS == 5000

    import pymongo

    monkeypatch.setattr(pymongo, "MongoClient", FailingClient)
    uri = "mongodb://secret.example.invalid"
    with pytest.raises(RuntimeError) as error:
        create_mongo_store(uri, "bloom")
    assert uri not in str(error.value)


def test_consent_revocation_preserves_cache_mapping() -> None:
    """Revocation mutates the shared cache mapping instead of replacing it."""
    client, _session, base = setup()
    response = client.post(
        base + "/recovery/jobs",
        headers=headers(),
        json={"start_ms": 0, "end_ms": 30_000},
    )
    assert response.status_code == 202, response.text
    cache = client.app.state.store.recovery_cache
    assert len(cache) == 1

    response = client.put(
        base + "/external-text-consent",
        headers=headers(),
        json={"provider": "openai", "is_allowed": False},
    )

    assert response.status_code == 200, response.text
    assert client.app.state.store.recovery_cache is cache
    assert len(cache) == 0
