"""CPU-local derived observations with explicit model approval and frame ownership.

Caller transfers ownership of each frame; the worker erases it on every exit.
No model download, frame persistence, telemetry or networking is performed here.
"""

import hashlib
import time
from pathlib import Path
from typing import Literal, Protocol
from uuid import uuid4

import cv2
import numpy as np
from numpy.typing import NDArray
from pydantic import Field, model_validator

from app.contracts.learning import (
    DeliveryEvent,
    DeliveryEvidence,
    DeliveryKind,
    StrictPayload,
)

Frame = NDArray[np.uint8]


class Region(StrictPayload):
    """Normalized local-only rectangle; no boxes are emitted to the server."""

    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float = Field(gt=0, le=1)
    y2: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def ordered(self):
        """Reject reversed or empty rectangles."""
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("Empty region")
        return self


class Detection(Region):
    """Allowed person detection in normalized local coordinates."""

    confidence: float = Field(ge=0, le=1)


class LocalDetector(Protocol):
    """Local-only inference boundary; implementations must not retain frame references."""

    def detect(self, frame: Frame) -> list[Detection]:
        """Return person boxes or raise ValueError for unsupported input/model output."""
        ...


class ModelManifest(StrictPayload):
    """Operator-approved artifact provenance and exact supported tensor contract."""

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: str = Field(min_length=1, max_length=400)
    license: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=80)
    is_approved: bool = False
    input_size: int = Field(ge=32, le=320)
    person_class_id: int = Field(ge=0, le=1000, default=0)
    output_format: Literal["xyxy_score_class_normalized"] = "xyxy_score_class_normalized"


class OnnxPersonDetector:
    """CPU adapter for approved NCHW RGB models with normalized Nx6 output.

    Export conversion is model-specific and must happen before approval. Arbitrary
    YOLO/SSD tensor layouts are rejected rather than guessed.
    """

    def __init__(self, path: Path, manifest: ModelManifest) -> None:
        """Verify bounded artifact digest and approval before loading ONNX Runtime."""
        if not manifest.is_approved or path.stat().st_size > 30 * 1024 * 1024:
            raise ValueError("Model must be approved and at most 30 MiB")
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest.sha256:
            raise ValueError("Model digest mismatch")
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.manifest = manifest
        inputs = self.session.get_inputs()
        if (
            len(inputs) != 1
            or inputs[0].shape != [1, 3, manifest.input_size, manifest.input_size]
            or inputs[0].type != "tensor(float)"
        ):
            raise ValueError("Unsupported model input tensor")
        self.input_name = inputs[0].name

    def detect(self, frame: Frame) -> list[Detection]:
        """Run CPU inference and validate local boxes; erase all intermediate tensors."""
        resized = cv2.resize(frame, (self.manifest.input_size, self.manifest.input_size))
        tensor = (
            np.ascontiguousarray(
                resized[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32
            )
            / 255.0
        )
        outputs = []
        try:
            outputs = self.session.run(None, {self.input_name: tensor})
            boxes = np.asarray(outputs[0])
            if (
                boxes.ndim != 2
                or boxes.shape[1] != 6
                or boxes.shape[0] > 1000
                or not np.isfinite(boxes).all()
            ):
                raise ValueError("Unsupported model output tensor")
            return [
                Detection(
                    x1=float(b[0]),
                    y1=float(b[1]),
                    x2=float(b[2]),
                    y2=float(b[3]),
                    confidence=float(b[4]),
                )
                for b in boxes
                if b[5] == self.manifest.person_class_id and b[4] >= 0.5
            ]
        finally:
            tensor.fill(0)
            resized.fill(0)
            for output in outputs:
                output.fill(0)


class VisionPolicy(StrictPayload):
    """Configurable synthetic heuristics; benchmark and evaluate before real use."""

    minimum_duration_ms: int = Field(default=3000, ge=100, le=60_000)
    maximum_sample_gap_ms: int = Field(default=2000, ge=100, le=10_000)
    cooldown_ms: int = Field(default=5000, ge=0, le=60_000)
    minimum_confidence: float = Field(default=0.5, ge=0, le=1)
    occlusion_ratio: float = Field(default=0.4, gt=0, le=1)
    blur_threshold: float = Field(default=40, ge=0)
    contrast_threshold: float = Field(default=20, ge=0)
    profile: Literal["low_power", "balanced", "performance"] = "low_power"
    detector_version: str = "local-vision-v1"


def overlap_fraction(left: Region, right: Region) -> float:
    """Return the fraction of right covered by left, using normalized local boxes."""
    area = max(0.0, min(left.x2, right.x2) - max(left.x1, right.x1)) * max(
        0.0, min(left.y2, right.y2) - max(left.y1, right.y1)
    )
    return area / ((right.x2 - right.x1) * (right.y2 - right.y1))


class VisionWorker:
    """One frame at a time; unavailable sources clear candidates without false events."""

    def __init__(
        self,
        detector: LocalDetector,
        policy: VisionPolicy,
        presenter: Region,
        board: Region | None = None,
    ) -> None:
        """Inject a local detector and user-confirmed regions; no camera is opened."""
        self.detector, self.policy, self.presenter, self.board = (
            detector,
            policy,
            presenter,
            board,
        )
        self.active: dict[DeliveryKind, tuple[int, int]] = {}
        self.cooldowns: dict[DeliveryKind, int] = {}
        self.previous_ms: int | None = None
        self.sampling_ms = {"low_power": 1000, "balanced": 334, "performance": 200}[
            policy.profile
        ]
        self.last_latency_ms = 0
        self.is_available = True

    def _close_interval(
        self, kind: DeliveryKind, begin_ms: int, positive_count: int, end_ms: int
    ) -> DeliveryEvent | None:
        """Build an event for a finished candidate, or None if it was too short.

        Args:
            kind: Delivery condition that was active.
            begin_ms: Lecture time of the first positive sample.
            positive_count: Positive samples observed so far.
            end_ms: Lecture time at which the condition ended.

        Returns:
            A derived event when the interval meets the minimum duration.
        """
        if end_ms - begin_ms < self.policy.minimum_duration_ms:
            return None
        return DeliveryEvent(
            event_id=f"delivery_{uuid4().hex}",
            signal_type=kind,
            start_ms=begin_ms,
            end_ms=end_ms,
            confidence=0.5,
            detector_version=self.policy.detector_version,
            evidence=DeliveryEvidence(
                sample_count=positive_count + 1,
                positive_sample_count=positive_count,
                performance_profile=self.policy.profile,
            ),
        )

    def flush(self, lecture_time_ms: int) -> list[DeliveryEvent]:
        """Close conditions still open when observation stops, e.g. at end of lecture.

        Without this, an interval that is still true at the last sample is lost
        because events are otherwise emitted only when a condition ends.

        Args:
            lecture_time_ms: Lecture time at which observation stopped.

        Returns:
            Events for open conditions that already meet the minimum duration.
        """
        events = []
        for kind, (begin, count) in self.active.items():
            event = self._close_interval(kind, begin, count, lecture_time_ms)
            if event is not None:
                events.append(event)
        self.active.clear()
        return events

    def unavailable(self) -> None:
        """Discard incomplete candidates after camera loss; no cloud fallback or evidence."""
        self.active.clear()
        self.previous_ms = None
        self.is_available = False

    def observe(self, frame: Frame, lecture_time_ms: int) -> list[DeliveryEvent]:
        """Consume and erase an owned BGR frame; emit closed, sustained intervals only.

        Raises:
            ValueError: Invalid frame or non-monotonic lecture timestamp. Inference
                failures mark the worker unavailable and propagate without raw data.
        """
        started = time.perf_counter()
        try:
            if (
                frame.dtype != np.uint8
                or frame.ndim != 3
                or frame.shape[2] != 3
                or frame.size > 1920 * 1080 * 3
            ):
                raise ValueError("Invalid bounded BGR frame")
            if not 0 <= lecture_time_ms <= 28_800_000 or (
                self.previous_ms is not None and lecture_time_ms <= self.previous_ms
            ):
                raise ValueError("Lecture timestamps must increase")
            if (
                self.previous_ms is not None
                and lecture_time_ms - self.previous_ms < self.sampling_ms
            ):
                return []
            if (
                self.previous_ms is not None
                and lecture_time_ms - self.previous_ms > self.policy.maximum_sample_gap_ms
            ):
                self.active.clear()
            self.previous_ms = lecture_time_ms
            detections = [
                d
                for d in self.detector.detect(frame)
                if d.confidence >= self.policy.minimum_confidence
            ]
            flags: dict[DeliveryKind, bool] = {
                "presenter_out_of_frame": not any(
                    overlap_fraction(d, self.presenter) > 0 for d in detections
                )
            }
            if self.board is not None and self.policy.profile != "low_power":
                flags["board_or_screen_occluded"] = any(
                    overlap_fraction(d, self.board) >= self.policy.occlusion_ratio
                    for d in detections
                )
                height, width = frame.shape[:2]
                roi = frame[
                    int(self.board.y1 * height) : int(self.board.y2 * height),
                    int(self.board.x1 * width) : int(self.board.x2 * width),
                ]
                if roi.size:
                    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                    try:
                        flags["slide_text_low_legibility"] = (
                            float(cv2.Laplacian(gray, cv2.CV_64F).var())
                            < self.policy.blur_threshold
                            or float(gray.std()) < self.policy.contrast_threshold
                        )
                    finally:
                        gray.fill(0)
            events = []
            for kind, positive in flags.items():
                if positive and lecture_time_ms >= self.cooldowns.get(kind, 0):
                    begin, count = self.active.get(kind, (lecture_time_ms, 0))
                    self.active[kind] = (begin, count + 1)
                elif not positive and kind in self.active:
                    begin, count = self.active.pop(kind)
                    event = self._close_interval(kind, begin, count, lecture_time_ms)
                    if event is not None:
                        events.append(event)
                        self.cooldowns[kind] = lecture_time_ms + self.policy.cooldown_ms
            self.is_available = True
            return events
        except Exception:
            self.unavailable()
            raise
        finally:
            frame.fill(0)
            self.last_latency_ms = int((time.perf_counter() - started) * 1000)
            if self.last_latency_ms > self.sampling_ms:
                self.sampling_ms = min(
                    2000, max(self.sampling_ms, self.last_latency_ms * 2)
                )


def benchmark_detector(detector: LocalDetector, samples: int = 10) -> dict[str, int | str]:
    """Benchmark synthetic frames on this device; no cross-platform performance claim."""
    if not 3 <= samples <= 100:
        raise ValueError("Use 3 to 100 benchmark samples")
    latencies = []
    for _ in range(samples):
        frame = np.zeros((180, 320, 3), dtype=np.uint8)
        start = time.perf_counter()
        try:
            detector.detect(frame)
        finally:
            frame.fill(0)
        latencies.append((time.perf_counter() - start) * 1000)
    p95 = int(np.percentile(latencies, 95))
    return {
        "p95_latency_ms": p95,
        "samples": samples,
        "recommended_profile": "disabled"
        if p95 > 1000
        else "low_power"
        if p95 > 200
        else "balanced",
    }
