"""End-to-end synthetic demo covering the first-backend-MVP acceptance flow."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient

SETTINGS = Settings(app_env="demo")


def build_demo_client() -> TestClient:
    """Create an isolated client in explicit demo mode."""

    return TestClient(create_app(SETTINGS))


def test_demo_run_executes_full_acceptance_flow() -> None:
    """The demo run must exercise the whole recovery pipeline.

    Steps verified: session creation, transcript ingestion, missed-window
    events from enough synthetic participants, a grounded recovery card with
    valid transcript references, cache reuse on repeat, an aggregate
    professor summary, and suppression with too few participants.
    """

    client = build_demo_client()
    response = client.post("/api/v1/demo/runs")
    assert response.status_code == 201
    body = response.json()

    # 1. A synthetic lecture session exists.
    assert body["session"]["status"] == "ended"
    assert body["session"]["lecture_id"] == "demo-lecture-0001"

    # 2. Timestamped transcript chunks were ingested.
    assert len(body["transcript_chunk_ids"]) == 32

    # 3. Enough synthetic participants submitted missed-window events.
    assert len(body["submitted_event_ids"]) == 5

    # 4-5. Recovery produced a structured, grounded card.
    assert body["recovery_job"]["status"] == "completed"
    assert body["recovery_job"]["cache_status"] == "miss"
    card = body["recovery_card"]
    assert card["source_event_ids"] == ["demo-event-001"]
    assert card["source_timestamps"], "Card must carry transcript references."
    assert card["model_metadata"]["data_label"] == "synthetic"
    assert all(
        timestamp["chunk_id"].startswith("demo-chunk-")
        for timestamp in card["source_timestamps"]
    )

    # 6-7. A repeat request reuses the cached card.
    assert body["cached_recovery_job"]["cache_status"] == "hit"
    assert body["cached_recovery_job"]["card_id"] == card["card_id"]

    # 8. The professor summary is released with enough participants...
    summary = body["professor_summary"]
    assert summary["is_suppressed"] is False
    assert summary["participant_count"] >= 5
    assert summary["timeline_buckets"]
    assert summary["suggested_actions"]

    # ...and suppressed with too few participants.
    suppressed = body["professor_summary_suppressed"]
    assert suppressed["is_suppressed"] is True
    assert suppressed["timeline_buckets"] is None


def test_demo_run_uses_only_synthetic_data() -> None:
    """The demo response must be labeled synthetic throughout."""

    client = build_demo_client()
    body = client.post("/api/v1/demo/runs").json()
    assert body["recovery_card"]["model_metadata"]["provider_mode"] == "mock"
    assert body["recovery_card"]["model_metadata"]["data_label"] == "synthetic"
