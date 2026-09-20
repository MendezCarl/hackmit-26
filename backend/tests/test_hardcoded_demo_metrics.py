"""Hardcoded demo-metrics endpoint tests (gating, labeling, determinism)."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

DEMO_SETTINGS = Settings(app_env="demo")
TEST_SETTINGS = Settings(app_env="test")
DEVELOPMENT_SETTINGS = Settings(app_env="development")

EXPECTED_VALUES = {
    "recovery": {
        "total_missed_windows": 52,
        "recovered_missed_windows": 47,
        "recovery_rate": 0.904,
    },
    "token_savings": {
        "selected_context_tokens_per_card": 1710,
        "full_context_baseline_tokens": 10650,
        "token_savings_rate": 0.840,
    },
    "cache": {"cache_hit_rate": 0.62, "cached_cards_served": 29},
    "professor_participation": {
        "released_summaries": 12,
        "suppressed_summaries": 3,
        "average_participants_per_released_summary": 18,
        "minimum_group_size": 5,
    },
    "latency": {
        "average_recovery_latency_ms": 1240,
        "p95_recovery_latency_ms": 2100,
    },
}


def test_demo_mode_returns_hardcoded_metrics() -> None:
    """The endpoint must serve the exact synthetic values in demo mode."""

    client = TestClient(create_app(DEMO_SETTINGS))
    response = client.get("/api/v1/demo/metrics")
    assert response.status_code == 200
    body = response.json()

    assert body["data_label"] == "synthetic_demo"
    assert body["is_live_measured"] is False
    assert "hardcoded synthetic" in body["disclaimer"].lower()
    for section, expected in EXPECTED_VALUES.items():
        assert body[section] == expected, section
    assert "no-store" in response.headers["cache-control"]


def test_metrics_are_identical_on_every_call() -> None:
    """Hardcoded metrics must not vary between requests."""

    client = TestClient(create_app(DEMO_SETTINGS))
    first = client.get("/api/v1/demo/metrics").json()
    second = client.get("/api/v1/demo/metrics").json()
    assert first == second


def test_metrics_are_unavailable_outside_demo_mode() -> None:
    """Development and production must never see the demo numbers."""

    client = TestClient(create_app(DEVELOPMENT_SETTINGS))
    response = client.get("/api/v1/demo/metrics")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "demo_unavailable"


def test_metrics_are_readable_in_test_mode_for_verification() -> None:
    """Test mode may read the payload so CI can verify the labels."""

    client = TestClient(create_app(TEST_SETTINGS))
    response = client.get("/api/v1/demo/metrics")
    assert response.status_code == 200
    assert response.json()["data_label"] == "synthetic_demo"
