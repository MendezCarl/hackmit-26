"""Request-local demo composition: real domain services, synthetic data and mocks."""

from app.auth.access import StoreSessionAccess
from app.config import Settings
from app.contracts.learning import MetricsPolicy
from app.cost.ledger import CostLedger
from app.demo.runner import DemoRunner
from app.learning.state import LearningState
from app.professor.metrics import ProfessorMetricsService
from app.professor.service import ProfessorService
from app.recovery.generator import DeterministicRecoveryGenerator
from app.recovery.validated import PrivateRecoveryService, ValidatedGenerator
from app.sessions.service import SessionService
from app.signals.service import SignalService
from app.storage.in_memory import InMemoryStore
from app.transcript.repository import InMemoryTimelineReader
from app.transcript.service import TranscriptService
from app.ws.publisher import WebSocketEventPublisher


def build_demo_runner() -> DemoRunner:
    """Return a fresh mock-only scenario with no access to application session state.

    All created state lives for one request. No environment credentials, host
    providers, socket subscribers or user settings are consulted; no I/O occurs.
    """
    settings = Settings(app_env="demo", provider_mode="mock")
    store, state, ledger = InMemoryStore(), LearningState(), CostLedger()
    access, publisher = StoreSessionAccess(store), WebSocketEventPublisher()
    timeline = InMemoryTimelineReader(store)
    sessions = SessionService(store, settings, access)
    signals = SignalService(store, settings, access, publisher)
    transcript = TranscriptService(store, settings, access, timeline, publisher)
    recovery = PrivateRecoveryService(
        store,
        settings,
        access,
        timeline,
        ValidatedGenerator(DeterministicRecoveryGenerator()),
        signals,
        ledger,
        publisher,
    )
    recovery.configure_privacy(state)
    professor = ProfessorService(store, settings, access, signals, publisher)
    metrics = ProfessorMetricsService(
        store,
        state,
        access,
        settings,
        MetricsPolicy(
            policy_version="synthetic-demo-v1", minimum_group_size=5, bucket_ms=30_000
        ),
    )
    return DemoRunner(sessions, signals, transcript, recovery, professor, metrics, ledger)
