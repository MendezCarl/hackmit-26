"""Guided physical-camera smoke test for the student signal worker.

Two modes, both local and opt-in (``--consent-local-camera`` is required):

- ``false-alarms``: sit normally for a few minutes; every signal is a false alarm.
- ``guided``: follow spoken-style prompts (normal, phone, look aside, leave and return);
  the run is scored against the script.

Frames are analyzed in memory and erased. Only derived signal intervals and a score
summary are printed and saved (under the gitignored data/local/eval/).
"""

import argparse
import json
import statistics
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import cv2

from app.local_ml.student_signals import (
    Frame,
    FrameObservation,
    OnnxStudentAnalyzer,
    StudentSignal,
    StudentSignalPolicy,
    StudentSignalWorker,
)
from app.local_ml.student_worker import run_capture

COUNTDOWN_SECONDS = 5
BOUNDARY_SLACK_S = 3.0  # Reaction time and merge gap near a phase boundary are not errors.
DETECTED_COVERAGE = 0.5
MINIMUM_RUN_FRACTION = 0.9  # A run shorter than this means the camera stopped or never opened.
FALSE_ALARM_LABELS = ("phone_visible", "head_away")
MAXIMUM_FALSE_ALARMS_PER_MINUTE = 0.2  # About one event in five minutes.


@dataclass(frozen=True)
class Phase:
    """One scripted stretch of the guided run."""

    start_s: int
    end_s: int
    instruction: str
    expected: tuple[str, ...]  # Labels that should appear; empty means none should.


GUIDED_SCRIPT = (
    Phase(0, 30, "Sit normally and look at the screen.", ()),
    Phase(30, 60, "Hold your phone up near your chin, screen toward you, so the camera can see it.", ("phone_visible",)),
    Phase(60, 80, "Look to the side.", ("head_away",)),
    Phase(80, 100, "Leave the camera view, then come back.", ("student_left_frame", "face_absent")),
    Phase(100, 120, "Sit normally again.", ()),
)


def overlap_seconds(start_s: float, end_s: float, window_start: float, window_end: float) -> float:
    """Length in seconds of the overlap between two intervals, never negative."""
    return max(0.0, min(end_s, window_end) - max(start_s, window_start))


def score_guided_run(signals: list[StudentSignal], script: tuple[Phase, ...]) -> dict[str, object]:
    """Score a run against the scripted phases.

    Args:
        signals: Signals emitted during the run, in run time.
        script: The phases the person followed.

    Returns:
        Per-phase coverage of expected labels, unexpected signals inside each phase, and a
        verdict. An expected phase counts as detected when its labels cover at least half of
        it; unexpected signals near phase boundaries (within a few seconds) are ignored.
    """
    phases = []
    for phase in script:
        length = phase.end_s - phase.start_s
        spans = sorted(
            (max(s.start_ms / 1000, phase.start_s), min(s.end_ms / 1000, phase.end_s))
            for s in signals
            if s.event_type in phase.expected
            and overlap_seconds(s.start_ms / 1000, s.end_ms / 1000, phase.start_s, phase.end_s) > 0
        )
        covered, cursor = 0.0, float(phase.start_s)
        for start, end in spans:  # Union of spans, so overlapping signals are not double counted.
            start = max(start, cursor)
            if end > start:
                covered += end - start
                cursor = end
        inner = (phase.start_s + BOUNDARY_SLACK_S, phase.end_s - BOUNDARY_SLACK_S)
        unexpected = [
            s.event_type
            for s in signals
            if s.event_type not in phase.expected
            and overlap_seconds(s.start_ms / 1000, s.end_ms / 1000, *inner) >= 1.0
        ]
        phases.append(
            {
                "instruction": phase.instruction,
                "expected": list(phase.expected),
                "coverage": round(covered / length, 2),
                "detected": (covered / length >= DETECTED_COVERAGE) if phase.expected else None,
                "unexpected_signals": unexpected,
            }
        )
    missed = [p["instruction"] for p in phases if p["detected"] is False]
    unexpected_total = sum(len(p["unexpected_signals"]) for p in phases)  # type: ignore[arg-type]
    return {
        "phases": phases,
        "missed_phases": missed,
        "unexpected_signal_count": unexpected_total,
        "verdict": "PASS" if not missed and unexpected_total == 0 else "REVIEW",
    }


def score_false_alarms(signals: list[StudentSignal], seconds: float) -> dict[str, object]:
    """Rate signals per minute for a run in which no behavior was performed.

    Args:
        signals: Every signal emitted; each is a false alarm by construction.
        seconds: Length of the run in seconds.

    Returns:
        Counts and per-minute rates per label, and a verdict on phone and head-turn rates.
    """
    minutes = max(seconds, 1e-6) / 60
    counts: dict[str, int] = {}
    for signal in signals:
        counts[signal.event_type] = counts.get(signal.event_type, 0) + 1
    rates = {label: round(count / minutes, 2) for label, count in counts.items()}
    headline = sum(counts.get(label, 0) for label in FALSE_ALARM_LABELS) / minutes
    return {
        "seconds": round(seconds, 1),
        "signal_counts": counts,
        "per_minute": rates,
        "phone_and_head_per_minute": round(headline, 2),
        "verdict": "PASS" if headline <= MAXIMUM_FALSE_ALARMS_PER_MINUTE else "REVIEW",
    }


class RecordingAnalyzer:
    """Wrap an analyzer, keeping each frame's derived scores (numbers only, never pixels)."""

    def __init__(self, analyzer, live: bool = False) -> None:
        """Wrap a local analyzer; ``live`` prints one score line per second."""
        self.analyzer = analyzer
        self.live = live
        self.rows: list[dict[str, float | None]] = []
        self.origin = time.monotonic()
        self._last_printed = -1.0

    def start(self) -> None:
        """Set time zero for the recorded scores to the start of the run."""
        self.origin = time.monotonic()
        self.rows.clear()
        self._last_printed = -1.0

    def analyze(self, frame: Frame) -> FrameObservation:
        """Analyze a frame, record its scores, and optionally print them."""
        observation = self.analyzer.analyze(frame)
        elapsed = time.monotonic() - self.origin
        self.rows.append(
            {
                "t_s": round(elapsed, 2),
                "person": round(observation.person_score, 3),
                "phone": round(observation.phone_score, 3),
                "face": round(observation.face_score, 3),
                "yaw": None if observation.face_yaw is None else round(observation.face_yaw, 3),
            }
        )
        if self.live and elapsed - self._last_printed >= 1.0:
            self._last_printed = elapsed
            yaw = "  -  " if observation.face_yaw is None else f"{observation.face_yaw:5.2f}"
            print(
                f"    t={elapsed:5.1f}s  person {observation.person_score:.2f}  "
                f"phone {observation.phone_score:.2f}  face {observation.face_score:.2f}  yaw {yaw}",
                flush=True,
            )
        return observation


def summarize_phase_scores(
    rows: list[dict[str, float | None]], script: tuple[Phase, ...]
) -> list[dict[str, object]]:
    """Summarize the recorded scores inside each scripted phase.

    Args:
        rows: Per-sample derived scores with a ``t_s`` time.
        script: The phases the person followed.

    Returns:
        Per phase: sample count, median and maximum phone score, share of samples with a
        person and with a face, and the largest head-yaw magnitude seen.
    """
    summaries = []
    for phase in script:
        inside = [r for r in rows if phase.start_s <= float(r["t_s"] or 0) < phase.end_s]
        yaws = [abs(float(r["yaw"])) for r in inside if r["yaw"] is not None]
        phone = [float(r["phone"] or 0) for r in inside]
        summaries.append(
            {
                "instruction": phase.instruction,
                "samples": len(inside),
                "phone_median": round(statistics.median(phone), 2) if phone else None,
                "phone_max": round(max(phone), 2) if phone else None,
                "person_share": round(sum(float(r["person"] or 0) >= 0.5 for r in inside) / len(inside), 2) if inside else None,
                "face_share": round(sum(r["yaw"] is not None for r in inside) / len(inside), 2) if inside else None,
                "yaw_magnitude_max": round(max(yaws), 2) if yaws else None,
            }
        )
    return summaries


def announce(script: tuple[Phase, ...]) -> list[threading.Timer]:
    """Schedule the on-screen prompts for each phase; call ``start()`` on each timer."""
    timers = []
    for phase in script:
        timer = threading.Timer(
            phase.start_s,
            lambda p=phase: print(f"\a  [{p.start_s:>3}s]  {p.instruction}", flush=True),
        )
        timer.daemon = True
        timers.append(timer)
    return timers


def open_camera(index: int, width: int = 640, height: int = 480) -> cv2.VideoCapture:
    """Open the camera or exit with the usual causes, so a dead camera is not read as a pass."""
    capture = cv2.VideoCapture(index)
    if not capture.isOpened():
        sys.exit(
            "Could not open the camera. Check System Settings > Privacy & Security > Camera "
            "for your terminal app, close other apps using the camera (Zoom, FaceTime), or try "
            "--camera-index 1."
        )
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return capture


def countdown() -> None:
    """Give the person a few seconds to get into position."""
    for remaining in range(COUNTDOWN_SECONDS, 0, -1):
        print(f"  starting in {remaining}...", flush=True)
        time.sleep(1)


def main() -> int:
    """Run the chosen smoke test, print a readable result, and save the summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consent-local-camera", action="store_true", required=True)
    parser.add_argument("--mode", choices=("false-alarms", "guided"), required=True)
    parser.add_argument("--seconds", type=int, default=300, help="Length for false-alarms mode.")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--width", type=int, default=640, help="Capture width; a phone is tiny at low resolution.")
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Print derived scores once a second (numbers only) to help position the phone.",
    )
    parser.add_argument("--person-model", type=Path, default=Path("models/person_detector.onnx"))
    parser.add_argument(
        "--face-model", type=Path, default=Path("models/face_detection_yunet_2023mar.onnx")
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/local/eval"))
    arguments = parser.parse_args()

    print("Step 1/3: loading the models (usually 1-2 s; the first run can take up to a minute)...", flush=True)
    started = time.perf_counter()
    analyzer = OnnxStudentAnalyzer.from_files(arguments.person_model, arguments.face_model)
    recorder = RecordingAnalyzer(analyzer, live=arguments.live)
    worker = StudentSignalWorker(recorder, StudentSignalPolicy())
    print(f"          models ready in {time.perf_counter() - started:.1f} s", flush=True)
    print(
        "Step 2/3: opening the camera. If macOS shows a permission popup, click Allow "
        "(it may be hidden behind other windows)...",
        flush=True,
    )
    capture = open_camera(arguments.camera_index, arguments.width, arguments.height)
    actual = (int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    print(f"          camera open, delivering {actual[0]}x{actual[1]}", flush=True)
    print("Step 3/3: the test.", flush=True)
    seconds = arguments.seconds if arguments.mode == "false-alarms" else GUIDED_SCRIPT[-1].end_s
    print(f"\nMode: {arguments.mode}, {seconds} s. Your video stays on this computer.\n")
    if arguments.mode == "false-alarms":
        print("  Sit normally, look at the screen, and do not use a phone.")
    countdown()
    signals: list[StudentSignal] = []
    timers = announce(GUIDED_SCRIPT) if arguments.mode == "guided" else []
    recorder.start()
    for timer in timers:
        timer.start()
    try:
        elapsed_ms = run_capture(
            capture, worker, 0, signals.append, max_duration_ms=seconds * 1000
        )
    finally:
        capture.release()
        for timer in timers:
            timer.cancel()
    elapsed = elapsed_ms / 1000
    print(f"\nRan {elapsed:.0f} of {seconds} s.")
    if elapsed < seconds * MINIMUM_RUN_FRACTION:
        print("CAMERA PROBLEM: the run ended early, so this is not a valid result. Rerun it.")
    result = (
        score_false_alarms(signals, elapsed)
        if arguments.mode == "false-alarms"
        else score_guided_run(signals, GUIDED_SCRIPT)
    )
    result["ran_seconds"] = round(elapsed, 1)
    result["observations"] = recorder.rows
    if arguments.mode == "guided":
        result["phase_scores"] = summarize_phase_scores(recorder.rows, GUIDED_SCRIPT)
    result["signals"] = [s.model_dump(mode="json") for s in signals]
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    path = arguments.output_dir / f"smoke_test_{arguments.mode}_{int(time.time())}.json"
    path.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k not in ("signals", "observations")}, indent=2))
    print(f"\nSaved {path} (derived signals only, no video).")
    return 0


def run() -> int:
    """Run the test, turning Ctrl+C into a clear message instead of a traceback."""
    try:
        return main()
    except KeyboardInterrupt:
        print("\nStopped with Ctrl+C. No result was saved.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(run())
