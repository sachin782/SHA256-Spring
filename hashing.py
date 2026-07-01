"""SHA256 hashing with streaming reads."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO, Callable, Optional

CHUNK_SIZE = 1024 * 1024  # 1 MB


def hash_stream(
    stream: BinaryIO,
    chunk_size: int = CHUNK_SIZE,
    on_chunk: Optional[Callable[[int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> str:
    """Compute SHA256 from a readable binary stream.

    Args:
        stream: Binary input stream.
        chunk_size: Read size in bytes.
        on_chunk: Optional callback invoked with bytes read per chunk.
        cancel_check: Optional callback; raises CancellationError if True.

    Returns:
        Uppercase hexadecimal SHA256 digest.
    """
    hasher = hashlib.sha256()
    while True:
        if cancel_check and cancel_check():
            raise CancellationError("Hashing cancelled by user.")
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        hasher.update(chunk)
        if on_chunk:
            on_chunk(len(chunk))
    return hasher.hexdigest().upper()


def hash_file(
    path: Path,
    chunk_size: int = CHUNK_SIZE,
    on_chunk: Optional[Callable[[int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> str:
    """Compute SHA256 for a file on disk using chunked reads.

    Args:
        path: Path to the file.
        chunk_size: Read size in bytes.
        on_chunk: Optional callback invoked with bytes read per chunk.
        cancel_check: Optional callback; raises CancellationError if True.

    Returns:
        Uppercase hexadecimal SHA256 digest.
    """
    with path.open("rb") as handle:
        return hash_stream(handle, chunk_size, on_chunk, cancel_check)


class CancellationError(Exception):
    """Raised when hashing is cancelled."""
