"""Compatibility shim during the refactor — failover is integrations/llm/router.py. Removed in its last step.

The provider modules are looked up at call time, so tests that replace a module's extract_from_image still work."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import config
from integrations.llm.router import LlmRouter

PROVIDER_MODULES = {"gemini": "ai_extractor", "claude": "claude_extractor", "openai": "openai_extractor"}


class _ModuleProvider:
    def __init__(self, name: str) -> None:
        self.name = name

    def extract_from_image(self, image_path, known_senders=None):
        return importlib.import_module(PROVIDER_MODULES[self.name]).extract_from_image(image_path, known_senders)


def extract_from_image(image_path: str | Path, known_senders: list[str], providers: list[str] | None = None) -> dict[str, Any]:
    router = LlmRouter({name: _ModuleProvider(name) for name in PROVIDER_MODULES}, config.LLM_PROVIDERS)
    return router.extract_from_image(image_path, known_senders, providers=providers)
