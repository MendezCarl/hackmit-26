"""Composable feature app: each checkout registers only its installed features."""

import os

from fastapi import APIRouter, FastAPI

from app.timeline.composition import installed_features
from app.timeline.contracts import FeatureError, StrictModel
from app.timeline.demo import DemoSessionAccess, build_demo_services
from app.timeline.dependencies import AuthorizedSession, FeatureServices, Services
from app.timeline.http import ERROR_RESPONSES, BoundedJsonMiddleware, FeatureRoute


class DemoStatus(StrictModel):
    """Synthetic lecture lifecycle receipt."""

    session_id: str
    is_ended: bool


class HealthStatus(StrictModel):
    """Local process liveness, not external-provider readiness."""

    status: str = "ok"


demo_router = APIRouter(tags=["demo"], route_class=FeatureRoute, responses=ERROR_RESPONSES)


@demo_router.post(
    "/api/v1/sessions/{session_id}/demo/end",
    response_model=DemoStatus,
    description="Synthetic demo only: end the fixture lecture using the demo professor credential.",
)
async def end_demo(grant: AuthorizedSession, services: Services) -> DemoStatus:
    """End only the synthetic lecture; host session CRUD remains separate."""
    if grant.role != "professor" or not isinstance(services.access, DemoSessionAccess):
        raise FeatureError("forbidden", "Demo professor access is required.", 403)
    services.access.is_ended = True
    return DemoStatus(session_id=grant.session_id, is_ended=True)


def register_features(app: FastAPI, services: FeatureServices) -> None:
    """Register the selected installed features with host-provided dependencies.

    This adds no demo lifecycle/auth routes. Hosts must enforce equivalent request
    limits, verify JWT/consent, and configure the selected typed services first.
    """
    if getattr(app.state, "lecture_feature_services", None) is not None:
        raise RuntimeError("Lecture features features are already registered.")
    app.state.lecture_feature_services = services
    for feature in installed_features(services.enabled_features):
        feature.register(app)


def create_demo_app(enabled_features: tuple[str, ...] | None = None) -> FastAPI:
    """Create a synthetic app containing only the requested installed feature routes."""
    app = FastAPI(
        title="Lumina isolated backend features",
        version="0.1.0",
        description="Synthetic identities and providers. Only features installed in this checkout are registered.",
    )
    app.add_middleware(BoundedJsonMiddleware)
    services = build_demo_services(enabled_features)
    register_features(app, services)
    app.include_router(demo_router)
    for feature in installed_features(enabled_features):
        feature.register_demo(app)

    @app.get("/health", response_model=HealthStatus, tags=["system"])
    def health() -> HealthStatus:
        """Return process liveness without checking external services."""
        return HealthStatus()

    return app


def create_app() -> FastAPI:
    """Refuse default startup unless the operator explicitly enables synthetic demo mode."""
    if os.environ.get("LUMINA_DEMO") != "1":
        raise RuntimeError(
            "Set LUMINA_DEMO=1 for a synthetic demo; use register_features for host integration."
        )
    return create_demo_app()
