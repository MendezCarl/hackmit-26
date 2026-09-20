"""Bounded Dropbox SDK operations using host-provided account-specific clients.

OAuth and encrypted token storage remain with Person A. This adapter never accepts
tokens in application requests, persists credentials, or implements OAuth itself.
"""

import asyncio
from collections.abc import Callable
from contextlib import closing
from pathlib import PurePosixPath
from typing import Any, Literal, TypeVar

from app.dropbox.models import MAX_MATERIAL_BYTES, FileEntry, FilePage, Material
from app.timeline.contracts import FeatureError

Result = TypeVar("Result")
DOWNLOAD_CHUNK_BYTES = 8192


class SdkDropboxGateway:
    """Live provider adapter; synchronous SDK calls run off the event loop."""

    mode: Literal["mock", "live"] = "live"

    def __init__(self, client_for_actor: Callable[[str], Any]) -> None:
        """Inject an authorized SDK client factory with finite timeout and retry limits.

        The host must resolve the actor's encrypted credentials and return a client
        configured with a request timeout. Tests inject SDK-shaped synthetic fakes.
        """
        self._client_for_actor = client_for_actor

    async def _call(self, operation: Callable[[], Result]) -> Result:
        """Run provider I/O; redact provider errors before crossing the app boundary."""
        from dropbox.exceptions import AuthError, DropboxException
        from requests.exceptions import RequestException

        try:
            return await asyncio.to_thread(operation)
        except AuthError:
            raise FeatureError(
                "dropbox_authorization_required", "Reconnect the Dropbox account.", 409
            ) from None
        except (DropboxException, RequestException, TimeoutError, OSError):
            raise FeatureError(
                "dropbox_unavailable", "Dropbox could not complete the request.", 502
            ) from None

    async def verify_folder(self, actor_id: str, folder_path: str) -> None:
        """Require a real folder in this actor's account; raise a safe typed error."""
        from dropbox.files import FolderMetadata

        def operation() -> None:
            metadata = self._client_for_actor(actor_id).files_get_metadata(folder_path)
            if not isinstance(metadata, FolderMetadata):
                raise FeatureError(
                    "invalid_folder", "The selected path is not a Dropbox folder.", 400
                )

        await self._call(operation)

    async def list_files(
        self, actor_id: str, folder_path: str, cursor: str | None
    ) -> FilePage:
        """List a bounded provider page; restrict files to supported derived-text formats."""
        from dropbox.files import FileMetadata

        def operation() -> FilePage:
            client = self._client_for_actor(actor_id)
            page = (
                client.files_list_folder_continue(cursor)
                if cursor
                else client.files_list_folder(folder_path, recursive=False, limit=100)
            )
            files = [
                FileEntry(
                    file_path=entry.path_lower,
                    size_bytes=entry.size,
                    revision=entry.rev,
                )
                for entry in page.entries[:100]
                if isinstance(entry, FileMetadata)
                and entry.path_lower
                and entry.size <= MAX_MATERIAL_BYTES
                and PurePosixPath(entry.path_lower).suffix.lower() in {".txt", ".md"}
            ]
            return FilePage(files=files, next_cursor=page.cursor if page.has_more else None)

        return await self._call(operation)

    async def read_text(self, actor_id: str, file_path: str) -> Material:
        """Check size first, pin a revision, stream with a byte limit and close the response."""
        from dropbox.files import FileMetadata

        def operation() -> Material:
            client = self._client_for_actor(actor_id)
            metadata = client.files_get_metadata(file_path)
            if not isinstance(metadata, FileMetadata):
                raise FeatureError("invalid_material", "Select a text file.", 415)
            if metadata.size > MAX_MATERIAL_BYTES:
                raise FeatureError(
                    "material_too_large",
                    "Selected material exceeds the size limit.",
                    413,
                )
            downloaded, response = client.files_download(f"rev:{metadata.rev}")
            with closing(response):
                content = bytearray()
                for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
                    content.extend(chunk)
                    if len(content) > MAX_MATERIAL_BYTES:
                        raise FeatureError(
                            "material_too_large",
                            "Selected material exceeds the size limit.",
                            413,
                        )
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                raise FeatureError(
                    "unsupported_material", "Selected material must be UTF-8 text.", 415
                ) from None
            if any(ord(char) < 32 and char not in "\n\r\t" for char in text):
                raise FeatureError(
                    "unsupported_material", "Binary material is not supported.", 415
                )
            return Material(
                file_path=downloaded.path_lower or file_path,
                revision=downloaded.rev,
                text=text,
            )

        return await self._call(operation)

    async def write_text(self, actor_id: str, file_path: str, text: str) -> str:
        """Create a Markdown file with strict conflict handling; never overwrite a file."""
        from dropbox.files import WriteMode

        def operation() -> str:
            result = self._client_for_actor(actor_id).files_upload(
                text.encode("utf-8"),
                file_path,
                mode=WriteMode.add,
                autorename=False,
                strict_conflict=True,
                mute=True,
            )
            return str(result.rev)

        return await self._call(operation)
