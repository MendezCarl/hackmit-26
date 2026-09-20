"""Synthetic arrays validate local-only lifecycle, timing and evidence behavior."""

import numpy as np
import pytest
from app.local_ml.vision import (
    Detection,
    ModelManifest,
    OnnxPersonDetector,
    Region,
    VisionPolicy,
    VisionWorker,
    benchmark_detector,
)


class Detector:
    """Configurable synthetic detector; no model download or camera access."""

    def __init__(self):
        self.present = False
        self.fail = False

    def detect(self, frame):
        if self.fail:
            raise ValueError("synthetic inference failure")
        return (
            [Detection(x1=0, y1=0, x2=1, y2=1, confidence=0.9)] if self.present else []
        )


def frame():
    return np.full((180, 320, 3), 127, dtype=np.uint8)


def worker(detector):
    return VisionWorker(detector, VisionPolicy(), Region(x1=0, y1=0, x2=1, y2=1))


def test_sustained_interval_frame_erasure_and_cooldown():
    detector = Detector()
    vision = worker(detector)
    for timestamp in [0, 1000, 2000, 3000]:
        image = frame()
        assert vision.observe(image, timestamp) == []
        assert not image.any()
    detector.present = True
    events = vision.observe(frame(), 4000)
    assert len(events) == 1 and events[0].start_ms == 0 and events[0].end_ms == 4000
    assert "box" not in events[0].model_dump_json()
    detector.present = False
    assert vision.observe(frame(), 5000) == [] and vision.active == {}


def test_dropouts_do_not_bridge_missing_evidence():
    detector = Detector()
    vision = worker(detector)
    vision.observe(frame(), 0)
    vision.observe(frame(), 1000)
    vision.observe(frame(), 6000)
    detector.present = True
    assert vision.observe(frame(), 7000) == []


def test_inference_failure_erases_frame_and_marks_unavailable():
    detector = Detector()
    detector.fail = True
    vision = worker(detector)
    image = frame()
    with pytest.raises(ValueError):
        vision.observe(image, 0)
    assert not image.any() and vision.is_available is False and vision.active == {}


def test_model_approval_and_digest_required_before_runtime_load(tmp_path):
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
        OnnxPersonDetector(path, manifest)
    with pytest.raises(ValueError):
        OnnxPersonDetector(path, manifest.model_copy(update={"is_approved": True}))


def test_benchmark_has_no_hardware_guarantee():
    result = benchmark_detector(Detector(), 3)
    assert result["samples"] == 3 and result["p95_latency_ms"] >= 0


def test_visual_quality_events_use_only_derived_evidence():
    """Blur/contrast heuristics close an interval when readable structure returns."""
    detector = Detector()
    detector.present = True
    region = Region(x1=0, y1=0, x2=1, y2=1)
    vision = VisionWorker(detector, VisionPolicy(profile="balanced"), region, region)
    for timestamp in [0, 1000, 2000, 3000]:
        assert vision.observe(frame(), timestamp) == []
    pattern = (np.indices((180, 320)).sum(axis=0) % 2 * 255).astype(np.uint8)
    image = np.repeat(pattern[:, :, None], 3, axis=2)
    events = vision.observe(image, 4000)
    assert any(event.signal_type == "slide_text_low_legibility" for event in events)
    assert not image.any()
    assert all("frame" not in event.evidence.model_dump() for event in events)
