"""Cost accounting for provider usage with explicit synthetic labels."""

from __future__ import annotations

from app.contracts.models import CostMetrics


class CostLedger:
    """In-memory ledger for measured provider usage per recovery job.

    Mock provider usage is always labeled ``synthetic`` and never implies
    real savings. Cache hits are recorded as avoiding an additional
    generation call rather than as provider savings.
    """

    def __init__(self) -> None:
        """Create an empty ledger."""

        self._entries: list[CostMetrics] = []

    def record(self, entry: CostMetrics) -> None:
        """Append one usage record.

        Args:
            entry: Measured or synthetic usage for one recovery job.
        """

        self._entries.append(entry)

    def for_session(self, session_id: str) -> list[CostMetrics]:
        """Return every usage record recorded for one session.

        Args:
            session_id: Session whose records are needed.

        Returns:
            Usage records in recording order.
        """

        return [entry for entry in self._entries if entry.session_id == session_id]
