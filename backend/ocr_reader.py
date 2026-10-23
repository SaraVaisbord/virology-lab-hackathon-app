"""Compatibility shim during the refactor — OCR is integrations/ocr (TesseractEngine). Removed in its last step."""

from __future__ import annotations

from functools import cache

import config
from integrations.ocr.base import OcrUnavailableError, OcrWord  # noqa: F401
from integrations.ocr.tesseract import TesseractEngine


@cache
def default_engine() -> TesseractEngine:
    return TesseractEngine(config.TESSERACT_CMD, config.OCR_TESSDATA_DIR, config.OCR_LANGUAGES, config.OCR_TIMEOUT_SECONDS)


def is_available() -> bool:
    return default_engine().is_available()


def detect_rotation(image):
    return default_engine().detect_rotation(image)


def read_words(image, psm=11, languages=None, extra_config=None):
    return default_engine().read_words(image, psm=psm, languages=languages, extra_config=extra_config)
