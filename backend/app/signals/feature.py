"""Feature 2 registration; no professor or Dropbox implementation is imported."""

from fastapi import FastAPI
from pydantic import BaseModel

from app.integrations.zoom.transcript import SimulatedZoomBatch
from app.signals.models import SignalBatch, SignalEvent, SignalFeedback, SignalRules
from app.signals.routes import router as signals_router
from app.signals.service import SignalService
from app.timeline.dependencies import FeatureServices
from app.timeline.models import ContextWindow, TimelinePage
from app.timeline.routes import router as timeline_router
from app.timeline.service import TimelineService
from app.transcript.models import TranscriptBatch, TranscriptMessage
from app.transcript.routes import router as transcript_router
from app.transcript.service import TranscriptService
from app.transcript.websocket import router as socket_router
from app.zoom.routes import router as zoom_router

KEY = "signal_timeline"


def configure_demo(services: FeatureServices) -> None:
    """Install in-memory timeline services against the supplied shared repository."""
    rules = SignalRules()
    services.signals = SignalService(services.repository, rules)
    services.transcripts = TranscriptService(services.repository)
    services.timeline = TimelineService(services.repository, rules)


def register(app: FastAPI) -> None:
    """Add authorized signal, transcript, timeline and transcript-WebSocket routes."""
    for router in (signals_router, transcript_router, timeline_router, socket_router):
        app.include_router(router)


def register_demo(app: FastAPI) -> None:
    """Add the explicitly synthetic Zoom transcript adapter only to demo apps."""
    app.include_router(zoom_router)


def public_models() -> list[type[BaseModel]]:
    """Return public feature 2 payload models for contract generation."""
    return [
        SignalBatch,
        SignalEvent,
        SignalFeedback,
        TranscriptBatch,
        TranscriptMessage,
        ContextWindow,
        TimelinePage,
        SimulatedZoomBatch,
    ]
