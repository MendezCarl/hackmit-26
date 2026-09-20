"""Explicitly consented, local-only camera CLI; stdout contains derived events only."""

import argparse
import json
import time
from pathlib import Path
from typing import cast

import cv2

from app.local_ml.vision import (
    Frame,
    ModelManifest,
    OnnxPersonDetector,
    Region,
    VisionPolicy,
    VisionWorker,
    benchmark_detector,
)


def main() -> int:
    """Read local camera frames after explicit consent; release capture on every exit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consent-local-camera", action="store_true", required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument(
        "--clock-offset-ms",
        type=int,
        required=True,
        help="Current session-relative time at worker start",
    )
    parser.add_argument(
        "--profile",
        choices=("auto", "low_power", "balanced", "performance"),
        default="auto",
    )
    parser.add_argument(
        "--presenter-region",
        nargs=4,
        type=float,
        default=[0, 0, 1, 1],
        metavar=("X1", "Y1", "X2", "Y2"),
    )
    parser.add_argument(
        "--board-region", nargs=4, type=float, metavar=("X1", "Y1", "X2", "Y2")
    )
    args = parser.parse_args()
    origin = time.monotonic()
    if not 0 <= args.clock_offset_ms <= 28_800_000:
        parser.error("Clock offset must be within the eight-hour session clock.")
    manifest = ModelManifest.model_validate_json(args.manifest.read_text())
    detector = OnnxPersonDetector(args.model, manifest)
    profile = args.profile
    if profile == "auto":
        profile = benchmark_detector(detector)["recommended_profile"]
        if profile == "disabled":
            return 0
    presenter = Region.model_validate(
        dict(zip(("x1", "y1", "x2", "y2"), args.presenter_region, strict=True))
    )
    board = (
        Region.model_validate(
            dict(zip(("x1", "y1", "x2", "y2"), args.board_region, strict=True))
        )
        if args.board_region
        else None
    )
    worker = VisionWorker(
        detector, VisionPolicy.model_validate({"profile": profile}), presenter, board
    )
    capture = cv2.VideoCapture(args.camera_index)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
    try:
        while capture.isOpened():
            valid, frame = capture.read()
            if not valid:
                worker.unavailable()
                break
            timestamp = args.clock_offset_ms + int((time.monotonic() - origin) * 1000)
            for event in worker.observe(cast(Frame, frame), timestamp):
                print(json.dumps(event.model_dump(mode="json")), flush=True)
        return 0
    finally:
        worker.unavailable()
        capture.release()


if __name__ == "__main__":
    raise SystemExit(main())
