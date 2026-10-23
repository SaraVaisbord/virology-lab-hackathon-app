"""Local OCR with Tesseract (no data leaves the machine).

Tesseract is called as a process with TSV output because it reports per-word confidence; images go through a temp
file under the system temp dir (Tesseract on Windows can't open non-ASCII paths).
"""

from __future__ import annotations

import csv
import io
import os
import re
import subprocess
import tempfile

import cv2
import numpy as np

from integrations.ocr.base import OcrUnavailableError, OcrWord


class TesseractEngine:
    """cmd: the tesseract executable; tessdata_dir: heb + eng + osd .traineddata (an ASCII path on Windows);
    languages: the default OCR languages ("heb+eng")."""

    def __init__(self, cmd: str, tessdata_dir: str, languages: str, timeout_seconds: int) -> None:
        self._cmd = cmd
        self._tessdata_dir = tessdata_dir
        self._languages = languages
        self._timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        return os.path.isfile(self._cmd) and os.path.isdir(self._tessdata_dir)

    def _run(self, image: np.ndarray, args: list[str]) -> str:
        if not self.is_available():
            raise OcrUnavailableError(f"Tesseract not found ({self._cmd}) or no tessdata in {self._tessdata_dir}")
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            cv2.imwrite(path, image)
            result = subprocess.run(
                [self._cmd, path, "stdout", "--tessdata-dir", self._tessdata_dir, *args],
                capture_output=True, timeout=self._timeout_seconds, check=False,
            )
        finally:
            os.unlink(path)
        if result.returncode != 0:
            raise RuntimeError(f"Tesseract failed with exit code {result.returncode}")
        return result.stdout.decode("utf-8", errors="replace")

    def detect_rotation(self, image: np.ndarray) -> tuple[int, float]:
        """Uses the OSD model; returns (0, 0.0) when the page has too little text to decide."""
        try:
            output = self._run(image, ["--psm", "0"])
        except RuntimeError:  # OSD fails on pages with almost no text
            return 0, 0.0
        rotate = re.search(r"Rotate:\s*(\d+)", output)
        confidence = re.search(r"Orientation confidence:\s*([\d.]+)", output)
        return (int(rotate.group(1)) if rotate else 0), (float(confidence.group(1)) if confidence else 0.0)

    def read_words(self, image: np.ndarray, psm: int = 11, languages: str | None = None,
                   extra_config: list[str] | None = None) -> list[OcrWord]:
        """psm 11 = sparse text, the best default for forms."""
        height, width = image.shape[:2]
        output = self._run(image, [
            "-l", languages or self._languages,
            "--psm", str(psm),
            "-c", "preserve_interword_spaces=1",
            # Set directly (not the "tsv" config file, which lives in the install dir, not in the tessdata dir).
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
