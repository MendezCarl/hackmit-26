"""Authorization-scoped cache for recovery cards.

Cache keys MUST include the authorization scope, session, effective
interval, transcript/context revision, model, prompt version, and output
schema version. The in-memory implementation is replaced by Redis once the
real integration gate is met; the interface stays unchanged.
"""

from __future__ import annotations

from typing import Protocol


class RecoveryCache(Protocol):
    """Frozen interface for the segment-summary cache."""

    def get(self, key: str) -> str | None:
        """Return the cached card id for one key, if present."""
        ...

    def set(self, key: str, card_id: str) -> None:
        """Store one card id under the given key."""
        ...


def build_cache_key(
    actor_user_id: str,
    session_id: str,
    effective_start_ms: int,
    effective_end_ms: int,
    transcript_revision: int,
    model: str,
    prompt_version: str,
    output_schema_version: str,
) -> str:
    """Build the complete authorization-scoped cache key.

    Args:
        actor_user_id: Requesting user; the scope that must never be shared.
        session_id: Session whose transcript was used.
        effective_start_ms: Effective (merged and padded) window start.
        effective_end_ms: Effective (merged and padded) window end.
        transcript_revision: Transcript revision; corrections invalidate keys.
        model: Model identifier used for generation.
        prompt_version: Prompt version used for generation.
        output_schema_version: Output schema version used for generation.

    Returns:
        A deterministic cache-key string covering every component.
    """

    return "|".join(
        (
            "scope:" + actor_user_id,
            "session:" + session_id,
            f"window:{effective_start_ms}-{effective_end_ms}",
            f"revision:{transcript_revision}",
            f"model:{model}",
            f"prompt:{prompt_version}",
            f"schema:{output_schema_version}",
        )
    )


class InMemoryRecoveryCache:
    """Process-local cache used until the Redis integration gate is met."""

    def __init__(self, entries: dict[str, str]) -> None:
        """Bind the cache to the shared store's entry map.

        Args:
            entries: Injected key-to-card-id map from the storage layer.
        """

        self._entries = entries

    def get(self, key: str) -> str | None:
        """Return the cached card id for one key, if present.

        Args:
            key: Cache key built by ``build_cache_key``.

        Returns:
            The stored card id, or ``None`` on a miss.
        """

        return self._entries.get(key)

    def set(self, key: str, card_id: str) -> None:
        """Store one card id under the given key.

        Args:
            key: Cache key built by ``build_cache_key``.
            card_id: Generated card to reuse for this scope.
        """

        self._entries[key] = card_id
