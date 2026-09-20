"""Export a pretrained person detector into the vision worker's ONNX contract.

This is an operator tool, not application code. It needs ``torch`` and
``torchvision``, which are deliberately absent from the backend manifests; install
``backend/requirements-model-export.txt`` in a separate environment. The output
model and manifest belong in the gitignored ``models/`` directory.
"""

import argparse
import hashlib
from pathlib import Path

import torch
from torchvision.models.detection import (
    SSDLite320_MobileNet_V3_Large_Weights,
    ssdlite320_mobilenet_v3_large,
)

from app.local_ml.vision import ModelManifest

MODEL_INPUT_SIZE = 320
COCO_PERSON_CLASS_ID = 1  # torchvision uses the 91-index COCO label scheme.
EXPORT_SCORE_FLOOR = 0.3  # The worker applies its own, stricter confidence cutoff.
OPSET_VERSION = 17


class NormalizedPersonExport(torch.nn.Module):
    """Wrap a torchvision detector so it returns Nx6 normalized xyxy/score/class rows."""

    def __init__(self, detector: torch.nn.Module) -> None:
        """Store an eval-mode detector whose own transform handles normalization."""
        super().__init__()
        self.detector = detector

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        """Detect objects in one RGB float image of shape [1, 3, S, S] scaled to 0..1.

        Returns:
            A float tensor of shape [N, 6]: x1, y1, x2, y2 (0..1), score, class id.
        """
        result = self.detector([image[0]])[0]
        boxes = result["boxes"] / MODEL_INPUT_SIZE
        return torch.cat(
            [
                boxes.clamp(0.0, 1.0),
                result["scores"][:, None],
                result["labels"][:, None].to(torch.float32),
            ],
            dim=1,
        )


def export_person_detector(output_dir: Path, is_approved: bool) -> Path:
    """Download pretrained weights, export ONNX, and write the operator manifest.

    Args:
        output_dir: Destination for ``person_detector.onnx`` and its manifest.
        is_approved: Whether the operator has reviewed the license and approves use.

    Returns:
        Path of the written manifest.
    """
    weights = SSDLite320_MobileNet_V3_Large_Weights.DEFAULT
    detector = ssdlite320_mobilenet_v3_large(
        weights=weights, score_thresh=EXPORT_SCORE_FLOOR, detections_per_img=100
    ).eval()
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "person_detector.onnx"
    example = torch.zeros(1, 3, MODEL_INPUT_SIZE, MODEL_INPUT_SIZE)
    torch.onnx.export(
        NormalizedPersonExport(detector).eval(),
        (example,),
        str(model_path),
        input_names=["image"],
        output_names=["detections"],
        dynamic_axes={"detections": {0: "count"}},
        opset_version=OPSET_VERSION,
        dynamo=False,
    )
    manifest = ModelManifest(
        sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
        source="torchvision ssdlite320_mobilenet_v3_large, COCO_V1 weights",
        license="BSD-3-Clause code; weights trained on COCO (verify before redistribution)",
        version="ssdlite320-mobilenetv3-coco-v1",
        is_approved=is_approved,
        input_size=MODEL_INPUT_SIZE,
        person_class_id=COCO_PERSON_CLASS_ID,
    )
    manifest_path = output_dir / "person_detector.manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n")
    return manifest_path


def main() -> None:
    """Run the export from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("models"))
    parser.add_argument(
        "--approve",
        action="store_true",
        help="Record operator approval after reviewing the model license.",
    )
    arguments = parser.parse_args()
    print(export_person_detector(arguments.output_dir, arguments.approve))


if __name__ == "__main__":
    main()
