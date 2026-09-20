"""Bounded, injected feature repositories for a single-process MVP.

These are intentionally not durable; the host must replace them before scaling.
"""

from dataclasses import dataclass, field
from threading import RLock

from app.contracts.learning import (
    DeliveryEvent,
    EvidenceCoverage,
    RecommendationReport,
    RecommendationReview,
)


@dataclass
class LearningState:
    """Per-application state; lock makes batch validation and writes atomic."""

    coverage: dict[tuple[str, str, str], EvidenceCoverage] = field(default_factory=dict)
    delivery: dict[tuple[str, str], DeliveryEvent] = field(default_factory=dict)
    external_consent: set[tuple[str, str, str]] = field(default_factory=set)
    reviews: dict[tuple[str, str, str, int], RecommendationReview] = field(
        default_factory=dict
    )
    lock: RLock = field(default_factory=RLock)
    recommendation_runs: dict[tuple[str, str, str], RecommendationReport] = field(
        default_factory=dict
    )
    maximum_records: int = 10_000

    def delete_session(self, session_id: str) -> None:
        """Erase all feature-owned records for a host-authorized session deletion."""
        with self.lock:
            self.recommendation_runs = {
                k: v for k, v in self.recommendation_runs.items() if k[0] != session_id
            }
            self.coverage = {k: v for k, v in self.coverage.items() if k[0] != session_id}
            self.delivery = {k: v for k, v in self.delivery.items() if k[0] != session_id}
            self.external_consent = {k for k in self.external_consent if k[0] != session_id}
            self.reviews = {k: v for k, v in self.reviews.items() if k[0] != session_id}
