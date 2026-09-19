"""FastAPI application entry point and system endpoints."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Response returned by the liveness endpoint."""

    status: str = Field(description="Current process health state.", examples=["ok"])


class ApiStatusResponse(BaseModel):
    """Response describing whether the API skeleton is ready."""

    message: str = Field(
        description="Human-readable API status message.",
        examples=["FastAPI backend is ready."],
    )


OPENAPI_TAGS = [
    {
        "name": "system",
        "description": "Liveness and API readiness endpoints.",
    }
]

app = FastAPI(
    title="Lecture Recovery Assistant API",
    summary="Backend API for privacy-first lecture recovery.",
    description=(
        "Typed REST endpoints for lecture sessions, recovery cards, integrations, "
        "and anonymous professor summaries."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=OPENAPI_TAGS,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="Check process health",
)
def read_health() -> HealthResponse:
    """Return the current process liveness state.

    Returns:
        A typed response whose status is ``ok`` while the process is running.
    """

    return HealthResponse(status="ok")


@app.get(
    "/api/status",
    response_model=ApiStatusResponse,
    tags=["system"],
    summary="Check API readiness",
)
def read_api_status() -> ApiStatusResponse:
    """Return a human-readable readiness message for the frontend skeleton.

    Returns:
        A typed status response confirming that the API is ready.
    """

    return ApiStatusResponse(message="FastAPI backend is ready.")
