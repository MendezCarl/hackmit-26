"""Replay a local lecture video through the vision worker, entirely in memory.

Offline evaluation tool: frames are decoded, cropped to the presenter tile, handed
to ``VisionWorker`` (which erases them) and never written to disk. Only derived
events and summary counts are printed. Keep videos under the gitignored data/local/.
"""

import argparse
import json
from pathlib import Path
from typing import cast

import cv2

from app.local_ml.model_paths import PERSON_MODEL_PATH
from app.local_ml.vision import (
    Detection,
    Frame,
    ModelManifest,
    OnnxPersonDetector,
    Region,
    VisionPolicy,
    VisionWorker,
)

WHOLE_TILE = Region(x1=0, y1=0, x2=1, y2=1)
DEFAULT_TILE = (0.72, 0.0, 1.0, 0.30)  # Zoom presenter thumbnail, top-right corner.


class CountingDetector:
    """Delegate to a real detector while counting frames with a presenter present."""

    def __init__(self, detector: OnnxPersonDetector) -> None:
        """Wrap an approved local detector; no frame is retained."""
        self.detector = detector
        self.sample_count = 0
        self.presenter_present_count = 0

    def detect(self, frame: Frame) -> list[Detection]:
        """Detect people in one tile and update presence counters."""
        detections = self.detector.detect(frame)
        self.sample_count += 1
        self.presenter_present_count += bool(detections)
        return detections


DARK_PIXEL_LEVEL = 40
LIGHT_PIXEL_LEVEL = 235
BLANK_PIXEL_RATIO = 0.6


def is_tile_visible(tile_frame: Frame) -> bool:
    """Return whether the presenter tile appears to be on screen at all.

    When Zoom switches to full-screen sharing, the crop shows black margins or the
    shared page instead of a camera tile. That is a layout change, not a presenter
    leaving the frame, so it must be reported as unavailable rather than as an event.
    A room background is mid-toned, so a mostly near-black or near-white crop is
    treated as "no camera tile here". This is a heuristic for evaluation footage.

    Args:
        tile_frame: BGR crop of the expected tile position.

    Returns:
        False when most pixels are near-black or near-white.
    """
    gray = cv2.cvtColor(tile_frame, cv2.COLOR_BGR2GRAY)
    is_blank = (gray < DARK_PIXEL_LEVEL) | (gray > LIGHT_PIXEL_LEVEL)
    return bool(is_blank.mean() < BLANK_PIXEL_RATIO)


def crop_tile(frame: Frame, tile: tuple[float, float, float, float]) -> Frame:
    """Return an owned copy of the normalized presenter tile for the worker to erase."""
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = tile
    return cast(
        Frame,
        frame[
            int(y1 * height) : int(y2 * height), int(x1 * width) : int(x2 * width)
        ].copy(),
    )


def analyze_video(
    video_path: Path,
    detector: OnnxPersonDetector,
    tile: tuple[float, float, float, float],
    max_minutes: float | None,
    policy: VisionPolicy,
) -> dict[str, object]:
    """Run the worker over one video and summarize derived events.

    Args:
        video_path: Local video file; decoded frame by frame, never re-encoded.
        detector: Approved local ONNX person detector.
        tile: Normalized x1, y1, x2, y2 crop containing the presenter.
        max_minutes: Optional analysis limit from the start of the video.
        policy: Vision thresholds under evaluation.

    Returns:
        Event list plus sampling and presenter-presence counts.

    Raises:
        ValueError: If the video cannot be opened.
    """
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Cannot open {video_path.name}")
    counting = CountingDetector(detector)
    worker = VisionWorker(counting, policy, WHOLE_TILE)
    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    stride = max(1, round(fps * worker.sampling_ms / 1000))
    limit_ms = int(max_minutes * 60_000) if max_minutes else None
    events: list[dict[str, object]] = []
    index = 0
    last_sample_ms = 0
    unavailable_count = 0
    try:
        while capture.grab():
            lecture_ms = int(index / fps * 1000)
            if limit_ms is not None and lecture_ms > limit_ms:
                break
            if index % stride == 0:
                valid, frame = capture.retrieve()
                if valid:
                    last_sample_ms = lecture_ms
                    tile_frame = crop_tile(cast(Frame, frame), tile)
                    if not is_tile_visible(tile_frame):
                        unavailable_count += 1
                        worker.unavailable()
                        tile_frame.fill(0)
                    else:
                        for event in worker.observe(tile_frame, lecture_ms):
                            events.append(event.model_dump(mode="json"))
            index += 1
        # An interval still open at the last sample would otherwise be lost.
        events.extend(
            event.model_dump(mode="json") for event in worker.flush(last_sample_ms)
        )
    finally:
        capture.release()
    return {
        "video": video_path.name,
        "analyzed_minutes": round(index / fps / 60, 1),
        "samples": counting.sample_count,
        "tile_unavailable_samples": unavailable_count,
        "presenter_present_ratio": round(
            counting.presenter_present_count / max(1, counting.sample_count), 3
        ),
        "presenter_out_of_frame_events": len(events),
        "events": events,
    }


def main() -> None:
    """Analyze one or more local videos and print one JSON summary per video."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("videos", nargs="+", type=Path)
    parser.add_argument("--model", type=Path, default=PERSON_MODEL_PATH)
    parser.add_argument(
        "--manifest", type=Path, default=PERSON_MODEL_PATH.with_suffix(".manifest.json")
    )
    parser.add_argument("--tile", nargs=4, type=float, default=DEFAULT_TILE)
    parser.add_argument("--max-minutes", type=float)
    parser.add_argument(
        "--profile", default="balanced", choices=("low_power", "balanced", "performance")
    )
    arguments = parser.parse_args()
    detector = OnnxPersonDetector(
        arguments.model, ModelManifest.model_validate_json(arguments.manifest.read_text())
    )
    policy = VisionPolicy(profile=arguments.profile)
    for video in arguments.videos:
        summary = analyze_video(
            video, detector, tuple(arguments.tile), arguments.max_minutes, policy
        )
        print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
