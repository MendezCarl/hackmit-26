"""Feature 6 synthetic providers and authorized artifact fixture."""

from typing import Literal

from app.dropbox.models import DerivedArtifact, FileEntry, FilePage, Material
from app.timeline.contracts import FeatureError, SessionGrant


class DemoDropboxGateway:
    """In-memory Dropbox fake with per-actor storage and explicit mock receipts."""

    mode: Literal["mock", "live"] = "mock"

    def __init__(self) -> None:
        """Create an empty synthetic export store; no network or filesystem I/O."""
        self.exports: dict[tuple[str, str], str] = {}

    async def verify_folder(self, actor_id: str, folder_path: str) -> None:
        """Only /course exists in the synthetic account."""
        if folder_path != "/course":
            raise FeatureError("folder_not_found", "Selected folder was not found.", 404)

    async def list_files(
        self, actor_id: str, folder_path: str, cursor: str | None
    ) -> FilePage:
        """Return one synthetic text source; no follow-up cursor exists."""
        if cursor:
            raise FeatureError("invalid_cursor", "The page cursor is invalid.")
        return FilePage(
            files=[
                FileEntry(
                    file_path="/course/notes.md", size_bytes=42, revision="synthetic-1"
                )
            ]
        )

    async def read_text(self, actor_id: str, file_path: str) -> Material:
        """Return synthetic learning material for the one fixture file."""
        if file_path != "/course/notes.md":
            raise FeatureError("file_not_found", "Selected material was not found.", 404)
        return Material(
            file_path=file_path,
            revision="synthetic-1",
            text="A stack follows last-in, first-out ordering.",
        )

    async def write_text(self, actor_id: str, file_path: str, text: str) -> str:
        """Simulate create-only export; reject overwriting existing synthetic files."""
        key = (actor_id, file_path)
        if key in self.exports or file_path == "/course/notes.md":
            raise FeatureError("file_conflict", "Choose a new export filename.", 409)
        self.exports[key] = text
        return "synthetic-export-1"


class DemoArtifactReader:
    """Stand-in for Person A's authorized recovery artifact lookup."""

    async def read(self, grant: SessionGrant, artifact_id: str) -> DerivedArtifact:
        """Return one synthetic card, exclusively for student-1."""
        if grant.actor_id != "student-1" or artifact_id != "demo-card":
            raise FeatureError(
                "artifact_not_found", "Selected artifact was not found.", 404
            )
        return DerivedArtifact(
            artifact_id=artifact_id,
            kind="recovery_card",
            markdown="# Synthetic recovery card\n\nA stack follows last-in, first-out ordering.\n",
        )
