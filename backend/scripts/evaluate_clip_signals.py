"""Measure frame-level person, phone, and face signals on short local clips.

Offline evaluation tool for consented or synthetic webcam-style clips. Frames are
decoded and analyzed in memory only; nothing is written to disk. The output is
per-clip signal fractions and timelines, not attention or engagement scores.

Models (operator-supplied, gitignored under models/):
- models/person_detector.onnx: SSDLite person and cell-phone detector.
- models/face_detection_yunet_2023mar.onnx: OpenCV YuNet face detector with landmarks.
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from app.local_ml.student_signals import OnnxStudentAnalyzer

PHONE_SCORE_THRESHOLD = 0.5
PERSON_SCORE_THRESHOLD = 0.5
HEAD_TURN_YAW_THRESHOLD = 0.7  # Landmark yaw proxy; frontal is near 0, side view above 1.
SAMPLE_STRIDE_FRAMES = 6  # About 4 samples per second at 24 fps.


def load_analyzer(person_model: Path, face_model: Path) -> OnnxStudentAnalyzer:
    """Load the app's analyzer with the manifest that sits next to each model file."""
    return OnnxStudentAnalyzer.from_files(person_model, face_model)


def evaluate_clip(extractor: OnnxStudentAnalyzer, path: Path) -> dict[str, object]:
    """Sample a clip and summarize frame-level signals.

    Args:
        extractor: Loaded local analyzer.
        path: Local video clip.

    Returns:
        Fractions of samples with each signal, plus per-sample timelines.

    Raises:
        ValueError: If the clip cannot be opened.
    """
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"Cannot open {path.name}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 24.0
    rows = []
    index = 0
    while capture.grab():
        if index % SAMPLE_STRIDE_FRAMES == 0:
            valid, frame = capture.retrieve()
            if valid:
                person, phone = extractor.person_and_phone(frame)
                rows.append((round(index / fps, 2), person, phone, extractor.face_score_and_yaw(frame)[1]))
                frame.fill(0)
        index += 1
    capture.release()
    yaws = [row[3] for row in rows]
    return {
        "clip": path.name,
        "samples": len(rows),
        "person_present": round(float(np.mean([r[1] >= PERSON_SCORE_THRESHOLD for r in rows])), 2),
        "phone_visible": round(float(np.mean([r[2] >= PHONE_SCORE_THRESHOLD for r in rows])), 2),
        "face_found": round(float(np.mean([y is not None for y in yaws])), 2),
        "head_turned": round(
            float(np.mean([y is not None and abs(y) > HEAD_TURN_YAW_THRESHOLD for y in yaws])),
            2,
        ),
        "timeline": [
            {
                "t_s": r[0],
                "person": round(r[1], 2),
                "phone": round(r[2], 2),
                "yaw": None if r[3] is None else round(r[3], 2),
            }
            for r in rows
        ],
    }


def main() -> None:
    """Evaluate each clip and print one JSON summary per clip."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clips", nargs="+", type=Path)
    parser.add_argument("--person-model", type=Path, default=Path("models/person_detector.onnx"))
    parser.add_argument(
        "--face-model", type=Path, default=Path("models/face_detection_yunet_2023mar.onnx")
    )
    parser.add_argument("--timeline", action="store_true", help="Include per-sample timelines.")
    arguments = parser.parse_args()
    extractor = load_analyzer(arguments.person_model, arguments.face_model)
    for clip in arguments.clips:
        summary = evaluate_clip(extractor, clip)
        if not arguments.timeline:
            summary.pop("timeline")
        print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
