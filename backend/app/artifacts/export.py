"""Recovery-to-export bridge with a mock destination for the end-to-end MVP.

The existing Dropbox branch supplies a live SDK boundary separately. This bridge
requires an injected authorized destination; it never accepts arbitrary text.
"""

from threading import RLock
from typing import Annotated, Literal, Protocol
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from app.auth.dependencies import get_current_actor
from app.auth.tokens import AuthenticatedActor
from app.contracts.learning import Identifier, StrictPayload
from app.contracts.models import ErrorResponse
from app.core.errors import AppError, ErrorCode


class FolderSelection(StrictPayload):
    """Explicit selection of a provider-authorized folder identifier."""

    folder_id: Identifier


class ArtifactExport(StrictPayload):
    """Export an existing own recovery card; request bodies cannot supply file contents."""

    card_id: Identifier
    filename: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}\.md$")
    is_confirmed: bool


class ExportReceipt(StrictPayload):
    """Receipt distinguishes synthetic destination writes from real provider success."""

    export_id: Identifier
    provider_mode: Literal["mock", "live"]
    filename: str


class ArtifactDestination(Protocol):
    """Actor-scoped provider destination supplied by the host after OAuth."""

    def verify_folder(self, actor: AuthenticatedActor, folder_id: str) -> None:
        """Raise AppError if folder is unauthorized or unavailable."""
        ...

    def write(
        self, actor: AuthenticatedActor, folder_id: str, filename: str, text: str
    ) -> ExportReceipt:
        """Create selected derived Markdown without overwriting; return a truthful receipt."""
        ...


class MockArtifactDestination:
    """Bounded synthetic course folder; never contacts Dropbox or writes local files."""

    def __init__(self) -> None:
        """Create independent per-instance simulated exports."""
        self.exports: dict[tuple[str, str, str], str] = {}
        self.lock = RLock()

    def verify_folder(self, actor: AuthenticatedActor, folder_id: str) -> None:
        """Allow only the clearly synthetic demo folder."""
        if folder_id != "synthetic-course-folder":
            raise AppError(ErrorCode.NOT_FOUND, "Selected folder was not found.")

    def write(
        self, actor: AuthenticatedActor, folder_id: str, filename: str, text: str
    ) -> ExportReceipt:
        """Simulate one create-only actor-scoped write under a capacity bound."""
        self.verify_folder(actor, folder_id)
        key = (actor.user_id, folder_id, filename)
        with self.lock:
            if key in self.exports:
                raise AppError(
                    ErrorCode.DUPLICATE,
                    "Choose a new filename; exports never overwrite.",
                )
            if len(self.exports) >= 1000:
                raise AppError(
                    ErrorCode.PAYLOAD_TOO_LARGE, "Synthetic export capacity reached."
                )
            self.exports[key] = text
        return ExportReceipt(
            export_id="export_" + uuid4().hex, provider_mode="mock", filename=filename
        )


class ExportService:
    """Authorize the card at write time and require explicit destination selection."""

    def __init__(self, destination: ArtifactDestination | None) -> None:
        """Inject an authorized provider or leave export unavailable."""
        self.destination = destination
        self.folders: dict[tuple[str, str], str] = {}


router = APIRouter(
    prefix="/api/v1/sessions/{session_id}/artifacts",
    tags=["artifacts"],
    responses={
        code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 413, 422, 502)
    },
)
Actor = Annotated[AuthenticatedActor, Depends(get_current_actor)]


@router.put(
    "/folder",
    response_model=FolderSelection,
    description="JWT member selects their own authorized course folder. Default destination is synthetic in demo/test only.",
)
def select_folder(
    session_id: str, body: FolderSelection, actor: Actor, request: Request
) -> FolderSelection:
    """Verify provider scope before recording actor/session-specific selection."""
    request.app.state.session_access.resolve_membership(actor, session_id)
    service = request.app.state.artifact_exports
    if service.destination is None:
        raise AppError(ErrorCode.PROVIDER_FAILURE, "Artifact export is not configured.")
    service.destination.verify_folder(actor, body.folder_id)
    if len(service.folders) >= 1000:
        raise AppError(ErrorCode.PAYLOAD_TOO_LARGE, "Folder selection capacity reached.")
    service.folders[(session_id, actor.user_id)] = body.folder_id
    return body


@router.post(
    "/exports",
    response_model=ExportReceipt,
    description="JWT card owner confirms create-only export to their selected folder. Accepts a card reference, not arbitrary text or raw media. Mock receipts do not imply live Dropbox success.",
)
def export_card(
    session_id: str, body: ArtifactExport, actor: Actor, request: Request
) -> ExportReceipt:
    """Read the authorized derived card and export bounded Markdown after confirmation."""
    service = request.app.state.artifact_exports
    card = request.app.state.recovery_service.get_card(actor, session_id, body.card_id)
    folder = service.folders.get((session_id, actor.user_id))
    if not body.is_confirmed or folder is None:
        raise AppError(ErrorCode.FORBIDDEN, "Select a folder and confirm this export.")
    if service.destination is None:
        raise AppError(ErrorCode.PROVIDER_FAILURE, "Artifact export is not configured.")
    text = (
        "# "
        + card.topic
        + "\n\n"
        + card.what_you_missed
        + "\n\n"
        + "\n".join("- " + fact for fact in card.key_facts)
    )
    text += "\n\nSources: " + ", ".join(
        f"{s.start_ms}–{s.end_ms} ms" for s in card.source_timestamps
    )
    if len(text) > 20_000:
        raise AppError(
            ErrorCode.PAYLOAD_TOO_LARGE, "Derived artifact exceeds the export limit."
        )
    return service.destination.write(actor, folder, body.filename, text)
