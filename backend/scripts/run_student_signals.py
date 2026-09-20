"""Replay a local webcam-style clip through the student signal worker, in memory.

Offline evaluation and demo tool: frames are decoded, handed to the worker (which
erases them) and never written to disk. Only derived signal intervals are printed.
Models and manifests are operator-supplied under the gitignored models/ directory.
"""

import argparse
import json
from pathlib import Path
from typing import cast

import cv2

from app.local_ml.model_paths import FACE_MODEL_PATH, PERSON_MODEL_PATH
from app.local_ml.student_signals import Frame, StudentSignalPolicy, StudentSignalWorker
from scripts.evaluate_clip_signals import load_analyzer


def analyze_clip(
    worker: StudentSignalWorker, path: Path, sampling_ms: int
) -> dict[str, object]:
    """Run one clip through the worker and return its derived signals.

    Args:
        worker: Student signal worker wrapping approved local models.
        path: Local video clip.
        sampling_ms: Target spacing between analyzed frames.

    Returns:
        Clip name, analyzed length, and the emitted signal intervals.

    Raises:
        ValueError: If the clip cannot be opened.
    """
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"Cannot open {path.name}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 24.0
    stride = max(1, round(fps * sampling_ms / 1000))
    signals, index, last_ms = [], 0, 0
    while capture.grab():
        if index % stride == 0:
            valid, frame = capture.retrieve()
            if valid:
                last_ms = int(index / fps * 1000)
                signals += worker.observe(cast(Frame, frame), last_ms)
        index += 1
    capture.release()
    signals += worker.flush(last_ms)
    return {
        "clip": path.name,
        "seconds": round(index / fps, 1),
        "signals": [
            s.model_dump(mode="json") for s in sorted(signals, key=lambda s: s.start_ms)
        ],
    }


def main() -> None:
    """Print one JSON summary per clip."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clips", nargs="+", type=Path)
    parser.add_argument("--person-model", type=Path, default=PERSON_MODEL_PATH)
    parser.add_argument("--face-model", type=Path, default=FACE_MODEL_PATH)
    arguments = parser.parse_args()
    analyzer = load_analyzer(arguments.person_model, arguments.face_model)
    policy = StudentSignalPolicy()
    for clip in arguments.clips:
        worker = StudentSignalWorker(analyzer, policy)
        print(json.dumps(analyze_clip(worker, clip, policy.sampling_ms)), flush=True)


if __name__ == "__main__":
    main()
