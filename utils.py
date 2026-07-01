"""Shared utility helpers."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path


class ZipProcessingMode(Enum):
    """How ZIP and TAR archives should be processed."""

    ZIP_ONLY = "zip_only"
    ZIP_AND_CONTENTS = "zip_and_contents"


ZIP_EXTENSIONS = {".zip"}

TAR_EXTENSIONS = (
    ".tar",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tbz2",
    ".tar.xz",
    ".txz",
)


def is_zip_file(path: Path) -> bool:
    """Return True if the path appears to be a ZIP archive."""
    return path.suffix.lower() in ZIP_EXTENSIONS and path.is_file()


def is_tar_file(path: Path) -> bool:
    """Return True if the path appears to be a TAR archive."""
    if not path.is_file():
        return False
    name_lower = path.name.lower()
    return any(name_lower.endswith(ext) for ext in TAR_EXTENSIONS)


def is_archive_file(path: Path) -> bool:
    """Return True if the path is a supported ZIP or TAR archive."""
    return is_zip_file(path) or is_tar_file(path)


def unique_excel_path(directory: Path, base_name: str = "SHA256_Checksums") -> Path:
    """Return a non-conflicting Excel output path in the given directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = directory / f"{base_name}_{timestamp}.xlsx"
    if not candidate.exists():
        return candidate

    counter = 1
    while True:
        candidate = directory / f"{base_name}_{timestamp}_{counter}.xlsx"
        if not candidate.exists():
            return candidate
        counter += 1


def txt_output_path(source_file: Path) -> Path:
    """Return the TXT output path for a single uploaded file."""
    return source_file.with_suffix(".txt")


def excel_output_path(source_file: Path) -> Path:
    """Return the Excel output path matching a source file's base name."""
    return source_file.with_suffix(".xlsx")


def normalize_dropped_paths(raw: str) -> list[Path]:
    """Parse drag-and-drop path strings into file paths (no folders)."""
    paths: list[Path] = []
    if not raw:
        return paths

    current: list[str] = []
    in_braces = False
    for char in raw:
        if char == "{":
            in_braces = True
            current = []
        elif char == "}":
            in_braces = False
            segment = "".join(current).strip()
            if segment:
                paths.append(Path(segment))
            current = []
        elif char in (" ", "\n", "\t") and not in_braces:
            segment = "".join(current).strip()
            if segment:
                paths.append(Path(segment))
            current = []
        else:
            current.append(char)

    segment = "".join(current).strip()
    if segment:
        paths.append(Path(segment))

    files: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved.is_file():
            files.append(resolved)
    return files
