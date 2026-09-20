"""Shared professor-report interface; consumers can inject a threshold-safe fake."""

from typing import Protocol

from app.auth.tokens import AuthenticatedActor
from app.contracts.learning import ProfessorMetrics


class MetricsReader(Protocol):
    """Read current policy-filtered evidence without depending on its implementation."""

    def report(self, actor: AuthenticatedActor, session_id: str) -> ProfessorMetrics:
        """Return the authorized report or raise AppError for denied/unavailable access."""
        ...
