"""Checksum processing orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from excel_writer import write_excel_report, write_excel_report_tabbed
from hashing import CancellationError, hash_file
from models import ChecksumRecord, ProcessingResult
from tar_handler import classify_tar_error, hash_tar_entry, list_tar_file_entries
from txt_writer import write_txt_report
from utils import (
    ZipProcessingMode,
    excel_output_path,
    is_archive_file,
    is_tar_file,
    is_zip_file,
    txt_output_path,
    unique_excel_path,
)
from zip_handler import classify_zip_error, hash_zip_entry, list_zip_file_entries

logger = logging.getLogger("sha256_generator")


@dataclass(frozen=True)
class _ArchiveEntry:
    internal_path: str
    display_path: str


def export_single_archive_txt(source: Path, records: list[ChecksumRecord]) -> Path:
    """Write a TXT checksum report for a single archive and its contents."""
    output = txt_output_path(source)
    write_txt_report(records, output, archive_with_contents=True)
    logger.info("Wrote TXT report: %s", output)
    return output


def export_single_archive_excel(source: Path, records: list[ChecksumRecord]) -> Path:
    """Write an Excel checksum report for a single archive and its contents."""
    output = excel_output_path(source)
    write_excel_report(records, output)
    logger.info("Wrote Excel report: %s", output)
    return output


# Backward-compatible aliases for ZIP-specific export helpers.
export_single_zip_txt = export_single_archive_txt
export_single_zip_excel = export_single_archive_excel


class ChecksumProcessor:
    """Coordinates hashing, archive handling, and report generation."""

    def __init__(
        self,
        files: list[Path],
        zip_mode: ZipProcessingMode,
        cancel_check: Callable[[], bool],
        on_progress: Callable[[int, int, str], None],
    ) -> None:
        self.files = files
        self.zip_mode = zip_mode
        self.cancel_check = cancel_check
        self.on_progress = on_progress
        self.records: list[ChecksumRecord] = []
        self.archive_groups: dict[str, list[ChecksumRecord]] = {}
        self.other_records: list[ChecksumRecord] = []
        self.output_path: Optional[Path] = None

    def run(self) -> ProcessingResult:
        """Process all files and write or prepare the appropriate report."""
        total_steps = self._count_steps() + 1  # +1 for writing output
        current_step = 0

        for file_path in self.files:
            if self.cancel_check():
                raise CancellationError("Processing cancelled by user.")

            if self._should_process_with_contents(file_path):
                current_step = self._process_archive_with_contents(
                    file_path, current_step, total_steps
                )
            else:
                current_step = self._process_regular_file(file_path, current_step, total_steps)

        if self._needs_single_archive_export_choice():
            self.on_progress(
                total_steps - 1,
                total_steps,
                "Checksums ready — choose export format...",
            )
            logger.info(
                "Single archive with contents hashed; awaiting export format choice for %s",
                self.files[0],
            )
            return ProcessingResult(
                records=self.records,
                single_archive_source=self.files[0],
            )

        self.on_progress(current_step, total_steps, "Writing output...")
        self.output_path = self._write_output()
        self.on_progress(total_steps, total_steps, "Completed")
        logger.info("Processing completed. Output: %s", self.output_path)
        return ProcessingResult(output_path=self.output_path, records=self.records)

    def _should_process_with_contents(self, file_path: Path) -> bool:
        return (
            is_archive_file(file_path)
            and self.zip_mode == ZipProcessingMode.ZIP_AND_CONTENTS
        )

    def _needs_single_archive_export_choice(self) -> bool:
        return len(self.files) == 1 and self._should_process_with_contents(self.files[0])

    def _count_steps(self) -> int:
        count = 0
        for file_path in self.files:
            if self._should_process_with_contents(file_path):
                count += 1
                try:
                    count += len(self._list_archive_entries(file_path))
                except Exception:
                    count += 0
            else:
                count += 1
        return count

    def _list_archive_entries(self, file_path: Path) -> Sequence[_ArchiveEntry]:
        if is_zip_file(file_path):
            return [
                _ArchiveEntry(entry.internal_path, entry.display_path)
                for entry in list_zip_file_entries(file_path)
            ]
        return [
            _ArchiveEntry(entry.internal_path, entry.display_path)
            for entry in list_tar_file_entries(file_path)
        ]

    def _hash_archive_entry(self, file_path: Path, internal_path: str) -> str:
        if is_zip_file(file_path):
            return hash_zip_entry(
                file_path,
                internal_path,
                cancel_check=self.cancel_check,
            )
        return hash_tar_entry(
            file_path,
            internal_path,
            cancel_check=self.cancel_check,
        )

    def _classify_archive_error(self, file_path: Path, exc: Exception) -> str:
        if is_zip_file(file_path):
            return classify_zip_error(exc)
        if is_tar_file(file_path):
            return classify_tar_error(exc)
        return str(exc)

    def _process_regular_file(self, file_path: Path, step: int, total: int) -> int:
        step += 1
        self.on_progress(step, total, f"Hashing {file_path.name}...")
        record = self._hash_path(file_path, str(file_path), file_path.name)
        self._add_record(record)
        return step

    def _process_archive_with_contents(self, file_path: Path, step: int, total: int) -> int:
        step += 1
        self.on_progress(step, total, f"Hashing {file_path.name}...")
        group: list[ChecksumRecord] = []
        archive_record = self._hash_path(file_path, str(file_path), file_path.name)
        group.append(archive_record)

        try:
            entries = self._list_archive_entries(file_path)
        except Exception as exc:
            message = self._classify_archive_error(file_path, exc)
            logger.error("Failed to read archive contents for %s: %s", file_path, message)
            group.append(
                ChecksumRecord(
                    file_name=f"{file_path.name} (contents)",
                    file_path=str(file_path),
                    sha256="",
                    success=False,
                    error_message=message,
                )
            )
            self._add_archive_group(file_path.name, group)
            return step

        for entry in entries:
            if self.cancel_check():
                raise CancellationError("Processing cancelled by user.")
            step += 1
            self.on_progress(step, total, f"Hashing {entry.display_path}...")
            try:
                digest = self._hash_archive_entry(file_path, entry.internal_path)
                group.append(
                    ChecksumRecord(
                        file_name=entry.display_path,
                        file_path=entry.display_path,
                        sha256=digest,
                        internal_path=entry.internal_path,
                    )
                )
            except Exception as exc:
                message = self._classify_archive_error(file_path, exc)
                logger.error("Failed to hash %s: %s", entry.display_path, message)
                group.append(
                    ChecksumRecord(
                        file_name=entry.display_path,
                        file_path=entry.display_path,
                        sha256="",
                        success=False,
                        error_message=message,
                        internal_path=entry.internal_path,
                    )
                )
        self._add_archive_group(file_path.name, group)
        return step

    def _add_record(self, record: ChecksumRecord) -> None:
        self.records.append(record)
        self.other_records.append(record)

    def _add_archive_group(self, archive_name: str, group: list[ChecksumRecord]) -> None:
        self.archive_groups[archive_name] = group
        self.records.extend(group)

    def _hash_path(self, path: Path | str, display_path: str, display_name: str) -> ChecksumRecord:
        file_path = Path(path)
        try:
            digest = hash_file(file_path, cancel_check=self.cancel_check)
            logger.info("Hashed %s successfully", display_path)
            return ChecksumRecord(
                file_name=display_name,
                file_path=display_path,
                sha256=digest,
            )
        except CancellationError:
            raise
        except Exception as exc:
            message = self._classify_archive_error(file_path, exc)
            logger.error("Failed to hash %s: %s", display_path, message)
            return ChecksumRecord(
                file_name=display_name,
                file_path=display_path,
                sha256="",
                success=False,
                error_message=message,
            )

    def _write_output(self) -> Path:
        if len(self.files) == 1:
            source = self.files[0]
            output = txt_output_path(source)
            try:
                write_txt_report(self.records, output, archive_with_contents=False)
                logger.info("Wrote TXT report: %s", output)
                return output
            except OSError as exc:
                logger.error("Failed to write TXT report: %s", exc)
                raise

        directory = self.files[0].parent
        output = unique_excel_path(directory)
        archive_files = [file_path for file_path in self.files if is_archive_file(file_path)]
        use_tabbed_archive_sheets = (
            self.zip_mode == ZipProcessingMode.ZIP_AND_CONTENTS and len(archive_files) >= 2
        )
        try:
            if use_tabbed_archive_sheets:
                write_excel_report_tabbed(self.archive_groups, self.other_records, output)
                logger.info(
                    "Wrote tabbed Excel report (%s archive sheets): %s",
                    len(self.archive_groups),
                    output,
                )
            else:
                write_excel_report(self.records, output)
                logger.info("Wrote Excel report: %s", output)
            return output
        except OSError as exc:
            logger.error("Failed to write Excel report: %s", exc)
            raise
