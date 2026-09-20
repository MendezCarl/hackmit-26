"""Derived delivery ingestion keeps authority out of request bodies."""

import pytest
from app.contracts.learning import DeliveryBatch
from app.core.errors import AppError
from app.delivery.service import DeliveryService

from .support import actor, fixture


def test_delivery_authorization_duplicates_and_private_signal_separation():
    store, state, access, _ = fixture()
    service = DeliveryService(store, state, access)
    batch = DeliveryBatch.model_validate(
        {
            "events": [
                {
                    "event_id": "d",
                    "signal_type": "presenter_out_of_frame",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "confidence": 0.5,
                    "detector_version": "synthetic",
                    "evidence": {
                        "sample_count": 2,
                        "positive_sample_count": 1,
                        "performance_profile": "low_power",
                    },
                }
            ]
        }
    )
    with pytest.raises(AppError):
        service.ingest(actor(), "s", batch)
    assert service.ingest(actor("prof", "professor"), "s", batch).accepted == 1
    assert service.ingest(actor("prof", "professor"), "s", batch).duplicates == 1
    assert not store.events
