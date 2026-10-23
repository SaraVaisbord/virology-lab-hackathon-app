"""Local barcode detection with zbar (no data leaves the machine).

Library use: scan_pil_image(image) / scan_image(path) -> barcodes with coordinates normalized to the image (0..1).
CLI use:     python -m integrations.imaging.barcode path/to/file.(pdf|png|jpg)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pymupdf
from PIL import Image
from pyzbar.pyzbar import decode

SUPPORTED_FORMATS = {".png", ".jpg", ".jpeg", ".pdf"}


def scan_pil_image(image: Image.Image) -> list[dict]:
    width, height = image.size
    results = []
    for barcode in decode(image):
        rect = barcode.rect
        results.append({
            "data": barcode.data.decode("utf-8", errors="replace").strip(),
            "type": barcode.type,
            "x": rect.left / width,
            "y": rect.top / height,
            "width": rect.width / width,
            "height": rect.height / height,
        })
    return results


def scan_image(image_path: str | Path) -> list[dict]:
    with Image.open(image_path) as image:
        return scan_pil_image(image.convert("RGB"))


def _load_pages(path: Path, dpi: int) -> list[Image.Image]:
    if path.suffix.lower() == ".pdf":
        with pymupdf.open(str(path)) as doc:
            return [
                Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                for pix in (page.get_pixmap(dpi=dpi) for page in doc)
            ]
    return [Image.open(path).convert("RGB")]


def main() -> None:
    from config import load_settings

    if len(sys.argv) != 2:
        print("Usage: python -m integrations.imaging.barcode path/to/file.pdf")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists() or path.suffix.lower() not in SUPPORTED_FORMATS:
        print(f"Error: unsupported or missing file: {path}")
        sys.exit(1)

    result = [
        {"page": page_number, **barcode}
        for page_number, image in enumerate(_load_pages(path, load_settings().page_render_dpi), start=1)
        for barcode in scan_pil_image(image)
    ]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
