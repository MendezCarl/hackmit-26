"""Feature 6 registration; artifacts and provider credentials remain injected."""

from fastapi import FastAPI
from pydantic import BaseModel

from app.dropbox.demo import DemoArtifactReader, DemoDropboxGateway
from app.dropbox.models import (
    ExportReceipt,
    ExportRequest,
    FilePage,
    FolderReceipt,
    FolderSelection,
    Material,
    MaterialRequest,
)
from app.dropbox.routes import router
from app.dropbox.service import DropboxService
from app.timeline.dependencies import FeatureServices

KEY = "dropbox_integration"


def configure_demo(services: FeatureServices) -> None:
    """Install fake provider I/O and a synthetic authorized artifact reader."""
    services.dropbox = DropboxService(
        services.repository, DemoDropboxGateway(), DemoArtifactReader()
    )


def register(app: FastAPI) -> None:
    """Add only the authorized selected-folder/material/export endpoints."""
    app.include_router(router)


def register_demo(app: FastAPI) -> None:
    """No additional feature-specific demo endpoint is required."""


def public_models() -> list[type[BaseModel]]:
    """Return public feature 6 payload models for contract generation."""
    return [
        FolderSelection,
        FolderReceipt,
        FilePage,
        MaterialRequest,
        Material,
        ExportRequest,
        ExportReceipt,
    ]
