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
    # The interval ends at the first non-matching sample and is emitted once the merge gap passes.
    assert worker.observe(synthetic_frame(), 4 * STEP_MS) == []
    signals = worker.observe(synthetic_frame(), 6 * STEP_MS)
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
    }
    for expected, observation in cases.items():
        analyzer.observation = observation
        worker.active.clear()
        worker.previous_ms = None
        run(worker, 4)
        assert [signal.event_type for signal in worker.flush(4 * STEP_MS)] == [expected]
    # Head turn is judged against a baseline, so it needs frames of the person facing forward first.
    analyzer.observation = FrameObservation(0.99, 0.0, 0.9, 0.0)
    worker = make_worker(analyzer)
    run(worker, 4)
    analyzer.observation = FrameObservation(0.99, 0.0, 0.9, 1.2)
    run(worker, 4, start_ms=4 * STEP_MS)
    assert [signal.event_type for signal in worker.flush(8 * STEP_MS)] == ["head_away"]


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
        sha256="0" * 64, source="synthetic", license="synthetic-test", version="v1", input_size=320
    )
    with pytest.raises(ValueError):
        verify_model_file(path, manifest)
    with pytest.raises(ValueError):
        verify_model_file(path, manifest.model_copy(update={"is_approved": True}))


def sequence_worker(observations):
    """Worker over a scripted per-sample observation sequence (last one repeats)."""

    class Sequence:
        def __init__(self):
            self.index = 0

        def analyze(self, frame):
            observation = observations[min(self.index, len(observations) - 1)]
            self.index += 1
            return observation

    return make_worker(Sequence())


def test_brief_dropout_within_the_merge_gap_keeps_one_interval():
    phone, none = FrameObservation(0.99, 0.8, 0.9, 0.0), FrameObservation(0.99, 0.0, 0.9, 0.0)
    worker = sequence_worker([phone] * 3 + [none] + [phone] * 3)
    signals = run(worker, 7) + worker.flush(6 * STEP_MS)
    assert [s.event_type for s in signals] == ["phone_visible"]
    assert (signals[0].start_ms, signals[0].end_ms) == (0, 6 * STEP_MS)


def test_pause_longer_than_the_merge_gap_splits_into_two_intervals():
    phone, none = FrameObservation(0.99, 0.8, 0.9, 0.0), FrameObservation(0.99, 0.0, 0.9, 0.0)
    worker = sequence_worker([phone] * 3 + [none] * 3 + [phone] * 3)
    signals = run(worker, 9) + worker.flush(8 * STEP_MS)
    assert [s.event_type for s in signals] == ["phone_visible", "phone_visible"]
    assert signals[0].end_ms == 3 * STEP_MS and signals[1].start_ms == 6 * STEP_MS


def test_person_who_sits_at_an_angle_is_not_flagged_but_a_real_turn_is():
    angled, turned = FrameObservation(0.99, 0.0, 0.9, 0.9), FrameObservation(0.99, 0.0, 0.9, 2.0)
    worker = sequence_worker([angled] * 8 + [turned] * 4)
    signals = run(worker, 12) + worker.flush(11 * STEP_MS)
    assert [s.event_type for s in signals] == ["head_away"]
    assert signals[0].start_ms == 8 * STEP_MS  # The constant 0.9 angle was never flagged.


def test_long_turn_is_reported_for_its_whole_length_not_absorbed_into_the_baseline():
    forward, turned = FrameObservation(0.99, 0.0, 0.9, 0.0), FrameObservation(0.99, 0.0, 0.9, 1.3)
    worker = sequence_worker([forward] * 6 + [turned] * 60)
    signals = run(worker, 66) + worker.flush(65 * STEP_MS)
    assert [s.event_type for s in signals] == ["head_away"]
    assert signals[0].end_ms - signals[0].start_ms >= 25_000


def test_turn_longer_than_the_reset_is_treated_as_a_new_seating_position():
    forward, turned = FrameObservation(0.99, 0.0, 0.9, 0.0), FrameObservation(0.99, 0.0, 0.9, 1.3)
    worker = sequence_worker([forward] * 6 + [turned] * 400)
    signals = run(worker, 406) + worker.flush(405 * STEP_MS)
    assert [s.event_type for s in signals] == ["head_away"]
    assert signals[0].end_ms - signals[0].start_ms < 70_000  # Re-baselined after about a minute.


def test_phone_score_without_a_person_is_ignored():
    worker = sequence_worker([FrameObservation(0.0, 0.9, 0.0, None)])
    run(worker, 6)
    assert [s.event_type for s in worker.flush(5 * STEP_MS)] == ["student_left_frame"]


def test_baseline_is_discarded_when_the_camera_is_lost():
    worker = sequence_worker([FrameObservation(0.99, 0.0, 0.9, 0.9)])
    run(worker, 6)
    assert len(worker.yaw_history) > 0
    worker.unavailable()
    assert len(worker.yaw_history) == 0


def test_face_lost_after_a_turn_continues_head_away_instead_of_face_absent():
    forward, turned = FrameObservation(0.99, 0.0, 0.9, 0.0), FrameObservation(0.99, 0.0, 0.9, 1.3)
    profile = FrameObservation(0.99, 0.0, 0.0, None)  # Person still there, face no longer found.
    worker = sequence_worker([forward] * 4 + [turned] * 4 + [profile] * 8)
    signals = run(worker, 16) + worker.flush(15 * STEP_MS)
    assert [s.event_type for s in signals] == ["head_away"]
    assert signals[0].end_ms - signals[0].start_ms >= 5_000  # One turn, not split in two.


def test_face_lost_while_facing_forward_is_face_absent():
    forward, covered = FrameObservation(0.99, 0.0, 0.9, 0.0), FrameObservation(0.99, 0.0, 0.0, None)
    worker = sequence_worker([forward] * 4 + [covered] * 6)
    signals = run(worker, 10) + worker.flush(9 * STEP_MS)
    assert [s.event_type for s in signals] == ["face_absent"]


def test_leaving_after_a_turn_reports_left_frame_and_forgets_the_turn():
    forward, turned = FrameObservation(0.99, 0.0, 0.9, 0.0), FrameObservation(0.99, 0.0, 0.9, 1.3)
    gone, back_no_face = FrameObservation(0.0, 0.0, 0.0, None), FrameObservation(0.99, 0.0, 0.0, None)
    worker = sequence_worker([forward] * 4 + [turned] * 3 + [gone] * 4 + [back_no_face] * 6)
    signals = run(worker, 17) + worker.flush(16 * STEP_MS)
    labels = [s.event_type for s in signals]
    assert "student_left_frame" in labels and labels[-1] == "face_absent"
