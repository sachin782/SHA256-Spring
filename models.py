"""Shared data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ChecksumRecord:
    """A single checksum result row."""

    file_name: str
    file_path: str
    sha256: str
    success: bool = True
    error_message: str = ""
    internal_path: str = ""


@dataclass
class ProcessingResult:
    """Outcome of a checksum processing run."""

    records: list[ChecksumRecord] = field(default_factory=list)
    output_path: Path | None = None
    single_archive_source: Path | None = None
