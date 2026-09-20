"""Hardcoded synthetic demo metrics for judge-facing presentation.

Every value in this module is a fixed, clearly labeled synthetic number used
only in explicit demo mode. None of these values are live measurements, and
this module must never be imported by production code paths. The endpoint
serving them is gated on ``APP_ENV in (demo, test)`` and always sets
``data_label`` to ``synthetic_demo`` so the numbers can never be presented as
real, measured usage.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SYNTHETIC_DEMO_LABEL = "synthetic_demo"

HARDCODED_METRICS_DISCLAIMER = (
    "Every value on this endpoint is a hardcoded synthetic demo number. "
    "These are not live measured results and must never be presented as "
    "real usage, real savings, or real student data."
)

# --- Hardcoded judge-facing numbers ---------------------------------------
# Recovery of missed windows.
TOTAL_MISSED_WINDOWS = 52
RECOVERED_MISSED_WINDOWS = 47
RECOVERY_RATE = 0.904

# Token cost savings of selected-context retrieval vs a full-context baseline.
SELECTED_CONTEXT_TOKENS_PER_CARD = 1_710
FULL_CONTEXT_BASELINE_TOKENS = 10_650
TOKEN_SAVINGS_RATE = 0.840

# Cache reuse across repeated recovery requests.
CACHE_HIT_RATE = 0.62
CACHED_CARDS_SERVED = 29

# Anonymous professor-summary participation (threshold-suppressed groups
# are excluded from released summaries).
RELEASED_SUMMARIES = 12
SUPPRESSED_SUMMARIES = 3
AVERAGE_PARTICIPANTS_PER_RELEASED_SUMMARY = 18
MINIMUM_GROUP_SIZE = 5

# Recovery latency.
AVERAGE_RECOVERY_LATENCY_MS = 1_240
P95_RECOVERY_LATENCY_MS = 2_100


class HardcodedRecoveryMetrics(BaseModel):
    """Synthetic missed-window recovery counts."""

    total_missed_windows: int = Field(
        ge=0, description="Hardcoded synthetic count of detected missed windows."
    )
    recovered_missed_windows: int = Field(
        ge=0, description="Hardcoded synthetic count of recovered missed windows."
    )
    recovery_rate: float = Field(
        ge=0,
        le=1,
        description="Hardcoded synthetic fraction of missed windows recovered.",
    )


class HardcodedTokenSavingsMetrics(BaseModel):
    """Synthetic token-cost illustration vs a full-context baseline."""

    selected_context_tokens_per_card: int = Field(
        ge=0,
        description="Hardcoded synthetic input tokens for selected-context recovery.",
    )
    full_context_baseline_tokens: int = Field(
        ge=0,
        description="Hardcoded synthetic full-transcript baseline tokens.",
    )
    token_savings_rate: float = Field(
        ge=0,
        le=1,
        description="Hardcoded synthetic fraction of tokens avoided vs baseline.",
    )


class HardcodedCacheMetrics(BaseModel):
    """Synthetic cache-reuse numbers."""

    cache_hit_rate: float = Field(
        ge=0,
        le=1,
        description="Hardcoded synthetic fraction of requests served from cache.",
    )
    cached_cards_served: int = Field(
        ge=0, description="Hardcoded synthetic count of cards served from cache."
    )


class HardcodedProfessorParticipationMetrics(BaseModel):
    """Synthetic anonymous aggregation-participation counts."""

    released_summaries: int = Field(
        ge=0, description="Hardcoded synthetic professor summaries released."
    )
    suppressed_summaries: int = Field(
        ge=0, description="Hardcoded synthetic summaries suppressed for privacy."
    )
    average_participants_per_released_summary: int = Field(
        ge=0,
        description="Hardcoded synthetic unique participating users per summary.",
    )
    minimum_group_size: int = Field(
        ge=1, description="Privacy threshold used by the demo configuration."
    )


class HardcodedLatencyMetrics(BaseModel):
    """Synthetic recovery latency numbers."""

    average_recovery_latency_ms: int = Field(
        ge=0, description="Hardcoded synthetic average recovery latency in ms."
    )
    p95_recovery_latency_ms: int = Field(
        ge=0, description="Hardcoded synthetic 95th-percentile latency in ms."
    )


class HardcodedDemoMetrics(BaseModel):
    """Judge-facing demo metrics; every field is hardcoded synthetic data."""

    data_label: Literal["synthetic_demo"] = Field(
        default=SYNTHETIC_DEMO_LABEL,
        description="Always ``synthetic_demo``; these are not live measurements.",
    )
    is_live_measured: Literal[False] = Field(
        default=False,
        description="Always ``false``; no live provider or usage data is involved.",
    )
    disclaimer: str = Field(
        description="Explicit statement that every value is synthetic."
    )
    recovery: HardcodedRecoveryMetrics
    token_savings: HardcodedTokenSavingsMetrics
    cache: HardcodedCacheMetrics
    professor_participation: HardcodedProfessorParticipationMetrics
    latency: HardcodedLatencyMetrics


def build_hardcoded_demo_metrics() -> HardcodedDemoMetrics:
    """Build the fixed, clearly labeled synthetic metrics payload.

    Returns:
        The same hardcoded values on every call; no state, services, or
        providers are consulted.
    """

    return HardcodedDemoMetrics(
        data_label=SYNTHETIC_DEMO_LABEL,
        is_live_measured=False,
        disclaimer=HARDCODED_METRICS_DISCLAIMER,
        recovery=HardcodedRecoveryMetrics(
            total_missed_windows=TOTAL_MISSED_WINDOWS,
            recovered_missed_windows=RECOVERED_MISSED_WINDOWS,
            recovery_rate=RECOVERY_RATE,
        ),
        token_savings=HardcodedTokenSavingsMetrics(
            selected_context_tokens_per_card=SELECTED_CONTEXT_TOKENS_PER_CARD,
            full_context_baseline_tokens=FULL_CONTEXT_BASELINE_TOKENS,
            token_savings_rate=TOKEN_SAVINGS_RATE,
        ),
        cache=HardcodedCacheMetrics(
            cache_hit_rate=CACHE_HIT_RATE,
            cached_cards_served=CACHED_CARDS_SERVED,
        ),
        professor_participation=HardcodedProfessorParticipationMetrics(
            released_summaries=RELEASED_SUMMARIES,
            suppressed_summaries=SUPPRESSED_SUMMARIES,
            average_participants_per_released_summary=(
                AVERAGE_PARTICIPANTS_PER_RELEASED_SUMMARY
            ),
            minimum_group_size=MINIMUM_GROUP_SIZE,
        ),
        latency=HardcodedLatencyMetrics(
            average_recovery_latency_ms=AVERAGE_RECOVERY_LATENCY_MS,
            p95_recovery_latency_ms=P95_RECOVERY_LATENCY_MS,
        ),
    )
