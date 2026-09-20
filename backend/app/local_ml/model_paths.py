"""Repository-anchored locations of the operator-supplied local model files.

The model artifacts live in the gitignored ``models/`` directory at the repository
root (see ``backend/Makefile`` ``export-model``). Anchoring the defaults to this file's
location rather than the working directory lets the evaluation and demo scripts run
from any directory.
"""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = REPOSITORY_ROOT / "models"
PERSON_MODEL_PATH = MODELS_DIR / "person_detector.onnx"
FACE_MODEL_PATH = MODELS_DIR / "face_detection_yunet_2023mar.onnx"


def resolve_model_paths(models_dir: Path) -> tuple[Path, Path]:
    """Return the person and face detector paths inside a models directory.

    Args:
        models_dir: Directory holding the exported model files and their manifests.

    Returns:
        ``(person_model, face_model)`` paths using the export script filenames.
    """

    return (
        models_dir / PERSON_MODEL_PATH.name,
        models_dir / FACE_MODEL_PATH.name,
    )
