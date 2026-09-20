"""Synthetic checks for closing open intervals and posting derived events."""

import json
import sys
from pathlib import Path

import httpx
import numpy as np
import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from app.contracts.learning import DeliveryEvent  # noqa: E402
from app.local_ml.vision import Detection, Region, VisionPolicy, VisionWorker  # noqa: E402
from scripts.post_delivery_events import (  # noqa: E402
    MAX_EVENTS_PER_BATCH,
    load_events,
    post_events,
)


class ScriptedDetector:
    """Synthetic detector whose presence is switched by the test."""

    def __init__(self) -> None:
        self.present = False

    def detect(self, frame):
        if self.present:
            return [Detection(x1=0, y1=0, x2=1, y2=1, confidence=0.9)]
        return []


def synthetic_frame():
    return np.full((180, 320, 3), 127, dtype=np.uint8)


def make_worker(detector):
    return VisionWorker(detector, VisionPolicy(), Region(x1=0, y1=0, x2=1, y2=1))


def make_event(index: int) -> DeliveryEvent:
    return DeliveryEvent.model_validate(
        {
            "event_id": f"delivery_{index}",
            "signal_type": "presenter_out_of_frame",
            "start_ms": index * 10_000,
            "end_ms": index * 10_000 + 4_000,
            "confidence": 0.5,
            "detector_version": "local-vision-v1",
            "evidence": {
                "sample_count": 5,
                "positive_sample_count": 4,
                "performance_profile": "low_power",
            },
        }
    )


def test_flush_emits_interval_still_open_at_end_of_observation():
    vision = make_worker(ScriptedDetector())
    for timestamp in [0, 1000, 2000, 3000, 4000]:
        assert vision.observe(synthetic_frame(), timestamp) == []
    events = vision.flush(4000)
    assert len(events) == 1
    assert events[0].signal_type == "presenter_out_of_frame"
    assert (events[0].start_ms, events[0].end_ms) == (0, 4000)
    assert vision.active == {}


def test_flush_drops_interval_shorter_than_minimum_duration():
    vision = make_worker(ScriptedDetector())
    vision.observe(synthetic_frame(), 0)
    vision.observe(synthetic_frame(), 1000)
    assert vision.flush(1000) == []
    assert vision.active == {}


def test_load_events_reads_worker_lines_and_runner_summaries(tmp_path):
    path = tmp_path / "events.jsonl"
    worker_line = make_event(1).model_dump(mode="json")
    summary_line = {
        "video": "synthetic.mp4",
        "events": [make_event(2).model_dump(mode="json")],
    }
    path.write_text(json.dumps(worker_line) + "\n" + json.dumps(summary_line) + "\n")
    assert [event.event_id for event in load_events(path)] == ["delivery_1", "delivery_2"]


def test_load_events_rejects_invalid_event_before_any_post(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps({"event_id": "x", "signal_type": "unknown_kind"}) + "\n")
    with pytest.raises(ValueError):
        load_events(path)


def test_post_events_batches_and_sends_token_only_in_header():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append((request.headers["authorization"], len(body["events"]), body))
        return httpx.Response(200, json={"accepted": len(body["events"]), "duplicates": 0})

    events = [make_event(index) for index in range(MAX_EVENTS_PER_BATCH + 2)]
    with httpx.Client(
        base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(handler)
    ) as client:
        totals = post_events(client, "session_1", events, "synthetic-token")
    assert totals == {"accepted": MAX_EVENTS_PER_BATCH + 2, "duplicates": 0}
    assert [count for _, count, _ in seen] == [MAX_EVENTS_PER_BATCH, 2]
    assert all(auth == "Bearer synthetic-token" for auth, _, _ in seen)
    assert all("synthetic-token" not in json.dumps(body) for _, _, body in seen)


def test_post_events_surfaces_backend_rejection():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"code": "forbidden"}})

    with (
        httpx.Client(
            base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        post_events(client, "session_1", [make_event(1)], "synthetic-token")
