"""Compatibility shim during the refactor — the Gemini provider is integrations/llm/gemini.py. Removed in its last step."""

from __future__ import annotations

from functools import cache

import config
from integrations.llm.errors import ExtractionError, MissingApiKeyError, ModelsUnavailableError

__all__ = ["ExtractionError", "MissingApiKeyError", "ModelsUnavailableError", "extract_from_image", "providers"]


@cache
def providers():
    from container import build_llm_providers

    return build_llm_providers(config)


def extract_from_image(image_path, known_senders=None):
    return providers()["gemini"].extract_from_image(image_path, known_senders)
