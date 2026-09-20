"""Download the OpenCV Zoo YuNet face detector, verify its pinned digest, write a manifest.

Operator tool. The digest is pinned, so a changed or tampered download is rejected
before anything is written. The file and manifest belong in the gitignored models/.
"""

import argparse
import hashlib
import ssl
import urllib.request
from pathlib import Path

from app.local_ml.vision import ModelManifest

YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
    "face_detection_yunet_2023mar.onnx"
)
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
YUNET_FILENAME = "face_detection_yunet_2023mar.onnx"
DOWNLOAD_TIMEOUT_SECONDS = 60
MAXIMUM_DOWNLOAD_BYTES = 5 * 1024 * 1024


def fetch_face_model(output_dir: Path, is_approved: bool) -> Path:
    """Download and verify the face model, then write its manifest.

    Args:
        output_dir: Destination directory, created if missing.
        is_approved: Whether the operator has reviewed the license and approves use.

    Returns:
        Path of the written manifest.

    Raises:
        ValueError: If the download is too large or its SHA-256 differs from the pin.
    """
    try:  # python.org macOS builds lack CA certificates; certifi fixes that if present.
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    with urllib.request.urlopen(
        YUNET_URL, timeout=DOWNLOAD_TIMEOUT_SECONDS, context=context
    ) as response:
        content = response.read(MAXIMUM_DOWNLOAD_BYTES + 1)
    if len(content) > MAXIMUM_DOWNLOAD_BYTES:
        raise ValueError("Face model download is larger than expected")
    if hashlib.sha256(content).hexdigest() != YUNET_SHA256:
        raise ValueError("Face model digest does not match the pinned value")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / YUNET_FILENAME).write_bytes(content)
    manifest = ModelManifest(
        sha256=YUNET_SHA256,
        source="OpenCV Zoo face_detection_yunet_2023mar.onnx",
        license="MIT per OpenCV Zoo listing (verify before redistribution)",
        version="yunet-2023mar",
        is_approved=is_approved,
        input_size=320,
        person_class_id=0,
    )
    manifest_path = output_dir / "face_detection_yunet_2023mar.manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n")
    return manifest_path


def main() -> None:
    """Run the download from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("models"))
    parser.add_argument("--approve", action="store_true", help="Record operator approval.")
    arguments = parser.parse_args()
    print(fetch_face_model(arguments.output_dir, arguments.approve))


if __name__ == "__main__":
    main()
