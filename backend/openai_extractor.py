"""Compatibility shim during the refactor — the OpenAI provider is integrations/llm/openai.py. Removed in its last step."""

from __future__ import annotations

from ai_extractor import providers


def extract_from_image(image_path, known_senders=None, model=None):
    return providers()["openai"].extract_from_image(image_path, known_senders, model=model)
