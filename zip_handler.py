"""ZIP archive detection and in-archive hashing."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from hashing import CancellationError, hash_stream
from utils import is_zip_file


@dataclass(frozen=True)
class ZipEntryInfo:
    """Metadata for a file entry inside a ZIP archive."""

    archive_path: Path
    internal_path: str
    display_path: str


def list_zip_file_entries(archive_path: Path) -> list[ZipEntryInfo]:
    """List non-directory file entries inside a ZIP archive."""
    entries: list[ZipEntryInfo] = []
    with zipfile.ZipFile(archive_path, "r") as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            internal = info.filename.replace("\\", "/")
            display = f"{archive_path.name}/{internal}"
            entries.append(
                ZipEntryInfo(
                    archive_path=archive_path,
                    internal_path=internal,
                    display_path=display,
                )
            )
    return entries


def hash_zip_entry(
    archive_path: Path,
    internal_path: str,
    on_chunk: Optional[Callable[[int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> str:
    """Hash a single file inside a ZIP without extracting to disk."""
    with zipfile.ZipFile(archive_path, "r") as archive:
        with archive.open(internal_path, "r") as stream:
            return hash_stream(stream, on_chunk=on_chunk, cancel_check=cancel_check)


def open_zip_for_hashing(archive_path: Path) -> zipfile.ZipFile:
    """Open a ZIP archive for reading, with helpful error context."""
    if not is_zip_file(archive_path):
        raise ValueError(f"Not a ZIP file: {archive_path}")
    return zipfile.ZipFile(archive_path, "r")


def classify_zip_error(exc: Exception) -> str:
    """Return a user-friendly message for ZIP-related failures."""
    if isinstance(exc, zipfile.BadZipFile):
        return f"Corrupted or invalid ZIP archive: {exc}"
    if isinstance(exc, RuntimeError) and "password" in str(exc).lower():
        return "Encrypted/password-protected ZIP cannot be processed without a password."
    if isinstance(exc, PermissionError):
        return f"Permission denied: {exc}"
    if isinstance(exc, CancellationError):
        raise exc
    return str(exc)
