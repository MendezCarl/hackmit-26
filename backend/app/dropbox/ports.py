"""Provider and recovery-artifact ports, with credentials owned by the host."""

from typing import Literal, Protocol

from app.dropbox.models import DerivedArtifact, FilePage, Material
from app.timeline.contracts import SessionGrant


class DropboxGateway(Protocol):
    """Account-isolated provider operations, with safe FeatureError failures."""

    mode: Literal["mock", "live"]

    async def verify_folder(self, actor_id: str, folder_path: str) -> None:
        """Verify that the selected folder exists in this actor's authorized account."""
        ...

    async def list_files(
        self, actor_id: str, folder_path: str, cursor: str | None
    ) -> FilePage:
        """Return one page of bounded text-file metadata, or raise FeatureError."""
        ...

    async def read_text(self, actor_id: str, file_path: str) -> Material:
        """Download bounded UTF-8 text; reject binary/oversized content."""
        ...

    async def write_text(self, actor_id: str, file_path: str, text: str) -> str:
        """Create a derived artifact without overwriting; return its revision."""
        ...


class ArtifactReader(Protocol):
    """Person A supplies authorization-checked recovery cards and review notes."""

    async def read(self, grant: SessionGrant, artifact_id: str) -> DerivedArtifact:
        """Return this actor's selected derived artifact, or raise a safe error."""
        ...
