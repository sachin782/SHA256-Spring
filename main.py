"""Entry point for the SHA256 Checksum Generator."""

from __future__ import annotations

import tkinter as tk

from gui import create_app


def main() -> None:
    """Launch the SHA256 Checksum Generator desktop application."""
    root = create_app()
    root.mainloop()


if __name__ == "__main__":
    main()
