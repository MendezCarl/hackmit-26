"""FastAPI application entry point, system endpoints, and app composition."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.auth.access import StoreSessionAccess
from app.config import LIVE_PROVIDER_MODE, Settings, get_settings
from app.core.body_limits import DerivedJsonLimit
from app.core.errors import install_error_handlers
from app.cost.ledger import CostLedger
from app.demo.routes import router as demo_router
from app.learning.composition import install_learning_features
from app.professor.routes import router as professor_router
from app.professor.service import ProfessorService
from app.recovery.generator import DeterministicRecoveryGenerator, RecoveryGenerator
from app.recovery.routes import router as recovery_router
from app.recovery.validated import PrivateRecoveryService, ValidatedGenerator
from app.sessions.routes import router as session_router
from app.sessions.service import SessionService
from app.signals.routes import router as signal_router
from app.signals.service import SignalService
from app.storage.in_memory import InMemoryStore
from app.transcript.repository import InMemoryTimelineReader
from app.transcript.routes import router as transcript_router
from app.transcript.service import TranscriptService
from app.ws.publisher import WebSocketEventPublisher
from app.ws.routes import router as websocket_router

OPENAPI_TAGS = [
    {"name": "system", "description": "Liveness and API readiness endpoints."},
    {"name": "sessions", "description": "Lecture-session lifecycle."},
    {"name": "signals", "description": "Coarse signal events and participants."},
    {"name": "transcript", "description": "Transcript ingestion and timeline reads."},
    {"name": "recovery", "description": "Recovery jobs, cards, and cost metrics."},
    {"name": "professor", "description": "Anonymous, threshold-safe summaries."},
    {"name": "demo", "description": "Gated synthetic demo orchestration."},
]


class HealthResponse(BaseModel):
    """Response returned by the liveness endpoint."""

    status: str = Field(description="Current process health state.", examples=["ok"])


class ApiStatusResponse(BaseModel):
    """Response describing whether the API is ready."""

    message: str = Field(
        description="Human-readable API status message.",
        examples=["FastAPI backend is ready."],
    )


def create_app(
    settings: Settings | None = None,
    recovery_generator: RecoveryGenerator | None = None,
) -> FastAPI:
    """Compose the application with injected settings and dependencies.

    Args:
        settings: Application settings; resolved from the environment when
            omitted.
        recovery_generator: Optional generator override for provider-failure
            tests; defaults to the deterministic mock.

    Returns:
        The fully wired FastAPI application.
    """

    if settings is None:
        settings = get_settings()
    if settings.provider_mode == LIVE_PROVIDER_MODE and recovery_generator is None:
        import os

        from openai import OpenAI

        from app.integrations.openai.recovery import OpenAIRecoveryGenerator

        model = os.environ.get("OPENAI_MODEL", "")
        if not os.environ.get("OPENAI_API_KEY") or not model:
            raise RuntimeError("Live mode requires OPENAI_API_KEY and OPENAI_MODEL.")
        recovery_generator = OpenAIRecoveryGenerator(
            OpenAI(timeout=20.0, max_retries=1), model
        )

    app = FastAPI(
        title="Lecture Recovery Assistant API",
        summary="Backend API for privacy-first lecture recovery.",
        description=(
            "Typed REST endpoints for lecture sessions, recovery cards, "
            "integrations, and anonymous professor summaries."
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
    app.add_middleware(DerivedJsonLimit)
    install_error_handlers(app)

    store = InMemoryStore()
    session_access = StoreSessionAccess(store)
    event_publisher = WebSocketEventPublisher()
    cost_ledger = CostLedger()
    generator = ValidatedGenerator(
        recovery_generator or DeterministicRecoveryGenerator()
    )

    session_service = SessionService(store, settings, session_access)
    signal_service = SignalService(store, settings, session_access, event_publisher)
    timeline_reader = InMemoryTimelineReader(store)
    transcript_service = TranscriptService(
        store, settings, session_access, timeline_reader, event_publisher
    )
    recovery_service = PrivateRecoveryService(
        store,
        settings,
        session_access,
        timeline_reader,
        generator,
        signal_service,
        cost_ledger,
        event_publisher,
    )
    professor_service = ProfessorService(
        store, settings, session_access, signal_service, event_publisher
    )

    app.state.settings = settings
    app.state.store = store
    app.state.session_access = session_access
    app.state.event_publisher = event_publisher
    app.state.cost_ledger = cost_ledger
    app.state.recovery_generator = generator
    app.state.session_service = session_service
    app.state.signal_service = signal_service
    app.state.transcript_service = transcript_service
    app.state.recovery_service = recovery_service
    app.state.professor_service = professor_service

    install_learning_features(app)

    app.include_router(session_router)
    app.include_router(signal_router)
    app.include_router(transcript_router)
    app.include_router(recovery_router)
    app.include_router(professor_router)
    app.include_router(demo_router)
    app.include_router(websocket_router)

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["system"],
        summary="Check process health",
    )
    def read_health() -> HealthResponse:
        """Return the current process liveness state.

        Returns:
            A typed response whose status is ``ok`` while the process runs.
        """

        return HealthResponse(status="ok")

    @app.get(
        "/api/status",
        response_model=ApiStatusResponse,
        tags=["system"],
        summary="Check API readiness",
    )
    def read_api_status() -> ApiStatusResponse:
        """Return a human-readable readiness message for the frontend.

        Returns:
            A typed status response confirming that the API is ready.
        """

        return ApiStatusResponse(message="FastAPI backend is ready.")

    return app


app = create_app()
