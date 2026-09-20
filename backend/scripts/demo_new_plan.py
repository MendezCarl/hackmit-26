"""Run the new-plan MVP entirely in process with synthetic fixtures and providers."""

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
from fastapi.testclient import TestClient

from app.auth.tokens import AuthenticatedActor, issue_access_token
from app.config import Settings
from app.main import create_app


def run_demo() -> dict[str, object]:
    """Exercise real routing, auth, recovery, metrics, recommendations and mock export.

    Returns:
        A JSON-safe summary explicitly labeled synthetic; no provider calls.

    Raises:
        RuntimeError: If an integration step violates its expected API result.
    """
    settings = Settings(app_env="demo", context_padding_ms=0)
    with TestClient(create_app(settings)) as client:

        def call(method: str, path: str, body=None, user="student-1", role="student"):
            token = issue_access_token(
                settings,
                AuthenticatedActor(user_id=user, role=role, course_id="synthetic-course"),
            )
            response = client.request(
                method, path, json=body, headers={"Authorization": "Bearer " + token}
            )
            if response.status_code >= 300:
                raise RuntimeError(
                    f"Synthetic demo failed at {method} {path}: {response.status_code}"
                )
            return response.json()

        session = call(
            "POST",
            "/api/v1/sessions",
            {
                "lecture_id": "synthetic-lecture",
                "course_id": "synthetic-course",
                "title": "Synthetic stacks",
                "mode": "in_person",
            },
        )
        session_id = session["session_id"]
        base = f"/api/v1/sessions/{session_id}"
        call(
            "POST",
            base + "/transcript-chunks/batch",
            {
                "lecture_id": "synthetic-lecture",
                "chunks": [
                    {
                        "chunk_id": "synthetic-chunk",
                        "session_id": session_id,
                        "start_ms": 0,
                        "end_ms": 60_000,
                        "text": "A stack follows last-in, first-out ordering.",
                        "source": "local_transcription",
                        "is_final": True,
                    }
                ],
            },
        )
        for number in range(1, 6):
            user = f"student-{number}"
            call("POST", base + "/participants", user=user)
            call(
                "POST",
                base + "/coverage/batch",
                {
                    "records": [
                        {
                            "coverage_id": "coverage",
                            "start_ms": 0,
                            "end_ms": 60_000,
                            "is_available": True,
                        }
                    ]
                },
                user=user,
            )
            if number <= 2:
                call(
                    "POST",
                    base + "/events/batch",
                    {
                        "lecture_id": "synthetic-lecture",
                        "events": [
                            {
                                "event_id": f"signal-{number}",
                                "session_id": session_id,
                                "event_type": "possible_missed_window",
                                "start_ms": 0,
                                "end_ms": 30_000,
                                "signals": ["head_away"],
                                "confidence": 0.7,
                            }
                        ],
                    },
                    user=user,
                )
        call(
            "POST",
            base + "/delivery-events/batch",
            {
                "events": [
                    {
                        "event_id": "delivery-1",
                        "signal_type": "presenter_out_of_frame",
                        "start_ms": 0,
                        "end_ms": 10_000,
                        "confidence": 0.5,
                        "detector_version": "synthetic-v1",
                        "evidence": {
                            "sample_count": 11,
                            "positive_sample_count": 10,
                            "performance_profile": "low_power",
                        },
                    }
                ]
            },
            user="professor",
            role="professor",
        )
        job = call("POST", base + "/recovery-cards", {"start_ms": 0, "end_ms": 30_000})
        card = call("GET", base + "/recovery-cards/" + job["card_id"])
        reused = call("POST", base + "/recovery-cards", {"start_ms": 0, "end_ms": 30_000})
        tool_run = call(
            "POST", base + "/recovery/tool-runs", {"start_ms": 0, "end_ms": 30_000}
        )
        call("PUT", base + "/artifacts/folder", {"folder_id": "synthetic-course-folder"})
        receipt = call(
            "POST",
            base + "/artifacts/exports",
            {"card_id": card["card_id"], "filename": "review.md", "is_confirmed": True},
        )
        call("POST", base + "/end")
        metrics = call(
            "GET", base + "/professor-metrics", user="professor", role="professor"
        )
        recommendations = call(
            "POST",
            base + "/professor-recommendations",
            user="professor",
            role="professor",
        )
        call(
            "PUT",
            base + "/aggregation-consent",
            {"is_allowed": False},
            user="student-5",
        )
        suppressed = call(
            "GET", base + "/professor-metrics", user="professor", role="professor"
        )
        return {
            "mode": "synthetic_only",
            "recovery_status": job["status"],
            "source_count": len(card["source_timestamps"]),
            "repeat_cache_status": reused["cache_status"],
            "tool_mode": tool_run["provider_mode"],
            "export": receipt,
            "metrics_status": metrics["status"],
            "delivery_findings": len(metrics["delivery_findings"]),
            "recommendation_count": len(recommendations["recommendations"]),
            "after_revocation": suppressed["status"],
        }


if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2))
