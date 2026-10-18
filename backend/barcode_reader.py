"""
barcode_reader.py - Local barcode detection from images and PDF forms.
No data is sent to external services. No sensitive data is logged.
"""

import sys
import json
from pathlib import Path
from PIL import Image
from pyzbar.pyzbar import decode
import fitz  # pymupdf

SUPPORTED_FORMATS = {".png", ".jpg", ".jpeg", ".pdf"}


def pdf_to_images(path: Path) -> list:
    """Convert each PDF page to a PIL Image (in memory, no temp files)."""
    doc = fitz.open(str(path))
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    doc.close()
    return images


def load_images(image_path: str) -> list:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {image_path}")
    if path.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format '{path.suffix}'. Supported: {SUPPORTED_FORMATS}")
    if path.suffix.lower() == ".pdf":
        return pdf_to_images(path)
    try:
        return [Image.open(path).convert("RGB")]
    except Exception:
        raise ValueError(f"Cannot read image file: {image_path}")


def scan_page(image: Image.Image, page_num: int) -> list:
    results = []
    for bc in decode(image):
        rect = bc.rect
        results.append({
            "page": page_num,
            "data": bc.data.decode("utf-8", errors="replace"),
            "type": bc.type,
            "x": rect.left,
            "y": rect.top,
            "width": rect.width,
            "height": rect.height,
        })
    return results


def scan_file(file_path: str) -> dict:
    images = load_images(file_path)
    barcodes = []
    for i, img in enumerate(images, 1):
        barcodes.extend(scan_page(img, i))

    return {
        "file": file_path,
        "pages": len(images),
        "found": len(barcodes),
        "barcodes": barcodes,
        "message": f"Found {len(barcodes)} barcode(s)." if barcodes else "No barcodes found.",
    }


def main():
    if len(sys.argv) != 2:
        print("Usage: python barcode_reader.py path/to/file.pdf")
        sys.exit(1)

    try:
        result = scan_file(sys.argv[1])
    except (FileNotFoundError, ValueError) as e:
        result = {"error": str(e)}
        print(f"Error: {e}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(1)

    print(result["message"])
    for i, bc in enumerate(result["barcodes"], 1):
        print(f"  [{i}] page={bc['page']}  type={bc['type']}  data={bc['data']}  "
              f"pos=({bc['x']},{bc['y']})  size={bc['width']}x{bc['height']}")

    print("\n--- JSON ---")
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
