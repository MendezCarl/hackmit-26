"""Selected mock exports cannot overwrite or claim live provider success."""

import pytest
from app.artifacts.export import MockArtifactDestination
from app.core.errors import AppError

from .support import actor


def test_export_scope_and_create_only_write():
    destination = MockArtifactDestination()
    with pytest.raises(AppError):
        destination.write(actor(), "unselected", "review.md", "Synthetic text")
    assert (
        destination.write(
            actor(), "synthetic-course-folder", "review.md", "Synthetic text"
        ).provider_mode
        == "mock"
    )
    with pytest.raises(AppError):
        destination.write(
            actor(), "synthetic-course-folder", "review.md", "Replacement"
        )
    assert (
        destination.write(
            actor("student2"), "synthetic-course-folder", "review.md", "Other own text"
        ).provider_mode
        == "mock"
    )
