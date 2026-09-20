"""Scoring logic of the guided smoke test, on synthetic signals (no camera)."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from app.local_ml.student_signals import StudentSignal  # noqa: E402
from scripts.smoke_test_camera import (  # noqa: E402
    GUIDED_SCRIPT,
    score_false_alarms,
    score_guided_run,
)


def signal(label: str, start_s: float, end_s: float) -> StudentSignal:
    return StudentSignal(
        event_id=f"student_{label}_{int(start_s)}",
        event_type=label,
        start_ms=int(start_s * 1000),
        end_ms=int(end_s * 1000),
        signals=[label],
        confidence=0.7,
    )


def perfect_run():
    return [
        signal("phone_visible", 31, 59),
        signal("head_away", 61, 79),
        signal("student_left_frame", 82, 98),
    ]


def test_a_run_that_matches_the_script_passes():
    result = score_guided_run(perfect_run(), GUIDED_SCRIPT)
    assert result["verdict"] == "PASS"
    assert result["missed_phases"] == [] and result["unexpected_signal_count"] == 0


def test_a_missed_behavior_is_reported():
    signals = [s for s in perfect_run() if s.event_type != "phone_visible"]
    result = score_guided_run(signals, GUIDED_SCRIPT)
    assert result["verdict"] == "REVIEW"
    assert result["missed_phases"] == [
        "Hold your phone up near your chin, screen toward you, so the camera can see it."
    ]


def test_a_signal_during_a_normal_phase_is_a_false_alarm():
    result = score_guided_run(
        perfect_run() + [signal("phone_visible", 5, 15)], GUIDED_SCRIPT
    )
    assert result["verdict"] == "REVIEW" and result["unexpected_signal_count"] == 1


def test_signals_at_a_phase_boundary_are_not_counted_as_errors():
    # The phone event runs two seconds into the next phase: within reaction slack.
    result = score_guided_run(
        perfect_run() + [signal("phone_visible", 58, 62)], GUIDED_SCRIPT
    )
    assert result["unexpected_signal_count"] == 0


def test_overlapping_signals_are_not_double_counted():
    signals = [signal("phone_visible", 30, 50), signal("phone_visible", 35, 60)]
    phone_phase = score_guided_run(signals, GUIDED_SCRIPT)["phases"][1]
    assert phone_phase["coverage"] == 1.0


def test_false_alarm_rate_verdict():
    assert score_false_alarms([], 300)["verdict"] == "PASS"
    assert score_false_alarms([signal("face_absent", 10, 20)] * 5, 300)["verdict"] == "PASS"
    result = score_false_alarms([signal("phone_visible", 10, 20)] * 3, 300)
    assert result["verdict"] == "REVIEW" and result["phone_and_head_per_minute"] == 0.6


def test_phase_score_summary_reports_phone_scores_per_phase():
    from scripts.smoke_test_camera import summarize_phase_scores

    rows = [
        {"t_s": 5.0, "person": 0.99, "phone": 0.05, "face": 0.9, "yaw": 0.1},
        {"t_s": 35.0, "person": 0.99, "phone": 0.30, "face": 0.9, "yaw": 0.2},
        {"t_s": 40.0, "person": 0.99, "phone": 0.10, "face": 0.9, "yaw": None},
        {"t_s": 65.0, "person": 0.99, "phone": 0.0, "face": 0.9, "yaw": -1.4},
    ]
    summary = summarize_phase_scores(rows, GUIDED_SCRIPT)
    phone_phase, look_phase = summary[1], summary[2]
    assert phone_phase["samples"] == 2 and phone_phase["phone_max"] == 0.30
    assert phone_phase["face_share"] == 0.5
    assert look_phase["yaw_magnitude_max"] == 1.4
    assert summary[4]["samples"] == 0 and summary[4]["phone_max"] is None


def test_recorder_keeps_numbers_only():
    import numpy as np

    from app.local_ml.student_signals import FrameObservation
    from scripts.smoke_test_camera import RecordingAnalyzer

    class Fixed:
        def analyze(self, frame):
            return FrameObservation(0.9, 0.4, 0.8, 0.3)

    recorder = RecordingAnalyzer(Fixed())
    recorder.analyze(np.zeros((4, 4, 3), dtype=np.uint8))
    assert set(recorder.rows[0]) == {"t_s", "person", "phone", "face", "yaw"}
    assert recorder.rows[0]["phone"] == 0.4
