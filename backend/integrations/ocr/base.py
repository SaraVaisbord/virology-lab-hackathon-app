from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


class OcrUnavailableError(RuntimeError):
    """The OCR engine or its language data is not installed / configured."""


@dataclass(frozen=True)
class OcrWord:
    text: str
    confidence: float  # 0..100 as reported by the engine
    x: float  # box normalized to the image (0..1)
    y: float
    width: float
    height: float
    line_key: tuple[int, int, int]  # (block, paragraph, line) — words on the same printed line share it


class OcrEngine(Protocol):
    def is_available(self) -> bool: ...

    def read_words(self, image: np.ndarray, psm: int = 11, languages: str | None = None,
                   extra_config: list[str] | None = None) -> list[OcrWord]:
        """OCR an image (grey or BGR numpy array); psm = page segmentation mode (11 = sparse text)."""
        ...

    def detect_rotation(self, image: np.ndarray) -> tuple[int, float]:
        """Clockwise rotation (0/90/180/270) that makes the page upright, and the confidence in it."""
        ...
