"""Tkinter GUI for the SHA256 Checksum Generator."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from hashing import CancellationError
from logger import setup_logging
from models import ProcessingResult
from processor import (
    ChecksumProcessor,
    export_single_archive_excel,
    export_single_archive_txt,
)
from utils import ZipProcessingMode, is_archive_file, normalize_dropped_paths

logger = logging.getLogger("sha256_generator")

ICON_FILENAME = "icon.png"


def _resource_path(filename: str) -> Path:
    """Return a path to a bundled or project-local resource file."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent
    return base / filename


def _set_window_icon(root: tk.Tk) -> None:
    """Set the window title-bar icon from icon.png."""
    icon_path = _resource_path(ICON_FILENAME)
    if not icon_path.is_file():
        logger.warning("Window icon not found: %s", icon_path)
        return

    try:
        icon = tk.PhotoImage(file=str(icon_path))
    except tk.TclError as exc:
        logger.warning("Could not load window icon from %s: %s", icon_path, exc)
        return

    root.iconphoto(True, icon)
    root._window_icon = icon  # type: ignore[attr-defined]


class SHA256GeneratorApp:
    """Main application window."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("SHA256 Checksum Generator")
        self.root.minsize(520, 560)
        self.root.geometry("640x680")

        self.selected_files: list[Path] = []
        self.archive_mode = tk.StringVar(value=ZipProcessingMode.ZIP_ONLY.value)
        self.auto_open = tk.BooleanVar(value=False)
        self.status_text = tk.StringVar(value="Ready")
        self.file_count_text = tk.StringVar(value="0 files selected")
        self.progress_text = tk.StringVar(value="")

        self._cancel_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._processing = False
        self._last_output: Optional[Path] = None

        self._build_ui()
        self._setup_drag_drop()
        self._update_archive_options_state()

    def _build_ui(self) -> None:
        padding = {"padx": 16, "pady": 6}

        header = ttk.Label(
            self.root,
            text="SHA256 Checksum Generator",
            font=("Segoe UI", 16, "bold"),
        )
        header.pack(pady=(16, 8))

        upload_btn = ttk.Button(self.root, text="Upload Files", command=self._upload_files)
        upload_btn.pack(pady=4)

        count_label = ttk.Label(self.root, textvariable=self.file_count_text)
        count_label.pack(anchor="w", **padding)

        files_frame = ttk.LabelFrame(self.root, text="Selected Files", padding=8)
        files_frame.pack(fill="both", expand=True, **padding)

        self.files_listbox = tk.Listbox(files_frame, height=10, activestyle="none")
        self.files_listbox.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(files_frame, orient="vertical", command=self.files_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.files_listbox.config(yscrollcommand=scrollbar.set)

        list_buttons = ttk.Frame(self.root)
        list_buttons.pack(fill="x", **padding)
        ttk.Button(list_buttons, text="Remove Selected", command=self._remove_selected).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(list_buttons, text="Clear All", command=self._clear_files).pack(side="left")

        archive_frame = ttk.LabelFrame(self.root, text="ZIP/TAR File Processing", padding=10)
        archive_frame.pack(fill="x", **padding)

        self.archive_only_radio = ttk.Radiobutton(
            archive_frame,
            text="Hash ZIP/TAR file only",
            variable=self.archive_mode,
            value=ZipProcessingMode.ZIP_ONLY.value,
        )
        self.archive_and_contents_radio = ttk.Radiobutton(
            archive_frame,
            text="Hash ZIP/TAR file and every file inside it",
            variable=self.archive_mode,
            value=ZipProcessingMode.ZIP_AND_CONTENTS.value,
        )
        self.archive_only_radio.pack(anchor="w")
        self.archive_and_contents_radio.pack(anchor="w", pady=(4, 0))

        options_frame = ttk.Frame(self.root)
        options_frame.pack(fill="x", **padding)
        ttk.Checkbutton(
            options_frame,
            text="Open report automatically after generation",
            variable=self.auto_open,
        ).pack(anchor="w")

        action_frame = ttk.Frame(self.root)
        action_frame.pack(fill="x", **padding)

        self.generate_btn = ttk.Button(
            action_frame,
            text="Generate SHA256",
            command=self._start_generation,
        )
        self.generate_btn.pack(side="left")

        self.cancel_btn = ttk.Button(
            action_frame,
            text="Cancel",
            command=self._cancel_generation,
            state="disabled",
        )
        self.cancel_btn.pack(side="left", padx=(8, 0))

        ttk.Button(
            action_frame,
            text="Copy Last SHA256",
            command=self._copy_last_hash,
        ).pack(side="right")

        progress_frame = ttk.LabelFrame(self.root, text="Progress", padding=10)
        progress_frame.pack(fill="x", **padding)

        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate", maximum=100)
        self.progress_bar.pack(fill="x")

        ttk.Label(progress_frame, textvariable=self.progress_text).pack(anchor="w", pady=(6, 0))
        ttk.Label(progress_frame, text="Status:").pack(anchor="w", pady=(8, 0))
        ttk.Label(progress_frame, textvariable=self.status_text).pack(anchor="w")

        self._setup_context_menu()

    def _setup_context_menu(self) -> None:
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Copy filename", command=self._copy_selected_filename)
        self.context_menu.add_command(label="Remove", command=self._remove_selected)

        self.files_listbox.bind("<Button-3>", self._show_context_menu)

    def _show_context_menu(self, event: tk.Event) -> None:
        try:
            index = self.files_listbox.nearest(event.y)
            self.files_listbox.selection_clear(0, tk.END)
            self.files_listbox.selection_set(index)
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _setup_drag_drop(self) -> None:
        """Enable drag-and-drop on Windows when windnd is available."""
        try:
            import windnd  # type: ignore[import-untyped]

            def on_drop(files: list[bytes]) -> None:
                decoded = []
                for item in files:
                    text = item.decode("utf-8", errors="replace")
                    decoded.append(text)
                raw = " ".join(decoded)
                self._add_files(normalize_dropped_paths(raw))

            windnd.hook_dropfiles(self.root, func=on_drop)
            logger.info("Drag-and-drop enabled")
        except ImportError:
            logger.info("windnd not installed; drag-and-drop disabled")

    def _upload_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select files",
            filetypes=[("All files", "*.*")],
        )
        if paths:
            self._add_files([Path(p) for p in paths])

    def _add_files(self, paths: list[Path]) -> None:
        added = 0
        for path in paths:
            resolved = path.resolve()
            if not resolved.is_file():
                continue
            if resolved not in self.selected_files:
                self.selected_files.append(resolved)
                self.files_listbox.insert(tk.END, resolved.name)
                added += 1

        if added:
            logger.info("Added %s file(s): %s", added, [str(p) for p in self.selected_files])
        self._refresh_file_count()
        self._update_archive_options_state()

    def _remove_selected(self) -> None:
        selection = list(self.files_listbox.curselection())
        if not selection:
            return
        for index in reversed(selection):
            self.files_listbox.delete(index)
            del self.selected_files[index]
        self._refresh_file_count()
        self._update_archive_options_state()

    def _clear_files(self) -> None:
        self.selected_files.clear()
        self.files_listbox.delete(0, tk.END)
        self._refresh_file_count()
        self._update_archive_options_state()

    def _refresh_file_count(self) -> None:
        count = len(self.selected_files)
        label = "file" if count == 1 else "files"
        self.file_count_text.set(f"{count} {label} selected")

    def _update_archive_options_state(self) -> None:
        has_archive = any(is_archive_file(path) for path in self.selected_files)
        state = "normal" if has_archive else "disabled"
        self.archive_only_radio.configure(state=state)
        self.archive_and_contents_radio.configure(state=state)

    def _get_archive_mode(self) -> ZipProcessingMode:
        value = self.archive_mode.get()
        if value == ZipProcessingMode.ZIP_AND_CONTENTS.value:
            return ZipProcessingMode.ZIP_AND_CONTENTS
        return ZipProcessingMode.ZIP_ONLY

    def _set_processing_state(self, processing: bool) -> None:
        self._processing = processing
        self.generate_btn.configure(state="disabled" if processing else "normal")
        self.cancel_btn.configure(state="normal" if processing else "disabled")

    def _start_generation(self) -> None:
        if not self.selected_files:
            messagebox.showwarning("No files", "Please upload at least one file.")
            return
        if self._worker and self._worker.is_alive():
            return

        self._cancel_event.clear()
        self._set_processing_state(True)
        self.progress_bar["value"] = 0
        self.status_text.set("Processing...")
        self.progress_text.set("Starting...")

        files = list(self.selected_files)
        archive_mode = self._get_archive_mode()
        logger.info(
            "Starting generation for %s file(s), archive mode: %s",
            len(files),
            archive_mode.value,
        )

        self._worker = threading.Thread(
            target=self._run_processor,
            args=(files, archive_mode),
            daemon=True,
        )
        self._worker.start()

    def _run_processor(self, files: list[Path], archive_mode: ZipProcessingMode) -> None:
        try:
            processor = ChecksumProcessor(
                files=files,
                zip_mode=archive_mode,
                cancel_check=self._cancel_event.is_set,
                on_progress=self._on_progress_thread,
            )
            result = processor.run()
            self.root.after(0, lambda: self._on_complete(result, None))
        except CancellationError:
            self.root.after(
                0,
                lambda: self._on_complete(ProcessingResult(), "Cancelled"),
            )
        except Exception as exc:
            logger.exception("Unexpected processing error")
            self.root.after(0, lambda: self._on_complete(ProcessingResult(), str(exc)))

    def _on_progress_thread(self, current: int, total: int, message: str) -> None:
        self.root.after(0, lambda: self._update_progress(current, total, message))

    def _update_progress(self, current: int, total: int, message: str) -> None:
        if total > 0:
            percent = min(100, int((current / total) * 100))
            self.progress_bar["value"] = percent
        self.progress_text.set(f"Processing {current} of {total}... {message}")
        self.status_text.set(message)

    def _cancel_generation(self) -> None:
        if self._processing:
            self._cancel_event.set()
            self.status_text.set("Cancelling...")

    def _on_complete(
        self,
        result: ProcessingResult,
        error: Optional[str],
    ) -> None:
        self._set_processing_state(False)

        if error == "Cancelled":
            self.status_text.set("Cancelled")
            self.progress_text.set("")
            messagebox.showinfo("Cancelled", "Checksum generation was cancelled.")
            return

        if error:
            self.status_text.set("Failed")
            messagebox.showerror("Error", f"An error occurred:\n{error}")
            return

        records = result.records
        output_path = result.output_path

        if result.single_archive_source is not None:
            export_format = self._prompt_single_archive_export(result.single_archive_source)
            if export_format is None:
                self.status_text.set("Export cancelled")
                self.progress_text.set("Checksums computed but not exported.")
                return
            try:
                if export_format == "txt":
                    output_path = export_single_archive_txt(result.single_archive_source, records)
                else:
                    output_path = export_single_archive_excel(
                        result.single_archive_source, records
                    )
            except OSError as exc:
                self.status_text.set("Failed")
                messagebox.showerror("Export Error", f"Could not save report:\n{exc}")
                return

        success_count = sum(1 for record in records if record.success)
        fail_count = len(records) - success_count
        summary = f"Completed — {success_count} succeeded"
        if fail_count:
            summary += f", {fail_count} failed"
        self.status_text.set(summary)
        self.progress_bar["value"] = 100

        if output_path:
            self._last_output = output_path
            self.progress_text.set(f"Saved: {output_path}")
            if self.auto_open.get():
                self._open_file(output_path)

            messagebox.showinfo(
                "Complete",
                f"Checksum report saved to:\n{output_path}",
            )

    def _prompt_single_archive_export(self, archive_path: Path) -> Optional[str]:
        """Ask the user to export a single archive report as TXT or Excel."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Choose Export Format")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        choice: dict[str, Optional[str]] = {"value": None}

        frame = ttk.Frame(dialog, padding=20)
        frame.pack()

        ttk.Label(
            frame,
            text=f"SHA256 checksums are ready for:\n{archive_path.name}",
            justify="center",
        ).pack(pady=(0, 12))

        ttk.Label(
            frame,
            text="How would you like to export the results?",
        ).pack(pady=(0, 12))

        ttk.Button(
            frame,
            text="Export as TXT file",
            command=lambda: self._close_export_dialog(dialog, choice, "txt"),
            width=28,
        ).pack(pady=4)

        ttk.Button(
            frame,
            text="Export as Excel file",
            command=lambda: self._close_export_dialog(dialog, choice, "xlsx"),
            width=28,
        ).pack(pady=4)

        ttk.Button(
            frame,
            text="Cancel",
            command=dialog.destroy,
            width=28,
        ).pack(pady=(8, 0))

        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.update_idletasks()
        dialog.geometry(
            f"+{self.root.winfo_rootx() + 80}+{self.root.winfo_rooty() + 80}"
        )
        self.root.wait_window(dialog)
        return choice["value"]

    def _close_export_dialog(
        self,
        dialog: tk.Toplevel,
        choice: dict[str, Optional[str]],
        value: str,
    ) -> None:
        choice["value"] = value
        dialog.destroy()

    def _open_file(self, path: Path) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", str(path)], check=False)
            else:
                subprocess.run(["xdg-open", str(path)], check=False)
        except OSError as exc:
            logger.error("Failed to open %s: %s", path, exc)

    def _copy_last_hash(self) -> None:
        if not self._last_output or not self._last_output.exists():
            messagebox.showinfo("Copy", "Generate a report first.")
            return
        try:
            content = self._last_output.read_text(encoding="utf-8")
            for line in content.splitlines():
                stripped = line.strip()
                if len(stripped) == 64 and all(c in "0123456789ABCDEFabcdef" for c in stripped):
                    self.root.clipboard_clear()
                    self.root.clipboard_append(stripped.upper())
                    self.status_text.set("SHA256 copied to clipboard")
                    return
            messagebox.showinfo("Copy", "No SHA256 hash found in the last report.")
        except OSError as exc:
            messagebox.showerror("Copy", str(exc))

    def _copy_selected_filename(self) -> None:
        selection = self.files_listbox.curselection()
        if not selection:
            return
        name = self.files_listbox.get(selection[0])
        self.root.clipboard_clear()
        self.root.clipboard_append(name)
        self.status_text.set(f"Copied: {name}")


def create_app() -> tk.Tk:
    """Create and configure the main application window."""
    setup_logging()
    root = tk.Tk()
    _set_window_icon(root)

    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
    except tk.TclError:
        pass

    SHA256GeneratorApp(root)
    return root
