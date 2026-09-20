"""System endpoint and demo-mode gating tests."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def build_test_client(app_env: str = "test") -> TestClient:
    """Create an isolated client with explicit test settings."""

    return TestClient(create_app(Settings(app_env=app_env)))


def test_health_returns_ok() -> None:
    """The liveness endpoint must stay available in every mode."""

    client = build_test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_status_returns_ready_message() -> None:
    """The readiness endpoint must stay available in every mode."""

    client = build_test_client()
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json() == {"message": "FastAPI backend is ready."}


def test_demo_run_is_unavailable_outside_demo_mode() -> None:
    """Demo runs must be rejected outside explicit demo mode."""

    client = build_test_client(app_env="development")
    response = client.post("/api/v1/demo/runs")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "demo_unavailable"


def test_demo_token_is_unavailable_outside_demo_or_test_mode() -> None:
    """Demo token minting must be rejected in development mode."""

    client = build_test_client(app_env="development")
    response = client.post(
        "/api/v1/demo/token",
        json={"user_id": "student-1", "role": "student"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "demo_unavailable"


def test_demo_token_is_available_in_test_mode() -> None:
    """Test mode may mint synthetic actors for fixture setup."""

    client = build_test_client(app_env="test")
    response = client.post(
        "/api/v1/demo/token",
        json={"user_id": "student-1", "role": "student"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "student"


def test_demo_token_rejects_unknown_role() -> None:
    """Only student and professor roles may be minted."""

    client = build_test_client(app_env="test")
    response = client.post(
        "/api/v1/demo/token",
        json={"user_id": "student-1", "role": "admin"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"
