"""Provider-neutral selected-folder and derived-text contracts."""

from typing import Annotated, Literal

from pydantic import Field, field_validator

from app.timeline.contracts import Identifier, StrictModel

MAX_MATERIAL_BYTES = 100_000
MAX_ARTIFACT_BYTES = 100_000


def validate_dropbox_path(value: str) -> str:
    """Return an absolute provider path; reject traversal and ambiguous separators."""
    if (
        not value.startswith("/")
        or value == "/"
        or any(part in ("", ".", "..") for part in value[1:].split("/"))
        or "\\" in value
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError("Choose a non-root absolute Dropbox path without traversal.")
    return value


class FolderSelection(StrictModel):
    """Explicitly select a non-root folder in the authenticated user's Dropbox."""

    folder_path: Annotated[str, Field(min_length=2, max_length=500)]
    confirmed: Literal[True]

    _validate_folder = field_validator("folder_path")(validate_dropbox_path)


class FolderLink(StrictModel):
    """Internal session/user-specific folder selection; never a bearer credential."""

    actor_id: Identifier
    folder_path: str


class FolderReceipt(StrictModel):
    """The selected folder and whether operations are simulated."""

    folder_path: str
    provider_mode: Literal["mock", "live"]


class MaterialRequest(StrictModel):
    """Read only a selected UTF-8 .txt or .md file inside the linked folder."""

    file_path: Annotated[str, Field(min_length=2, max_length=500)]
    _validate_path = field_validator("file_path")(validate_dropbox_path)


class Material(StrictModel):
    """Bounded supporting text with its provider revision and source reference."""

    file_path: str
    revision: str
    text: Annotated[str, Field(max_length=MAX_MATERIAL_BYTES)]


class FileEntry(StrictModel):
    """Authorized text-file metadata, without file content."""

    file_path: str
    size_bytes: Annotated[int, Field(ge=0)]
    revision: str


class FilePage(StrictModel):
    """Provider listing capped at 100 files; cursor remains scoped to a linked folder."""

    files: list[FileEntry]
    next_cursor: str | None = None


class DerivedArtifact(StrictModel):
    """Trusted, authorized artifact fetched from Person A, not arbitrary upload bytes."""

    artifact_id: Identifier
    kind: Literal["recovery_card", "review_notes"]
    markdown: Annotated[str, Field(min_length=1, max_length=MAX_ARTIFACT_BYTES)]


class ExportRequest(StrictModel):
    """Explicit export selection; existing provider files are never overwritten."""

    artifact_id: Identifier
    filename: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}\.md$")]
    confirmed: Literal[True]


class ExportReceipt(StrictModel):
    """Actual provider response or an explicitly labeled synthetic receipt."""

    artifact_id: Identifier
    file_path: str
    revision: str
    provider_mode: Literal["mock", "live"]
