"""Compatibility shim during the refactor — the local extractor is integrations/ocr/local_extractor.py. Removed in its last step."""

from integrations.ocr.local_extractor import *  # noqa: F401,F403
from integrations.ocr.local_extractor import drop_irrelevant_numbers, normalize_date  # noqa: F401
