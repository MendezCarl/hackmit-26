"""Synthetic checks for student observations: timing, erasure, mapping and contract fit."""

import numpy as np
import pytest

from app.contracts.models import SignalEvent
from app.local_ml.student_signals import (
    FrameObservation,
    StudentSignalPolicy,
    StudentSignalWorker,
    verify_model_file,
)
from app.local_ml.vision import ModelManifest

STEP_MS = 500  # Larger than the default 334 ms sampling interval.


class ScriptedAnalyzer:
    """Synthetic analyzer whose observation is set by the test; no models, no camera."""

    def __init__(self) -> None:
        self.observation = FrameObservation(0.99, 0.0, 0.9, 0.0)
        self.fail = False

    def analyze(self, frame):
        if self.fail:
            raise ValueError("synthetic inference failure")
        return self.observation


def synthetic_frame():
    return np.full((180, 320, 3), 127, dtype=np.uint8)


def run(worker, count, start_ms=0):
    """Feed `count` frames at STEP_MS spacing and return all emitted signals."""
    signals = []
    for index in range(count):
        signals += worker.observe(synthetic_frame(), start_ms + index * STEP_MS)
    return signals


def make_worker(analyzer):
    return StudentSignalWorker(analyzer, StudentSignalPolicy())


def test_sustained_phone_emits_one_signal_with_mean_score_and_erases_frames():
    analyzer = ScriptedAnalyzer()
    worker = make_worker(analyzer)
    analyzer.observation = FrameObservation(0.99, 0.8, 0.9, 0.0)
    image = synthetic_frame()
    assert worker.observe(image, 0) == []
    assert not image.any()
    run(worker, 3, start_ms=STEP_MS)
    analyzer.observation = FrameObservation(0.99, 0.0, 0.9, 0.0)
    signals = worker.observe(synthetic_frame(), 4 * STEP_MS)
    assert len(signals) == 1
    assert signals[0].event_type == "phone_visible"
    assert (signals[0].start_ms, signals[0].end_ms) == (0, 4 * STEP_MS)
    assert signals[0].confidence == pytest.approx(0.8)
    dumped = signals[0].model_dump_json()
    assert "box" not in dumped and "frame" not in dumped


def test_signal_shorter_than_minimum_duration_is_dropped():
    analyzer = ScriptedAnalyzer()
    worker = make_worker(analyzer)
    analyzer.observation = FrameObservation(0.99, 0.8, 0.9, 0.0)
    worker.observe(synthetic_frame(), 0)
    analyzer.observation = FrameObservation(0.99, 0.0, 0.9, 0.0)
    assert worker.observe(synthetic_frame(), STEP_MS) == []


def test_observation_labels_map_to_distinct_signals():
    analyzer = ScriptedAnalyzer()
    worker = make_worker(analyzer)
    cases = {
        "student_left_frame": FrameObservation(0.0, 0.0, 0.0, None),
        "face_absent": FrameObservation(0.99, 0.0, 0.0, None),
        "head_away": FrameObservation(0.99, 0.0, 0.9, 1.2),
    }
    for expected, observation in cases.items():
        analyzer.observation = observation
        worker.active.clear()
        worker.previous_ms = None
        run(worker, 4)
        assert [signal.event_type for signal in worker.flush(4 * STEP_MS)] == [expected]


def test_small_yaw_is_not_a_head_turn():
    analyzer = ScriptedAnalyzer()
    analyzer.observation = FrameObservation(0.99, 0.0, 0.9, 0.4)
    worker = make_worker(analyzer)
    run(worker, 4)
    assert worker.flush(4 * STEP_MS) == []


def test_sampling_gap_does_not_bridge_missing_evidence():
    analyzer = ScriptedAnalyzer()
    worker = make_worker(analyzer)
    analyzer.observation = FrameObservation(0.99, 0.8, 0.9, 0.0)
    worker.observe(synthetic_frame(), 0)
    worker.observe(synthetic_frame(), STEP_MS)
    worker.observe(synthetic_frame(), 10_000)
    assert worker.flush(10_000) == []


def test_flush_closes_interval_open_at_end():
    analyzer = ScriptedAnalyzer()
    analyzer.observation = FrameObservation(0.99, 0.7, 0.9, 0.0)
    worker = make_worker(analyzer)
    run(worker, 4)
    signals = worker.flush(3 * STEP_MS)
    assert [signal.event_type for signal in signals] == ["phone_visible"]
    assert worker.active == {}


def test_inference_failure_erases_frame_and_marks_unavailable():
    analyzer = ScriptedAnalyzer()
    analyzer.fail = True
    worker = make_worker(analyzer)
    image = synthetic_frame()
    with pytest.raises(ValueError):
        worker.observe(image, 0)
    assert not image.any() and worker.is_available is False and worker.active == {}


def test_invalid_frame_and_non_monotonic_time_are_rejected():
    worker = make_worker(ScriptedAnalyzer())
    with pytest.raises(ValueError):
        worker.observe(np.zeros((10, 10), dtype=np.uint8), 0)
    worker = make_worker(ScriptedAnalyzer())
    worker.observe(synthetic_frame(), 1000)
    with pytest.raises(ValueError):
        worker.observe(synthetic_frame(), 1000)


def test_signal_fits_backend_signal_event_contract():
    analyzer = ScriptedAnalyzer()
    analyzer.observation = FrameObservation(0.99, 0.8, 0.9, 0.0)
    worker = make_worker(analyzer)
    run(worker, 4)
    (signal,) = worker.flush(3 * STEP_MS)
    event = SignalEvent(session_id="session_1", **signal.model_dump(mode="json"))
    assert event.event_type == "phone_visible" and event.signals == ["phone_visible"]


def test_model_verification_requires_approval_and_matching_digest(tmp_path):
    path = tmp_path / "synthetic.onnx"
    path.write_bytes(b"not a model")
    manifest = ModelManifest(
        sha256="0" * 64,
        source="synthetic",
        license="synthetic-test",
        version="v1",
        input_size=320,
    )
    with pytest.raises(ValueError):
        verify_model_file(path, manifest)
    with pytest.raises(ValueError):
        verify_model_file(path, manifest.model_copy(update={"is_approved": True}))
