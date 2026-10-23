"""Compatibility shim during the refactor — the Claude provider is integrations/llm/claude.py. Removed in its last step."""

from __future__ import annotations

from ai_extractor import providers


def extract_from_image(image_path, known_senders=None):
    return providers()["claude"].extract_from_image(image_path, known_senders)
