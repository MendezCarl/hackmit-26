"""Explicit Dropbox selection, supporting-text access and derived export."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.dropbox.models import (
    ExportReceipt,
    ExportRequest,
    FilePage,
    FolderReceipt,
    FolderSelection,
    Material,
    MaterialRequest,
)
from app.timeline.dependencies import AuthorizedSession, Services
from app.timeline.http import ERROR_RESPONSES, FeatureRoute

router = APIRouter(
    prefix="/api/v1/sessions/{session_id}/dropbox",
    tags=["dropbox"],
    route_class=FeatureRoute,
    responses=ERROR_RESPONSES,
)


@router.put(
    "/folder",
    response_model=FolderReceipt,
    summary="Link a selected course folder",
    description="Bearer membership and host-approved Dropbox access required. Confirm a non-root folder in your account. No provider token is accepted or stored by this endpoint. Provider failure returns a redacted 502.",
)
async def link_folder(
    selection: FolderSelection, grant: AuthorizedSession, services: Services
) -> FolderReceipt:
    """Remember this user's explicitly selected folder for the authorized session."""
    return await services.dropbox.link(grant, selection)


@router.get(
    "/files",
    response_model=FilePage,
    summary="Browse selected text materials",
    description="Bearer membership and Dropbox consent required. Only text-file metadata inside your linked folder is returned, with bounded provider pagination. No course file is downloaded by listing.",
)
async def list_files(
    grant: AuthorizedSession,
    services: Services,
    cursor: Annotated[str | None, Query(max_length=4000)] = None,
) -> FilePage:
    """List one page of authorized supporting-material metadata."""
    return await services.dropbox.list_files(grant, cursor)


@router.post(
    "/materials",
    response_model=Material,
    summary="Read selected supporting text",
    description="Bearer membership and Dropbox consent required. Reads one explicitly selected UTF-8 .txt/.md file inside your linked folder. Size is capped; media/binary files return 415 and out-of-folder paths return 403. Content is returned only to the requesting member.",
)
async def read_material(
    request: MaterialRequest, grant: AuthorizedSession, services: Services
) -> Material:
    """Return selected bounded derived text and its source revision."""
    return await services.dropbox.read(grant, request)


@router.post(
    "/exports",
    response_model=ExportReceipt,
    summary="Export selected recovery notes",
    description="Bearer membership and Dropbox consent required, plus explicit confirmation. The host resolves and authorizes the artifact ID. Only derived Markdown is written inside your selected folder; existing files are not overwritten. Synthetic receipts are labeled mock.",
)
async def export_artifact(
    request: ExportRequest, grant: AuthorizedSession, services: Services
) -> ExportReceipt:
    """Write the authorized artifact and return its provider receipt."""
    return await services.dropbox.export(grant, request)
