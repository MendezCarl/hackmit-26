"""Session/account scoped folder linking, selected materials, and safe export."""

from pathlib import PurePosixPath

from app.dropbox.models import (
    MAX_ARTIFACT_BYTES,
    ExportReceipt,
    ExportRequest,
    FilePage,
    FolderLink,
    FolderReceipt,
    FolderSelection,
    Material,
    MaterialRequest,
)
from app.dropbox.ports import ArtifactReader, DropboxGateway
from app.timeline.contracts import FeatureError, SessionGrant
from app.timeline.repository import SessionRepository, SessionState, mutate_session


def is_within_folder(file_path: str, folder_path: str) -> bool:
    """Check a segment boundary, so /course-other never matches /course."""
    return file_path.casefold().startswith(folder_path.casefold() + "/")


class DropboxService:
    """Restrict provider I/O to explicitly selected folders and authorized artifacts."""

    def __init__(
        self,
        repository: SessionRepository,
        gateway: DropboxGateway,
        artifacts: ArtifactReader,
    ) -> None:
        """Inject storage, an actor-isolated provider, and the host artifact reader."""
        self.repository = repository
        self.gateway = gateway
        self.artifacts = artifacts

    def _require_access(self, grant: SessionGrant) -> None:
        """Reject provider operations unless the host grants Dropbox consent/access."""
        if not grant.can_use_dropbox:
            raise FeatureError(
                "consent_required", "Dropbox access is not authorized.", 403
            )

    async def link(
        self, grant: SessionGrant, selection: FolderSelection
    ) -> FolderReceipt:
        """Verify and remember this actor's explicit folder choice for this session."""
        self._require_access(grant)
        await self.gateway.verify_folder(grant.actor_id, selection.folder_path)

        def change(state: SessionState) -> tuple[FolderReceipt, bool]:
            state.folder_links = [
                link for link in state.folder_links if link.actor_id != grant.actor_id
            ]
            if len(state.folder_links) >= 1000:
                raise FeatureError(
                    "session_capacity", "Folder-link capacity reached.", 413
                )
            state.folder_links.append(
                FolderLink(actor_id=grant.actor_id, folder_path=selection.folder_path)
            )
            return FolderReceipt(
                folder_path=selection.folder_path, provider_mode=self.gateway.mode
            ), True

        return await mutate_session(self.repository, grant.session_id, change)

    async def _folder(self, grant: SessionGrant) -> str:
        """Resolve this actor's linked folder; never reuse another actor's selection."""
        self._require_access(grant)
        state = await self.repository.load(grant.session_id)
        for link in state.folder_links:
            if link.actor_id == grant.actor_id:
                return link.folder_path
        raise FeatureError("folder_not_linked", "Select a course folder first.", 409)

    async def list_files(
        self, grant: SessionGrant, cursor: str | None = None
    ) -> FilePage:
        """List text materials; constrain provider results even for supplied cursors."""
        folder = await self._folder(grant)
        page = await self.gateway.list_files(grant.actor_id, folder, cursor)
        return FilePage(
            files=[
                entry
                for entry in page.files
                if is_within_folder(entry.file_path, folder)
            ],
            next_cursor=page.next_cursor,
        )

    async def read(self, grant: SessionGrant, request: MaterialRequest) -> Material:
        """Read a selected text source; reject traversal, other folders and media types."""
        folder = await self._folder(grant)
        if not is_within_folder(request.file_path, folder):
            raise FeatureError(
                "file_outside_folder", "Select a file within the linked folder.", 403
            )
        if PurePosixPath(request.file_path).suffix.lower() not in {".txt", ".md"}:
            raise FeatureError(
                "unsupported_material",
                "Only UTF-8 text and Markdown materials are supported.",
                415,
            )
        material = await self.gateway.read_text(grant.actor_id, request.file_path)
        if material.file_path.casefold() != request.file_path.casefold():
            raise FeatureError(
                "provider_response_invalid",
                "Provider returned an unexpected source.",
                502,
            )
        return material

    async def export(
        self, grant: SessionGrant, request: ExportRequest
    ) -> ExportReceipt:
        """Export an authorized derived artifact; never accept arbitrary upload content."""
        folder = await self._folder(grant)
        artifact = await self.artifacts.read(grant, request.artifact_id)
        if artifact.artifact_id != request.artifact_id:
            raise FeatureError(
                "artifact_mismatch", "Selected artifact could not be resolved.", 409
            )
        if len(artifact.markdown.encode("utf-8")) > MAX_ARTIFACT_BYTES:
            raise FeatureError(
                "artifact_too_large", "Derived artifact exceeds the export limit.", 413
            )
        path = f"{folder}/{request.filename}"
        revision = await self.gateway.write_text(
            grant.actor_id, path, artifact.markdown
        )
        return ExportReceipt(
            artifact_id=request.artifact_id,
            file_path=path,
            revision=revision,
            provider_mode=self.gateway.mode,
        )
