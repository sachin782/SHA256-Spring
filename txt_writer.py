"""TXT report writer for single-file output."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from models import ChecksumRecord


def write_txt_report(
    records: Sequence[ChecksumRecord],
    output_path: Path,
    archive_with_contents: bool = False,
    *,
    zip_with_contents: bool | None = None,
) -> None:
    """Write a TXT checksum report for a single uploaded file.

    Args:
        records: Checksum rows to include.
        output_path: Destination TXT path.
        archive_with_contents: Use archive Option 2 formatting when True.
        zip_with_contents: Deprecated alias for archive_with_contents.
    """
    if zip_with_contents is not None:
        archive_with_contents = zip_with_contents

    lines: list[str] = []

    if archive_with_contents and len(records) > 1:
        archive_record = records[0]
        lines.extend(
            [
                "Archive File:",
                archive_record.file_name,
                "SHA256:",
                _sha256_or_error(archive_record),
                "",
            ]
        )
        for record in records[1:]:
            lines.extend(
                [
                    "--------------------------------",
                    "",
                    record.internal_path or record.file_name,
                    "SHA256:",
                    _sha256_or_error(record),
                    "",
                ]
            )
    else:
        record = records[0]
        lines.extend(
            [
                "Filename:",
                record.file_name,
                "",
                "SHA256:",
                _sha256_or_error(record),
            ]
        )

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _sha256_or_error(record: ChecksumRecord) -> str:
    if record.success:
        return record.sha256
    return f"ERROR: {record.error_message}"
