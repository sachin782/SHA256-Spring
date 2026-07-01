"""TAR archive detection and in-archive hashing."""

from __future__ import annotations

import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from hashing import CancellationError, hash_stream
from utils import is_tar_file


@dataclass(frozen=True)
class TarEntryInfo:
    """Metadata for a file entry inside a TAR archive."""

    archive_path: Path
    internal_path: str
    display_path: str


def list_tar_file_entries(archive_path: Path) -> list[TarEntryInfo]:
    """List non-directory file entries inside a TAR archive."""
    entries: list[TarEntryInfo] = []
    with tarfile.open(archive_path, "r:*") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            internal = member.name.replace("\\", "/")
            display = f"{archive_path.name}/{internal}"
            entries.append(
                TarEntryInfo(
                    archive_path=archive_path,
                    internal_path=internal,
                    display_path=display,
                )
            )
    return entries


def hash_tar_entry(
    archive_path: Path,
    internal_path: str,
    on_chunk: Optional[Callable[[int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> str:
    """Hash a single file inside a TAR without extracting to disk."""
    with tarfile.open(archive_path, "r:*") as archive:
        member = archive.getmember(internal_path)
        stream = archive.extractfile(member)
        if stream is None:
            raise ValueError(f"Cannot read entry from TAR archive: {internal_path}")
        with stream:
            return hash_stream(stream, on_chunk=on_chunk, cancel_check=cancel_check)


def open_tar_for_hashing(archive_path: Path) -> tarfile.TarFile:
    """Open a TAR archive for reading, with helpful error context."""
    if not is_tar_file(archive_path):
        raise ValueError(f"Not a TAR file: {archive_path}")
    return tarfile.open(archive_path, "r:*")


def classify_tar_error(exc: Exception) -> str:
    """Return a user-friendly message for TAR-related failures."""
    if isinstance(exc, tarfile.ReadError):
        return f"Corrupted or invalid TAR archive: {exc}"
    if isinstance(exc, tarfile.CompressionError):
        return f"Unsupported or corrupted TAR compression: {exc}"
    if isinstance(exc, PermissionError):
        return f"Permission denied: {exc}"
    if isinstance(exc, CancellationError):
        raise exc
    return str(exc)
