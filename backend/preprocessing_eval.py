"""
preprocessing_eval.py - Measure what preprocessing buys, locally (no LLM calls, no tokens).

    python preprocessing_eval.py <folder with PDFs> [--reference-db path/to/app.db]

For every page it compares the OLD input (page re-rendered at 200 dpi and shrunk to 2000 px, no cleanup)
with the NEW one (native-resolution scan + preprocessing.py) on:
  barcodes    distinct values decoded by zbar
  words       OCR words with confidence >= MIN_CONFIDENCE
  numbers     OCR tokens of >= 4 digits
  labels      key form labels found (see LABEL_KEYWORDS)
  ref_found   reference values found among OCR numbers / barcodes (only with --reference-db)

--reference-db reads values an earlier LLM run extracted. That is NOT ground truth — it only shows how many of
those readings the local sources can independently see. Only counts are printed — never values (medical data).
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from PIL import Image

import barcode_reader
import ocr_reader
from db.constants import LOCAL_LABEL_LEXICON
from preprocessing import preprocess

MIN_CONFIDENCE = 60
# The label words the local extractor looks for (one source: the label lexicon).
LABEL_KEYWORDS = tuple(dict.fromkeys(word for spec in LOCAL_LABEL_LEXICON.values() for word in spec["keywords"]))
REFERENCE_FIELDS = ("central_number", "commitment_number", "id_number")
OLD_RENDER_DPI, OLD_MAX_SIDE = 200, 2000


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def load_old_page(pdf: Path) -> np.ndarray:
    """The pipeline before this change: re-render at 200 dpi, shrink to 2000 px."""
    with pymupdf.open(str(pdf)) as doc:
        pix = doc[0].get_pixmap(dpi=OLD_RENDER_DPI, alpha=False)
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    image.thumbnail((OLD_MAX_SIDE, OLD_MAX_SIDE))
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def load_native_page(pdf: Path) -> tuple[np.ndarray, float]:
    """The scan as stored inside the PDF (no re-rendering), with its real dpi."""
    with pymupdf.open(str(pdf)) as doc:
        page = doc[0]
        images = page.get_images(full=True)
        if len(images) == 1:
            info = doc.extract_image(images[0][0])
            bgr = cv2.imdecode(np.frombuffer(info["image"], np.uint8), cv2.IMREAD_COLOR)
            return bgr, info["width"] / (page.rect.width / 72)
        pix = page.get_pixmap(dpi=300, alpha=False)  # not a single-scan page: render
        return cv2.cvtColor(np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3), cv2.COLOR_RGB2BGR), 300.0


def decode_barcodes(images: list[np.ndarray]) -> set[str]:
    found: set[str] = set()
    for image in images:
        found |= {b["data"] for b in barcode_reader.scan_pil_image(Image.fromarray(image).convert("RGB"))}
    return found


def ocr_metrics(image: np.ndarray) -> dict:
    words = [w for w in ocr_reader.read_words(image) if w.confidence >= MIN_CONFIDENCE]
    numbers = {_digits(w.text) for w in words if len(_digits(w.text)) >= 4}
    labels = {k for w in words for k in LABEL_KEYWORDS if k in w.text}
    return {"words": len(words), "numbers": numbers, "labels": labels}


def load_reference(db_path: Path) -> dict[str, set[str]]:
    connection = sqlite3.connect(db_path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(forms)")}
    column = "llm_result" if "llm_result" in columns else "raw_llm_json"
    reference: dict[str, set[str]] = {}
    for name, raw in connection.execute(f"SELECT source_file, {column} FROM forms WHERE {column} IS NOT NULL"):
        data = json.loads(raw)
        llm = data.get("llm", data)
        reference[name] = {_digits(c["value"]) for f in REFERENCE_FIELDS for c in llm.get(f, []) if len(_digits(c.get("value", ""))) >= 4}
    return reference


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--reference-db", type=Path)
    args = parser.parse_args()
    reference = load_reference(args.reference_db) if args.reference_db else {}

    totals = {key: [0, 0] for key in ("barcodes", "words", "numbers", "labels", "ref_found")}
    ref_total = 0
    print(f"{'file':8s} | {'barcodes':>9s} | {'words':>9s} | {'numbers':>9s} | {'labels':>7s} | {'ref_found':>9s} | sec   (old → new)")
    for pdf in sorted(args.folder.glob("*.pdf")):
        started = time.time()
        old = load_old_page(pdf)
        native, dpi = load_native_page(pdf)
        views = preprocess(native, source_dpi=dpi)

        old_bc = decode_barcodes([cv2.cvtColor(old, cv2.COLOR_BGR2GRAY)])
        new_bc = decode_barcodes(views.barcode_views)
        old_ocr = ocr_metrics(cv2.cvtColor(old, cv2.COLOR_BGR2GRAY))
        new_ocr = ocr_metrics(views.print_binary)

        refs = reference.get(pdf.name, set())
        ref_total += len(refs)
        old_ref = len(refs & (old_ocr["numbers"] | {_digits(b) for b in old_bc}))
        new_ref = len(refs & (new_ocr["numbers"] | {_digits(b) for b in new_bc}))

        row = {
            "barcodes": (len(old_bc), len(new_bc)),
            "words": (old_ocr["words"], new_ocr["words"]),
            "numbers": (len(old_ocr["numbers"]), len(new_ocr["numbers"])),
            "labels": (len(old_ocr["labels"]), len(new_ocr["labels"])),
            "ref_found": (old_ref, new_ref),
        }
        for key, (o, n) in row.items():
            totals[key][0] += o
            totals[key][1] += n
        ref_cell = f"{old_ref}→{new_ref}/{len(refs)}" if refs else "-"
        print(f"{pdf.name:8s} | {row['barcodes'][0]:>4d}→{row['barcodes'][1]:<4d} | {row['words'][0]:>4d}→{row['words'][1]:<4d} | "
              f"{row['numbers'][0]:>4d}→{row['numbers'][1]:<4d} | {row['labels'][0]:>2d}→{row['labels'][1]:<3d} | {ref_cell:>9s} | {time.time() - started:4.1f}", flush=True)

    print("-" * 80)
    print("TOTAL    | " + " | ".join(f"{key} {o}→{n}" for key, (o, n) in totals.items()) + (f" (of {ref_total})" if ref_total else ""))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
