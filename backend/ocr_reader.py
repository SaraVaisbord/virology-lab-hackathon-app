"""
ocr_reader.py - Local OCR with Tesseract (no data leaves the machine).

read_words(image) -> words with text, confidence (0-100) and a box normalized to the image (0..1).
Tesseract is called as a process with TSV output because it reports per-word confidence; images go
through a temp file under the system temp dir (Tesseract on Windows can't open non-ASCII paths).
"""

from __future__ import annotations

import csv
import io
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass

import cv2
import numpy as np

import config


class OcrUnavailableError(RuntimeError):
    """Tesseract or its language data is not installed / configured."""


@dataclass(frozen=True)
class OcrWord:
    text: str
    confidence: float  # 0..100 as reported by Tesseract
    x: float
    y: float
    width: float
    height: float
    line_key: tuple[int, int, int]  # (block, paragraph, line) — words on the same printed line share it


def is_available() -> bool:
    return os.path.isfile(config.TESSERACT_CMD) and os.path.isdir(config.OCR_TESSDATA_DIR)


def _run_tesseract(image: np.ndarray, args: list[str]) -> str:
    if not is_available():
        raise OcrUnavailableError(f"Tesseract not found ({config.TESSERACT_CMD}) or no tessdata in {config.OCR_TESSDATA_DIR}")
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        cv2.imwrite(path, image)
        result = subprocess.run(
            [config.TESSERACT_CMD, path, "stdout", "--tessdata-dir", config.OCR_TESSDATA_DIR, *args],
            capture_output=True, timeout=config.OCR_TIMEOUT_SECONDS, check=False,
        )
    finally:
        os.unlink(path)
    if result.returncode != 0:
        raise RuntimeError(f"Tesseract failed with exit code {result.returncode}")
    return result.stdout.decode("utf-8", errors="replace")


def detect_rotation(image: np.ndarray) -> tuple[int, float]:
    """Clockwise rotation (0/90/180/270) that makes the page upright, and Tesseract's confidence in it.
    Uses the OSD model; returns (0, 0.0) when the page has too little text to decide."""
    try:
        output = _run_tesseract(image, ["--psm", "0"])
    except RuntimeError:  # OSD fails on pages with almost no text
        return 0, 0.0
    rotate = re.search(r"Rotate:\s*(\d+)", output)
    confidence = re.search(r"Orientation confidence:\s*([\d.]+)", output)
    return (int(rotate.group(1)) if rotate else 0), (float(confidence.group(1)) if confidence else 0.0)


def read_words(image: np.ndarray, psm: int = 11, languages: str | None = None, extra_config: list[str] | None = None) -> list[OcrWord]:
    """OCR an image (grey or BGR numpy array). psm 11 = sparse text, the best default for forms."""
    height, width = image.shape[:2]
    output = _run_tesseract(image, [
        "-l", languages or config.OCR_LANGUAGES,
        "--psm", str(psm),
        "-c", "preserve_interword_spaces=1",
        # Set directly (not the "tsv" config file, which lives in the install dir, not in OCR_TESSDATA_DIR).
        "-c", "tessedit_create_tsv=1",
        *(extra_config or []),
    ])

    words = []
    for row in csv.DictReader(io.StringIO(output), delimiter="\t", quoting=csv.QUOTE_NONE):
        text = (row.get("text") or "").strip()
        if row.get("level") != "5" or not text:
            continue
        words.append(OcrWord(
            text=text,
            confidence=float(row["conf"]),
            x=int(row["left"]) / width,
            y=int(row["top"]) / height,
            width=int(row["width"]) / width,
            height=int(row["height"]) / height,
            line_key=(int(row["block_num"]), int(row["par_num"]), int(row["line_num"])),
        ))
    return words
