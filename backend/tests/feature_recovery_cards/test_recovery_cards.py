"""Private recovery service denies other members, including the session owner."""

import pytest

from app.contracts.models import CreateRecoveryJobRequest
from app.core.errors import AppError
from app.main import create_app
from app.recovery.generator import DeterministicRecoveryGenerator
from app.recovery.validated import PrivateRecoveryService, ValidatedGenerator
from app.transcript.repository import InMemoryTimelineReader

from .support import actor, fixture


def test_private_jobs_and_content_cache():
    store, state, access, settings = fixture()
    host = create_app(settings).state
    service = PrivateRecoveryService(
        store,
        settings,
        access,
        InMemoryTimelineReader(store),
        ValidatedGenerator(DeterministicRecoveryGenerator()),
        host.signal_service,
        host.cost_ledger,
        host.event_publisher,
    )
    service.configure_privacy(state)
    request = CreateRecoveryJobRequest(start_ms=0, end_ms=20_000)
    job = service.create_job(actor("student2"), "s", request)
    with pytest.raises(AppError):
        service.get_job(actor(), "s", job.job_id)
    with pytest.raises(AppError):
        service.get_card(actor(), "s", job.card_id)
    assert service.create_job(actor("student2"), "s", request).cache_status == "hit"
    store.transcript_chunks["s"][0].text = "A queue follows first-in, first-out ordering."
    assert service.create_job(actor("student2"), "s", request).cache_status == "miss"
