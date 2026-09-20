"""Explicitly consented, local-only student camera CLI; stdout has derived signals only.

The application never launches this tool. Frames are read from the local camera,
analyzed in memory, and erased; only labelled intervals with a confidence are printed
as JSON lines. Send them to the backend with ``scripts/post_student_signals.py``.
"""

import argparse
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

import cv2

from app.local_ml.student_signals import (
    Frame,
    OnnxStudentAnalyzer,
    StudentSignal,
    StudentSignalPolicy,
    StudentSignalWorker,
)

MAXIMUM_CLOCK_OFFSET_MS = 28_800_000


class FrameSource(Protocol):
    """The subset of a camera capture the loop needs; a fake is used in tests."""

    def isOpened(self) -> bool:  # noqa: N802 - mirrors the OpenCV method name.
        """Return whether frames can still be read."""
        ...

    def read(self) -> tuple[bool, object]:
        """Return a validity flag and one BGR frame."""
        ...


def run_capture(
    source: FrameSource,
    worker: StudentSignalWorker,
    clock_offset_ms: int,
    emit: Callable[[StudentSignal], None],
    monotonic: Callable[[], float] = time.monotonic,
    max_duration_ms: int | None = None,
) -> int:
    """Feed camera frames to the worker until the source ends, is lost, or is interrupted.

    Args:
        source: Local camera capture.
        worker: Student signal worker; it erases every frame it is given.
        clock_offset_ms: Session-relative lecture time when the worker starts.
        emit: Callback for each finished derived signal.
        monotonic: Clock injected for tests.
        max_duration_ms: Optional run length; the loop ends cleanly after it.

    Returns:
        Elapsed run length in milliseconds.

    Side effects:
        Loss of the camera calls ``worker.unavailable()`` and emits nothing further,
        so a vanished source is never reported as a student leaving the frame.
    """
    origin = monotonic()
    last_ms = clock_offset_ms
    try:
        while source.isOpened():
            valid, frame = source.read()
            if not valid:
                worker.unavailable()
                return int((monotonic() - origin) * 1000)
            elapsed_ms = int((monotonic() - origin) * 1000)
            if max_duration_ms is not None and elapsed_ms >= max_duration_ms:
                break
            last_ms = clock_offset_ms + elapsed_ms
            for signal in worker.observe(cast(Frame, frame), last_ms):
                emit(signal)
    except KeyboardInterrupt:
        pass
    for signal in worker.flush(last_ms):
        emit(signal)
    return last_ms - clock_offset_ms


def summarize_run(signals: list[StudentSignal], elapsed_ms: int) -> dict[str, object]:
    """Count signals per label and per minute for a smoke test.

    If the person did none of the behaviours during the run, every count is a false
    alarm, so ``per_minute`` is then the false-alarm rate for that label.

    Args:
        signals: Signals emitted during the run.
        elapsed_ms: Run length in milliseconds.

    Returns:
        Run length, counts per label, and events per minute per label.
    """
    minutes = max(elapsed_ms, 1) / 60_000
    counts: dict[str, int] = {}
    for signal in signals:
        counts[signal.event_type] = counts.get(signal.event_type, 0) + 1
    return {
        "seconds": round(elapsed_ms / 1000, 1),
        "signal_counts": counts,
        "per_minute": {label: round(count / minutes, 2) for label, count in counts.items()},
    }


def main() -> int:
    """Read local camera frames after explicit consent; release capture on every exit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consent-local-camera", action="store_true", required=True)
    parser.add_argument("--person-model", type=Path, required=True)
    parser.add_argument("--face-model", type=Path, required=True)
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument(
        "--clock-offset-ms",
        type=int,
        required=True,
        help="Current session-relative time at worker start",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        help="Stop after this many seconds and print a per-label summary to stderr.",
    )
    arguments = parser.parse_args()
    if not 0 <= arguments.clock_offset_ms <= MAXIMUM_CLOCK_OFFSET_MS:
        parser.error("Clock offset must be within the eight-hour session clock.")
    analyzer = OnnxStudentAnalyzer.from_files(arguments.person_model, arguments.face_model)
    worker = StudentSignalWorker(analyzer, StudentSignalPolicy())
    capture = cv2.VideoCapture(arguments.camera_index)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    emitted: list[StudentSignal] = []

    def emit(signal: StudentSignal) -> None:
        emitted.append(signal)
        print(signal.model_dump_json(), flush=True)

    try:
        elapsed_ms = run_capture(
            capture,
            worker,
            arguments.clock_offset_ms,
            emit,
            max_duration_ms=None if arguments.max_seconds is None else int(arguments.max_seconds * 1000),
        )
        if arguments.max_seconds is not None:
            print(json.dumps(summarize_run(emitted, elapsed_ms)), file=sys.stderr)
        return 0
    finally:
        worker.unavailable()
        capture.release()


if __name__ == "__main__":
    raise SystemExit(main())
