"""Automatic failover between LLM providers (config.LLM_PROVIDERS, in order).

Every provider module has the same interface — extract_from_image(image_path, known_senders) -> dict in one shape —
and the same three ways to fail:
  MissingApiKeyError       not configured (or key rejected)      → skipped
  ModelsUnavailableError   out of quota / overloaded, resting    → the next provider takes the page
  ExtractionError          this page got no usable answer        → the next provider tries it
The answer records which provider gave it (`_provider`). When every configured provider is resting the page goes
back to the queue (ModelsUnavailableError, the queue pauses); when one of them failed on the page itself the form
fails — re-queueing it would only spend tokens again.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

import config
from ai_extractor import ExtractionError, MissingApiKeyError, ModelsUnavailableError

logger = logging.getLogger(__name__)

# Provider name → module with extract_from_image. Looked up at call time, so tests can monkeypatch the modules.
PROVIDER_MODULES = {"gemini": "ai_extractor", "claude": "claude_extractor", "openai": "openai_extractor"}


def provider_names(providers: list[str] | None = None) -> list[str]:
    names = list(providers or config.LLM_PROVIDERS)
    unknown = [name for name in names if name not in PROVIDER_MODULES]
    if unknown:
        raise ValueError(f"Unknown LLM provider(s): {unknown} — known: {sorted(PROVIDER_MODULES)}")
    return names


def extract_from_image(image_path: str | Path, known_senders: list[str], providers: list[str] | None = None) -> dict[str, Any]:
    """The first usable answer from the providers, in order."""
    names = provider_names(providers)
    resting: list[ModelsUnavailableError] = []
    failed: list[str] = []
    for name in names:
        module = importlib.import_module(PROVIDER_MODULES[name])
        try:
            result = module.extract_from_image(image_path, known_senders)
        except MissingApiKeyError:
            logger.info("LLM provider %s is not configured — skipped", name)
            continue
        except ModelsUnavailableError as exc:
            logger.warning("LLM provider %s unavailable (%s) — trying the next one", name, exc.reason)
            resting.append(exc)
            continue
        except ExtractionError as exc:
            logger.warning("LLM provider %s gave no usable answer (%s) — trying the next one", name, exc)
            failed.append(f"{name}: {exc}")
            continue
        result["_provider"] = name
        if resting or failed:
            logger.info("Page read by %s after %d other provider(s) failed", name, len(resting) + len(failed))
        return result

    if failed:
        raise ExtractionError("No LLM provider returned a usable answer — " + "; ".join(failed))
    if resting:
        reason = "quota" if any(exc.reason == "quota" for exc in resting) else "busy"
        seconds = min(exc.retry_after_seconds for exc in resting)  # the first one back takes the next page
        raise ModelsUnavailableError(f"All LLM providers are resting ({', '.join(names)})", seconds, reason)
    raise MissingApiKeyError(f"No LLM provider is configured — set a key for one of: {', '.join(names)}")
