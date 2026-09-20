"""Fixtures limited to the lecture features' tests; never alter the shared test configuration."""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient

from app.timeline.application import create_demo_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Yield a fresh all-synthetic feature app for each test."""
    with TestClient(create_demo_app()) as client:
        yield client
