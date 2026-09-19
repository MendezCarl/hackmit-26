"""Feature 4 registration; timeline writes are supplied by the host or fixture."""

from fastapi import FastAPI
from pydantic import BaseModel

from app.professor.models import AggregationPolicy, ProfessorSummary
from app.professor.routes import router
from app.professor.service import ProfessorService
from app.timeline.dependencies import FeatureServices

KEY = "professor_aggregation"


def configure_demo(services: FeatureServices) -> None:
    """Install aggregation using an explicitly synthetic five-person policy."""
    services.professor = ProfessorService(
        services.repository,
        services.access,
        AggregationPolicy(
            minimum_group_size=5,
            aggregation_window_ms=15_000,
            policy_version="synthetic-demo-only",
        ),
    )


def register(app: FastAPI) -> None:
    """Add only the authorized post-lecture professor report endpoint."""
    app.include_router(router)


def register_demo(app: FastAPI) -> None:
    """No additional feature-specific demo endpoint is required."""


def public_models() -> list[type[BaseModel]]:
    """Return the public feature 4 response contract."""
    return [ProfessorSummary]
