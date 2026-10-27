import os
import re
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from app.database import PlatformError


class DocumentStorage(Protocol):
    def write(self, key: str, content: bytes) -> None: ...
    def read(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


def new_storage_key() -> str:
    return uuid4().hex


class LocalDocumentStorage:
    """Private runtime directory, never a user-controlled path or a static mount."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def path(self, key):
        if not re.fullmatch(r"[a-f0-9]{32}", key):
            raise PlatformError("storage_unavailable", "Document storage is unavailable.")
        path = self.root / key
        # Reject symlinks (including Windows junction escapes) even for generated names.
        if path.is_symlink() or path.resolve().parent != self.root:
            raise PlatformError("storage_unavailable", "Document storage is unavailable.")
        return path

    def write(self, key, content):
        path = self.path(key)
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as file:
                try:
                    file.write(content)
                    file.flush()
                    os.fsync(file.fileno())
                except BaseException:
                    file.close()
                    path.unlink(missing_ok=True)
                    raise
        except OSError:
            raise PlatformError("storage_unavailable", "Could not store this document.") from None

    def read(self, key):
        try:
            return self.path(key).read_bytes()
        except FileNotFoundError:
            raise PlatformError(
                "document_not_found", "Document file is unavailable.", 404
            ) from None
        except OSError:
            raise PlatformError("storage_unavailable", "Could not read this document.") from None

    def delete(self, key):
        try:
            self.path(key).unlink(missing_ok=True)
        except OSError:
            raise PlatformError(
                "storage_unavailable", "Deletion is pending. Try deleting again."
            ) from None
