"""Selected-folder boundaries, artifact ownership, safe exports and provider mocks."""

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import Mock

import pytest
from app.dropbox.models import MAX_MATERIAL_BYTES
from app.integrations.dropbox.client import SdkDropboxGateway
from app.timeline.contracts import FeatureError
from dropbox.files import FileMetadata, FolderMetadata, ListFolderResult
from fastapi.testclient import TestClient
from requests.exceptions import Timeout

from .factories import BASE, authorization


def link_folder(client: TestClient, actor: str = "student-1") -> None:
    """Select the synthetic course folder for one synthetic actor."""
    assert (
        client.put(
            f"{BASE}/dropbox/folder",
            headers=authorization(actor),
            json={"folder_path": "/course", "confirmed": True},
        ).status_code
        == 200
    )


def test_selected_material_and_derived_export(client: TestClient) -> None:
    """Read only selected text and export a trusted artifact with an explicit mock label."""
    link_folder(client)
    files = client.get(f"{BASE}/dropbox/files", headers=authorization()).json()
    assert files["files"][0]["file_path"] == "/course/notes.md"
    material = client.post(
        f"{BASE}/dropbox/materials",
        headers=authorization(),
        json={"file_path": "/course/notes.md"},
    )
    assert "last-in" in material.json()["text"]
    request = {"artifact_id": "demo-card", "filename": "recovery.md", "confirmed": True}
    result = client.post(
        f"{BASE}/dropbox/exports", headers=authorization(), json=request
    )
    assert result.status_code == 200
    assert result.json()["provider_mode"] == "mock"
    assert result.json()["file_path"] == "/course/recovery.md"
    assert (
        client.post(
            f"{BASE}/dropbox/exports", headers=authorization(), json=request
        ).status_code
        == 409
    )


def test_folder_selection_and_artifacts_are_actor_scoped(client: TestClient) -> None:
    """One user's folder selection or card never grants access to another user."""
    link_folder(client)
    assert (
        client.get(
            f"{BASE}/dropbox/files", headers=authorization("student-2")
        ).status_code
        == 409
    )
    link_folder(client, "student-2")
    assert (
        client.post(
            f"{BASE}/dropbox/exports",
            headers=authorization("student-2"),
            json={
                "artifact_id": "demo-card",
                "filename": "other.md",
                "confirmed": True,
            },
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"{BASE}/dropbox/files", headers=authorization("professor")
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "path, status",
    [
        ("/course-other/notes.md", 403),
        ("/private/notes.md", 403),
        ("/course/../private.md", 422),
        ("/course//notes.md", 422),
        ("/course\\private.md", 422),
        ("/course/audio.wav", 415),
        ("/course/screenshot.png", 415),
        ("id:private-file", 422),
    ],
)
def test_selected_folder_and_media_boundaries(
    client: TestClient, path: str, status: int
) -> None:
    """Path segment checks, traversal rejection and text allowlists hold at the API."""
    link_folder(client)
    assert (
        client.post(
            f"{BASE}/dropbox/materials",
            headers=authorization(),
            json={"file_path": path},
        ).status_code
        == status
    )


@pytest.mark.parametrize(
    "export_payload",
    [
        {"artifact_id": "demo-card", "filename": "../escape.md", "confirmed": True},
        {"artifact_id": "demo-card", "filename": "card.md", "confirmed": False},
        {
            "artifact_id": "demo-card",
            "filename": "card.md",
            "confirmed": True,
            "raw_audio": "PRIVATE-MARKER",
        },
    ],
)
def test_exports_require_explicit_safe_selection(
    client: TestClient, export_payload: dict[str, Any]
) -> None:
    """No caller-uploaded bytes, ambiguous filename or unconfirmed export is accepted."""
    link_folder(client)
    response = client.post(
        f"{BASE}/dropbox/exports", headers=authorization(), json=export_payload
    )
    assert response.status_code == 422
    assert "PRIVATE-MARKER" not in response.text


def file_metadata(path: str = "/course/notes.md", size: int = 20) -> FileMetadata:
    """Build real SDK metadata with synthetic values for adapter contract tests."""
    return FileMetadata(
        name="notes.md",
        id="id:synthetic",
        client_modified=datetime(2026, 1, 1, tzinfo=UTC),
        server_modified=datetime(2026, 1, 1, tzinfo=UTC),
        rev="123456789",
        size=size,
        path_lower=path,
    )


def test_sdk_listing_and_revision_pinned_streaming() -> None:
    """Match real SDK methods, filter media and close bounded download responses."""
    sdk = Mock()
    sdk.files_get_metadata.return_value = file_metadata()
    sdk.files_list_folder.return_value = ListFolderResult(
        entries=[file_metadata(), file_metadata("/course/video.mp4")],
        cursor="next-page",
        has_more=True,
    )
    response = Mock()
    response.iter_content.return_value = [b"Synthetic ", b"course notes"]
    sdk.files_download.return_value = (file_metadata(), response)
    gateway = SdkDropboxGateway(lambda actor: sdk)
    page = asyncio.run(gateway.list_files("student-1", "/course", None))
    assert len(page.files) == 1
    assert page.next_cursor == "next-page"
    material = asyncio.run(gateway.read_text("student-1", "/course/notes.md"))
    assert material.text == "Synthetic course notes"
    sdk.files_download.assert_called_once_with("rev:123456789")
    response.close.assert_called_once()


def test_sdk_size_checks_before_and_during_download() -> None:
    """Reject metadata oversize before download and dishonest streams during download."""
    sdk = Mock()
    sdk.files_get_metadata.return_value = file_metadata(size=MAX_MATERIAL_BYTES + 1)
    gateway = SdkDropboxGateway(lambda actor: sdk)
    with pytest.raises(FeatureError, match="size limit"):
        asyncio.run(gateway.read_text("student-1", "/course/notes.md"))
    sdk.files_download.assert_not_called()
    sdk.files_get_metadata.return_value = file_metadata()
    response = Mock()
    response.iter_content.return_value = [b"x" * (MAX_MATERIAL_BYTES + 1)]
    sdk.files_download.return_value = (file_metadata(), response)
    with pytest.raises(FeatureError, match="size limit"):
        asyncio.run(gateway.read_text("student-1", "/course/notes.md"))
    response.close.assert_called_once()


def test_sdk_timeout_is_redacted() -> None:
    """Provider exceptions cannot expose tokens, private paths or provider bodies."""
    sdk = Mock()
    sdk.files_get_metadata.side_effect = Timeout("SECRET-TOKEN PRIVATE-PATH")
    gateway = SdkDropboxGateway(lambda actor: sdk)
    with pytest.raises(FeatureError) as caught:
        asyncio.run(gateway.verify_folder("student-1", "/course"))
    assert caught.value.code == "dropbox_unavailable"
    assert "SECRET" not in str(caught.value)


def test_sdk_folder_and_create_only_upload() -> None:
    """Use the official SDK's folder type and explicit no-overwrite upload flags."""
    sdk = Mock()
    sdk.files_get_metadata.return_value = FolderMetadata(
        name="course", id="id:folder", path_lower="/course"
    )
    sdk.files_upload.return_value = file_metadata("/course/recovery.md")
    actors: list[str] = []

    def resolve(actor: str) -> Any:
        actors.append(actor)
        return sdk

    gateway = SdkDropboxGateway(resolve)
    asyncio.run(gateway.verify_folder("student-1", "/course"))
    assert (
        asyncio.run(
            gateway.write_text("student-1", "/course/recovery.md", "Synthetic note")
        )
        == "123456789"
    )
    assert actors == ["student-1", "student-1"]
    assert sdk.files_upload.call_args.kwargs["autorename"] is False
    assert sdk.files_upload.call_args.kwargs["strict_conflict"] is True
