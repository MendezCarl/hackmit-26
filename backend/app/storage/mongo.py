"""Optional MongoDB-backed mappings for the shared backend store."""

from __future__ import annotations

from collections.abc import Callable, Iterator, MutableMapping
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from app.contracts.models import (
    ConsentSettings,
    Course,
    Lecture,
    LectureSession,
    RecoveryCard,
    RecoveryJob,
    SignalEvent,
    TranscriptChunk,
)
from app.storage.in_memory import (
    CardRecord,
    EventRecord,
    InMemoryStore,
    ParticipantRecord,
    UserRecord,
)

if TYPE_CHECKING:
    from pymongo.collection import Collection


class MongoCollectionMapping[T](MutableMapping[str, T]):
    """Mapping facade that stores one value per MongoDB document."""

    def __init__(
        self,
        collection: Collection,
        encode: Callable[[T], Any],
        decode: Callable[[Any], T],
    ) -> None:
        """Bind a Mongo collection and value codecs.

        Args:
            collection: PyMongo collection receiving mapping documents.
            encode: Converts one mapping value to a JSON-compatible dictionary.
            decode: Converts a stored dictionary back to the mapping value.
        """

        self._collection = collection
        self._encode = encode
        self._decode = decode

    def __getitem__(self, key: str) -> T:
        """Return one decoded value or raise ``KeyError`` when absent."""
        document = self._collection.find_one({"_id": key})
        if document is None:
            raise KeyError(key)
        return self._decode(document["value"])

    def __setitem__(self, key: str, value: T) -> None:
        """Replace or insert one encoded value under ``key``."""
        self._collection.replace_one(
            {"_id": key},
            {"_id": key, "value": self._encode(value)},
            upsert=True,
        )

    def __delitem__(self, key: str) -> None:
        """Delete one value or raise ``KeyError`` when absent."""
        result = self._collection.delete_one({"_id": key})
        if result.deleted_count == 0:
            raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        """Iterate over mapping keys using an ``_id``-only projection."""
        for document in self._collection.find({}, {"_id": 1}):
            yield document["_id"]

    def __len__(self) -> int:
        """Return the number of stored mapping values."""
        return self._collection.count_documents({})

    def __contains__(self, key: object) -> bool:
        """Return whether MongoDB contains a document for ``key``."""
        return self._collection.find_one({"_id": key}, {"_id": 1}) is not None


def _encode_model[PydanticModel: BaseModel](value: PydanticModel) -> dict[str, Any]:
    """Encode a Pydantic model using JSON-compatible field values."""
    return value.model_dump(mode="json")


def _decode_model[PydanticModel: BaseModel](
    model: type[PydanticModel],
) -> Callable[[Any], PydanticModel]:
    """Build a decoder for one Pydantic model type."""
    return model.model_validate


def _encode_user(value: UserRecord) -> dict[str, Any]:
    """Encode a user dataclass and its nested consent model."""
    encoded = asdict(value)
    encoded["consent"] = value.consent.model_dump(mode="json")
    return encoded


def _decode_user(value: dict[str, Any]) -> UserRecord:
    """Decode a user dataclass and its nested consent model."""
    return UserRecord(
        user_id=value["user_id"],
        email=value["email"],
        password_hash=value["password_hash"],
        role=value["role"],
        display_name=value["display_name"],
        created_at=value["created_at"],
        consent=ConsentSettings.model_validate(value["consent"]),
    )


def _encode_participant(value: ParticipantRecord) -> dict[str, Any]:
    """Encode one participant dataclass."""
    return asdict(value)


def _decode_participant(value: dict[str, Any]) -> ParticipantRecord:
    """Decode one participant dataclass."""
    return ParticipantRecord(**value)


def _encode_event(value: EventRecord) -> dict[str, Any]:
    """Encode an event record with its nested Pydantic event."""
    return {
        "event": value.event.model_dump(mode="json"),
        "submitted_by": value.submitted_by,
    }


def _decode_event(value: dict[str, Any]) -> EventRecord:
    """Decode an event record with its nested Pydantic event."""
    return EventRecord(
        event=SignalEvent.model_validate(value["event"]),
        submitted_by=value["submitted_by"],
    )


def _encode_card(value: CardRecord) -> dict[str, Any]:
    """Encode a card record with its nested Pydantic card."""
    return {
        "card": value.card.model_dump(mode="json"),
        "owner_user_id": value.owner_user_id,
    }


def _decode_card(value: dict[str, Any]) -> CardRecord:
    """Decode a card record with its nested Pydantic card."""
    return CardRecord(
        card=RecoveryCard.model_validate(value["card"]),
        owner_user_id=value["owner_user_id"],
    )


def _encode_participants(
    value: dict[str, ParticipantRecord],
) -> dict[str, Any]:
    """Encode all participant records for one session."""
    return {key: _encode_participant(record) for key, record in value.items()}


def _decode_participants(value: dict[str, Any]) -> dict[str, ParticipantRecord]:
    """Decode all participant records for one session."""
    return {key: _decode_participant(record) for key, record in value.items()}


def _encode_events(value: list[EventRecord]) -> list[dict[str, Any]]:
    """Encode all event records for one session."""
    return [_encode_event(record) for record in value]


def _decode_events(value: list[dict[str, Any]]) -> list[EventRecord]:
    """Decode all event records for one session."""
    return [_decode_event(record) for record in value]


def _encode_transcript_chunks(value: list[TranscriptChunk]) -> list[dict[str, Any]]:
    """Encode all transcript chunks for one session."""
    return [_encode_model(chunk) for chunk in value]


def _decode_transcript_chunks(value: list[dict[str, Any]]) -> list[TranscriptChunk]:
    """Decode all transcript chunks for one session."""
    return [TranscriptChunk.model_validate(chunk) for chunk in value]


def _model_mapping[PydanticModel: BaseModel](
    collection: Collection,
    model: type[PydanticModel],
) -> MongoCollectionMapping[PydanticModel]:
    """Create a Mongo mapping for one Pydantic model type."""
    return MongoCollectionMapping(
        collection,
        _encode_model,
        _decode_model(model),
    )


def build_mongo_store(database: Any) -> InMemoryStore:
    """Build the shared store container from a Mongo-like database.

    Args:
        database: Database-like object whose named collections support mapping
            operations.

    Returns:
        An ``InMemoryStore`` dataclass populated with Mongo-backed mappings.
    """
    return InMemoryStore(
        users=MongoCollectionMapping(database["users"], _encode_user, _decode_user),
        courses=_model_mapping(database["courses"], Course),
        lectures=_model_mapping(database["lectures"], Lecture),
        sessions=_model_mapping(database["sessions"], LectureSession),
        participants=MongoCollectionMapping(
            database["participants"], _encode_participants, _decode_participants
        ),
        events=MongoCollectionMapping(database["events"], _encode_events, _decode_events),
        transcript_chunks=MongoCollectionMapping(
            database["transcript_chunks"],
            _encode_transcript_chunks,
            _decode_transcript_chunks,
        ),
        recovery_jobs=_model_mapping(database["recovery_jobs"], RecoveryJob),
        recovery_cards=MongoCollectionMapping(
            database["recovery_cards"], _encode_card, _decode_card
        ),
        recovery_cache=MongoCollectionMapping(
            database["recovery_cache"],
            lambda value: value,
            lambda value: value,
        ),
        recovery_idempotency=MongoCollectionMapping(
            database["recovery_idempotency"],
            lambda value: value,
            lambda value: value,
        ),
    )


def create_mongo_store(uri: str, database_name: str) -> InMemoryStore:
    """Create the shared store container backed by MongoDB mappings.

    Args:
        uri: MongoDB connection URI; it is never included in errors.
        database_name: MongoDB database containing the store collections.

    Returns:
        An ``InMemoryStore`` dataclass populated with Mongo-backed mappings.

    Raises:
        RuntimeError: If PyMongo is unavailable, the database cannot be reached,
            or the URI does not carry credentials that can read the database.
    """
    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise RuntimeError(
            "MONGODB_URI is set but pymongo is not installed; install the mongodb extra."
        ) from exc

    try:
        client: Any = MongoClient(uri, serverSelectionTimeoutMS=5000)
        database = client[database_name]
        database["users"].count_documents({})
    except Exception:  # noqa: BLE001 - redact connection details
        raise RuntimeError(
            "Could not connect to MongoDB or the MONGODB_URI credentials cannot"
            " read the database (check the username:password in the URI)."
        ) from None

    return build_mongo_store(database)
