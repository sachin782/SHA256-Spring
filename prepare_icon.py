"""Convert icon.png into a multi-size Windows .ico file."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

PROJECT_DIR = Path(__file__).resolve().parent
PNG_PATH = PROJECT_DIR / "icon.png"
ICO_PATH = PROJECT_DIR / "icon.ico"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> None:
    if not PNG_PATH.exists():
        raise FileNotFoundError(f"Missing application icon: {PNG_PATH}")

    image = Image.open(PNG_PATH).convert("RGBA")
    image.save(ICO_PATH, format="ICO", sizes=[(size, size) for size in ICO_SIZES])
    print(f"Created {ICO_PATH}")


if __name__ == "__main__":
    main()
