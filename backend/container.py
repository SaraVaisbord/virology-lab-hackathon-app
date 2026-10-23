"""Composition root: builds the application's components from the configuration and wires them together.
Nothing else creates integrations or services — they receive what they need."""

from __future__ import annotations

from types import ModuleType

from integrations.llm.base import LlmProvider
from integrations.llm.claude import ClaudeProvider, ClaudeSettings
from integrations.llm.gemini import GeminiProvider, GeminiSettings
from integrations.llm.openai import OpenAIProvider, OpenAISettings
from integrations.llm.page_image import PageImageSettings
from integrations.llm.prompt import ExtractionPrompt
from integrations.llm.router import LlmRouter


def build_llm_providers(cfg: ModuleType) -> dict[str, LlmProvider]:
    prompt = ExtractionPrompt(cfg.EXTRACTION_PROMPT_FILE)
    image = PageImageSettings(max_side_px=cfg.GEMINI_IMAGE_MAX_SIDE_PX, jpeg_quality=cfg.GEMINI_IMAGE_JPEG_QUALITY)
    verify_tls = not cfg.GEMINI_INSECURE_SSL
    return {
        "gemini": GeminiProvider(GeminiSettings(
            api_keys=cfg.GEMINI_API_KEYS, models=cfg.GEMINI_MODELS, timeout_seconds=cfg.GEMINI_TIMEOUT_SECONDS,
            max_attempts=cfg.GEMINI_MAX_ATTEMPTS, quota_default_backoff_seconds=cfg.GEMINI_QUOTA_DEFAULT_BACKOFF_SECONDS,
            busy_cooldown_seconds=cfg.GEMINI_BUSY_COOLDOWN_SECONDS, invalid_key_cooldown_seconds=cfg.GEMINI_INVALID_KEY_COOLDOWN_SECONDS,
        ), prompt, image, verify_tls),
        "claude": ClaudeProvider(ClaudeSettings(
            api_keys=cfg.ANTHROPIC_API_KEYS, model=cfg.CLAUDE_MODEL, effort=cfg.CLAUDE_EFFORT, max_tokens=cfg.CLAUDE_MAX_TOKENS,
            timeout_seconds=cfg.CLAUDE_TIMEOUT_SECONDS, quota_default_backoff_seconds=cfg.CLAUDE_QUOTA_DEFAULT_BACKOFF_SECONDS,
            busy_cooldown_seconds=cfg.CLAUDE_BUSY_COOLDOWN_SECONDS, invalid_key_cooldown_seconds=cfg.CLAUDE_INVALID_KEY_COOLDOWN_SECONDS,
        ), prompt, image, verify_tls),
        "openai": OpenAIProvider(OpenAISettings(
            api_key=cfg.OPENAI_API_KEY, model=cfg.OPENAI_MODEL, api_url=cfg.OPENAI_API_URL, timeout_seconds=cfg.OPENAI_TIMEOUT_SECONDS,
        ), prompt, image, verify_tls),
    }


def build_llm_router(cfg: ModuleType, providers: dict[str, LlmProvider] | None = None) -> LlmRouter:
    return LlmRouter(providers or build_llm_providers(cfg), cfg.LLM_PROVIDERS)
