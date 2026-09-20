"""Model paths used by the local-vision scripts resolve to the repository's ``models/``
directory regardless of the working directory (no model files are loaded)."""

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from app.local_ml import model_paths, student_signals  # noqa: E402
from scripts import demo_student_to_card, diagnose_model_load  # noqa: E402
from scripts import run_student_signals as clip_runner  # noqa: E402

EXPECTED_MODELS_DIR = BACKEND_ROOT.parent / "models"


def test_default_model_paths_are_anchored_to_the_repository_root():
    assert model_paths.MODELS_DIR == EXPECTED_MODELS_DIR
    assert model_paths.PERSON_MODEL_PATH == EXPECTED_MODELS_DIR / "person_detector.onnx"
    assert (
        model_paths.FACE_MODEL_PATH
        == EXPECTED_MODELS_DIR / "face_detection_yunet_2023mar.onnx"
    )
    assert model_paths.PERSON_MODEL_PATH.is_absolute()
    assert model_paths.FACE_MODEL_PATH.is_absolute()


def test_diagnostic_uses_the_same_model_locations_without_importing_app():
    assert diagnose_model_load.PERSON_MODEL == model_paths.PERSON_MODEL_PATH
    assert diagnose_model_load.FACE_MODEL == model_paths.FACE_MODEL_PATH


def test_resolve_model_paths_keeps_export_filenames(tmp_path):
    person_model, face_model = model_paths.resolve_model_paths(tmp_path)
    assert person_model == tmp_path / "person_detector.onnx"
    assert face_model == tmp_path / "face_detection_yunet_2023mar.onnx"


def test_demo_loads_models_from_repository_root_when_run_elsewhere(
    tmp_path, monkeypatch, capsys
):
    """Regression: the demo used ``models/`` relative to the working directory."""
    loaded: dict[str, Path] = {}

    class RecordingAnalyzer:
        @classmethod
        def from_files(cls, person_model: Path, face_model: Path):
            loaded["person"] = person_model
            loaded["face"] = face_model
            return cls()

    def analyze_clip_without_models(worker, clip, sampling_ms):
        return {"signals": []}

    monkeypatch.setattr(student_signals, "OnnxStudentAnalyzer", RecordingAnalyzer)
    monkeypatch.setattr(clip_runner, "analyze_clip", analyze_clip_without_models)
    monkeypatch.chdir(tmp_path)
    clip = tmp_path / "clip.mp4"
    clip.touch()
    monkeypatch.setattr(sys, "argv", ["demo_student_to_card", "--clip", str(clip)])

    with pytest.raises(ValueError, match="No signals"):
        demo_student_to_card.main()

    assert loaded == {
        "person": model_paths.PERSON_MODEL_PATH,
        "face": model_paths.FACE_MODEL_PATH,
    }


def test_demo_honours_an_explicit_models_directory(tmp_path, monkeypatch):
    loaded: dict[str, Path] = {}

    class RecordingAnalyzer:
        @classmethod
        def from_files(cls, person_model: Path, face_model: Path):
            loaded["person"] = person_model
            loaded["face"] = face_model
            return cls()

    monkeypatch.setattr(student_signals, "OnnxStudentAnalyzer", RecordingAnalyzer)
    monkeypatch.setattr(clip_runner, "analyze_clip", lambda *_: {"signals": []})
    custom_dir = tmp_path / "exported"
    monkeypatch.setattr(
        sys,
        "argv",
        ["demo_student_to_card", "--clip", "clip.mp4", "--models-dir", str(custom_dir)],
    )

    with pytest.raises(ValueError, match="No signals"):
        demo_student_to_card.main()

    assert loaded["person"] == custom_dir / "person_detector.onnx"
    assert loaded["face"] == custom_dir / "face_detection_yunet_2023mar.onnx"
