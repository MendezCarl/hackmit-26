"""Find which step of loading the local models hangs or fails on this machine.

Each step runs in its own process with a time limit, so a hang is reported instead of
blocking. No camera is opened and no video is read.
"""

import hashlib
import platform
import subprocess
import sys
import time
from pathlib import Path

STEP_TIMEOUT_SECONDS = 40
# Kept standard-library only so it still runs when importing ``app`` is the problem;
# mirrors ``app.local_ml.model_paths``.
MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
PERSON_MODEL = MODELS_DIR / "person_detector.onnx"
FACE_MODEL = MODELS_DIR / "face_detection_yunet_2023mar.onnx"

STEPS: list[tuple[str, str]] = [
    (
        "import onnxruntime",
        "import onnxruntime as ort; print(ort.__version__, ort.get_available_providers())",
    ),
    ("import cv2", "import cv2; print(cv2.__version__)"),
    (
        "load person model (default threads)",
        f"import onnxruntime as ort; ort.InferenceSession(r'{PERSON_MODEL}', providers=['CPUExecutionProvider']); print('ok')",
    ),
    (
        "load person model (1 thread, as the app does)",
        "import onnxruntime as ort; o=ort.SessionOptions(); o.intra_op_num_threads=1; o.inter_op_num_threads=1; "
        f"ort.InferenceSession(r'{PERSON_MODEL}', sess_options=o, providers=['CPUExecutionProvider']); print('ok')",
    ),
    (
        "create face detector",
        f"import cv2; cv2.FaceDetectorYN.create(r'{FACE_MODEL}', '', (320, 320), 0.6, 0.3, 50); print('ok')",
    ),
]


def run_step(name: str, code: str) -> tuple[str, float, str]:
    """Run one step in a fresh process; return its status, seconds and last output line."""
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=STEP_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return (
            "HUNG",
            time.perf_counter() - started,
            f"no result after {STEP_TIMEOUT_SECONDS} s",
        )
    # Prefer the step's own output; OpenCV prints harmless "[ WARN ...]" lines on stderr.
    lines = completed.stdout.strip().splitlines() or [
        line for line in completed.stderr.strip().splitlines() if "WARN" not in line
    ]
    status = "ok" if completed.returncode == 0 else "FAILED"
    return status, time.perf_counter() - started, lines[-1] if lines else ""


def main() -> int:
    """Print machine details and the result of each loading step."""
    translated = subprocess.run(
        ["sysctl", "-n", "sysctl.proc_translated"], capture_output=True, text=True
    ).stdout.strip()
    print(f"python   : {sys.version.split()[0]} at {sys.executable}")
    print(f"machine  : {platform.machine()} | running under Rosetta: {translated == '1'}")
    print(f"models   : {MODELS_DIR}")
    missing = [p.name for p in (PERSON_MODEL, FACE_MODEL) if not p.exists()]
    if missing:
        print(
            f"\nMISSING model files in {MODELS_DIR}: {missing} "
            "(build them with `make export-model APPROVE=1` in backend/)"
        )
        return 1
    print()
    started = time.perf_counter()
    digests = [
        hashlib.sha256(p.read_bytes()).hexdigest()[:12] for p in (PERSON_MODEL, FACE_MODEL)
    ]
    print(
        f"{'read + hash both model files':48} ok      {time.perf_counter() - started:5.1f} s  {digests}"
    )
    hung = False
    for name, code in STEPS:
        status, seconds, detail = run_step(name, code)
        hung = hung or status == "HUNG"
        print(f"{name:48} {status:7} {seconds:5.1f} s  {detail[:70]}", flush=True)
    print("\nSend this whole output back." if hung else "\nAll steps completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
