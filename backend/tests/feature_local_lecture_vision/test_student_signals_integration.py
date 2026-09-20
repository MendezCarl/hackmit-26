"""Worker output posted through the real app, and the camera loop with a fake camera."""

import json
import sys
from pathlib import Path

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from app.auth.tokens import AuthenticatedActor, issue_access_token  # noqa: E402
from app.config import Settings  # noqa: E402
from app.local_ml.student_signals import (  # noqa: E402
    FrameObservation,
    StudentSignalPolicy,
    StudentSignalWorker,
)
from app.local_ml.student_worker import run_capture  # noqa: E402
from app.main import create_app  # noqa: E402
from scripts.post_student_signals import load_signals, post_signals  # noqa: E402

SETTINGS = Settings(app_env="test")
LECTURE_ID = "lecture-1"
STEP_MS = 500


class ScriptedAnalyzer:
    """Synthetic analyzer; the observation can be changed between frames."""

    def __init__(self, observation: FrameObservation) -> None:
        self.observation = observation

    def analyze(self, frame):
        return self.observation


class FakeCamera:
    """Yields synthetic frames, then either closes cleanly or silently loses the camera."""

    def __init__(self, frames: int, lose_camera: bool) -> None:
        self.remaining = frames
        self.lose_camera = lose_camera
        self.is_open = True

    def isOpened(self) -> bool:  # noqa: N802 - mirrors OpenCV.
        return self.is_open

    def read(self):
        if self.remaining == 0:
            return False, None  # A lost camera stays open but returns no frame.
        self.remaining -= 1
        if self.remaining == 0 and not self.lose_camera:
            self.is_open = False  # A clean end closes the source after its last frame.
        return True, np.full((180, 320, 3), 127, dtype=np.uint8)


def ticking_clock():
    """Deterministic clock advancing 0.5 s per call."""
    state = {"now": 0.0}

    def tick() -> float:
        state["now"] += STEP_MS / 1000
        return state["now"]

    return tick


def token_for(user_id: str) -> str:
    return issue_access_token(SETTINGS, AuthenticatedActor(user_id=user_id, role="student"))


def make_session(client: TestClient) -> str:
    response = client.post(
        "/api/v1/sessions",
        json={
            "lecture_id": LECTURE_ID,
            "course_id": "course-1",
            "title": "Synthetic Lecture",
            "mode": "in_person",
        },
        headers={"Authorization": f"Bearer {token_for('owner-1')}"},
    )
    return response.json()["session_id"]


class LeadInAnalyzer:
    """Faces forward for the first samples, then shows the given observation."""

    def __init__(self, observation: FrameObservation, forward_samples: int) -> None:
        self.observation = observation
        self.forward = FrameObservation(0.99, 0.0, 0.9, 0.0)
        self.forward_samples = forward_samples
        self.calls = 0

    def analyze(self, frame):
        self.calls += 1
        return self.forward if self.calls <= self.forward_samples else self.observation


def signals_from(observation: FrameObservation, seconds: int, forward_seconds: int = 0):
    """Run the real worker on synthetic frames and return the closed signals."""
    analyzer = LeadInAnalyzer(observation, forward_seconds * 2)
    worker = StudentSignalWorker(analyzer, StudentSignalPolicy())
    collected = []
    run_capture(
        FakeCamera((seconds + forward_seconds) * 2, lose_camera=False),
        worker,
        0,
        collected.append,
        ticking_clock(),
    )
    return collected


def test_worker_signals_are_accepted_and_phone_alone_is_never_eligible():
    client = TestClient(create_app(SETTINGS))
    session_id = make_session(client)
    phone = signals_from(FrameObservation(0.99, 0.9, 0.9, 0.0), seconds=40)
    head = signals_from(
        FrameObservation(0.99, 0.0, 0.9, 1.3), seconds=40, forward_seconds=6
    )
    assert [s.event_type for s in phone] == ["phone_visible"]
    assert [s.event_type for s in head] == ["head_away"]
    receipt = post_signals(
        client, session_id, LECTURE_ID, phone + head, token_for("owner-1")
    )
    assert sorted(receipt["accepted_event_ids"]) == sorted(s.event_id for s in phone + head)
    # A 40 s phone-only signal must not qualify; a 40 s head turn meets the 30 s rule.
    assert receipt["recovery_eligible_event_ids"] == [head[0].event_id]


def test_offset_aligns_clip_time_with_lecture_clock():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            202, json={"accepted_event_ids": [], "recovery_eligible_event_ids": []}
        )

    signals = signals_from(FrameObservation(0.99, 0.9, 0.9, 0.0), seconds=5)
    with httpx.Client(
        base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(handler)
    ) as client:
        post_signals(
            client, "session_1", LECTURE_ID, signals, "synthetic-token", offset_ms=60_000
        )
    assert seen["events"][0]["start_ms"] == signals[0].start_ms + 60_000
    assert "synthetic-token" not in json.dumps(seen)


def test_non_member_cannot_post_signals():
    client = TestClient(create_app(SETTINGS))
    session_id = make_session(client)
    signals = signals_from(FrameObservation(0.99, 0.9, 0.9, 0.0), seconds=5)
    # TestClient may raise its own HTTPStatusError class, so assert on the status code.
    with pytest.raises(Exception) as rejected:  # noqa: B017
        post_signals(client, session_id, LECTURE_ID, signals, token_for("stranger-1"))
    assert rejected.value.response.status_code == 403


def test_load_signals_reads_worker_lines_and_clip_summaries(tmp_path):
    signals = signals_from(FrameObservation(0.99, 0.9, 0.9, 0.0), seconds=5)
    path = tmp_path / "signals.jsonl"
    path.write_text(
        signals[0].model_dump_json()
        + "\n"
        + json.dumps(
            {"clip": "synthetic.mp4", "signals": [signals[0].model_dump(mode="json")]}
        )
        + "\n"
    )
    assert len(load_signals(path)) == 2
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"event_type": "attention_score"}) + "\n")
    with pytest.raises(ValueError):
        load_signals(bad)


def test_camera_loss_reports_unavailable_and_emits_no_false_events():
    worker = StudentSignalWorker(
        ScriptedAnalyzer(FrameObservation(0.0, 0.0, 0.0, None)), StudentSignalPolicy()
    )
    collected = []
    run_capture(
        FakeCamera(4, lose_camera=True), worker, 0, collected.append, ticking_clock()
    )
    assert collected == [] and worker.is_available is False and worker.active == {}


def test_normal_end_flushes_open_interval():
    worker = StudentSignalWorker(
        ScriptedAnalyzer(FrameObservation(0.99, 0.9, 0.9, 0.0)), StudentSignalPolicy()
    )
    collected = []
    run_capture(
        FakeCamera(8, lose_camera=False), worker, 5_000, collected.append, ticking_clock()
    )
    assert [s.event_type for s in collected] == ["phone_visible"]
    assert collected[0].start_ms >= 5_000


def test_run_stops_at_max_duration_and_reports_elapsed_time():
    from app.local_ml.student_worker import summarize_run

    worker = StudentSignalWorker(
        ScriptedAnalyzer(FrameObservation(0.99, 0.9, 0.9, 0.0)), StudentSignalPolicy()
    )
    collected = []
    camera = FakeCamera(1000, lose_camera=False)
    elapsed = run_capture(
        camera, worker, 0, collected.append, ticking_clock(), max_duration_ms=4_000
    )
    assert 3_000 <= elapsed <= 4_500 and camera.remaining > 900
    summary = summarize_run(collected, elapsed)
    assert summary["signal_counts"] == {"phone_visible": 1}
    assert summary["per_minute"]["phone_visible"] > 0


def test_demo_turns_a_short_signal_into_a_grounded_card():
    from scripts.demo_student_to_card import LECTURE_OFFSET_MS, run_demo

    signals = signals_from(FrameObservation(0.99, 0.9, 0.9, 0.0), seconds=5)
    result = run_demo(signals)
    # The 30 s rule is advisory: a five-second phone signal is not eligible, yet a card exists.
    assert result["receipt"]["recovery_eligible_event_ids"] == []
    assert result["job"]["status"] == "completed"
    assert result["card"]["card_id"] == result["job"]["card_id"]
    assert result["card"]["source_timestamps"], "card must cite transcript timestamps"
    assert signals[0].start_ms + LECTURE_OFFSET_MS >= 0
