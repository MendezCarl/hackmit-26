"""Generate the reusable JSON Schema contracts from Pydantic models.

Keeps ``shared/contracts/`` synchronized with the canonical Pydantic models
so REST and WebSocket payloads share one source of truth.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
CONTRACTS_DIR = REPOSITORY_ROOT / "shared" / "contracts"

sys.path.insert(0, str(BACKEND_ROOT))

from pydantic import BaseModel

from app.contracts import models as contract_models
from app.integrations.zoom import service as zoom_models

CONTRACT_MODEL_NAMES: dict[str, str] = {
    "error_response": "ErrorResponse",
    "lecture_session": "LectureSession",
    "signal_event": "SignalEvent",
    "transcript_chunk": "TranscriptChunk",
    "context_window": "ContextWindow",
    "recovery_job": "RecoveryJob",
    "recovery_card": "RecoveryCard",
    "cost_metrics": "CostMetrics",
    "professor_summary": "ProfessorSummary",
    "websocket_envelope": "EventEnvelope",
    "user_profile": "UserProfile",
    "auth_session": "AuthSession",
    "consent_settings": "ConsentSettings",
    "course": "Course",
    "course_enrollment": "CourseEnrollment",
    "available_lecture_session": "AvailableLectureSession",
    "lecture": "Lecture",
}

# Provider-facing models that cross the REST boundary but live with their
# integration package rather than in ``app.contracts.models``.
INTEGRATION_CONTRACT_MODELS: dict[str, type[BaseModel]] = {
    "zoom_rtms_status": zoom_models.ZoomRtmsStatus,
    "start_zoom_rtms_request": zoom_models.StartZoomRtmsRequest,
}


def build_contract(model_name: str) -> str:
    """Serialize one Pydantic model's JSON Schema deterministically.

    Args:
        model_name: Name of the model class in ``app.contracts.models``.

    Returns:
        The formatted JSON Schema document with a trailing newline.
    """

    model = getattr(contract_models, model_name)
    return build_model_contract(model)


def build_model_contract(model: type[BaseModel]) -> str:
    """Serialize a Pydantic model class's JSON Schema deterministically.

    Args:
        model: Pydantic model whose schema should be emitted.

    Returns:
        The formatted JSON Schema document with a trailing newline.
    """

    schema = model.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def write_contracts(output_dir: Path = CONTRACTS_DIR) -> None:
    """Write every shared JSON Schema to the repository.

    Args:
        output_dir: Destination directory for the schema files.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    for file_stem, model_name in CONTRACT_MODEL_NAMES.items():
        target = output_dir / f"{file_stem}.schema.json"
        target.write_text(build_contract(model_name), encoding="utf-8")
        print(f"Generated {target}")
    for file_stem, model in INTEGRATION_CONTRACT_MODELS.items():
        target = output_dir / f"{file_stem}.schema.json"
        target.write_text(build_model_contract(model), encoding="utf-8")
        print(f"Generated {target}")


def main() -> int:
    """Generate all shared contracts and exit successfully."""

    write_contracts()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
