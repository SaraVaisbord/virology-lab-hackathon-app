"""Automatic failover between LLM providers, in the configured order.

Every provider has the same interface (base.LlmProvider) and the same three ways to fail:
  MissingApiKeyError       not configured (or key rejected)      → skipped
  ModelsUnavailableError   out of quota / overloaded, resting    → the next provider takes the page
  ExtractionError          this page got no usable answer        → the next provider tries it
The answer records which provider gave it (`_provider`). When every configured provider is resting the page goes
back to the queue (ModelsUnavailableError, the queue pauses); when one of them failed on the page itself the form
fails — re-queueing it would only spend tokens again.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from integrations.llm.base import LlmProvider
from integrations.llm.errors import ExtractionError, MissingApiKeyError, ModelsUnavailableError

logger = logging.getLogger(__name__)


class LlmRouter:
    """providers: every known provider by name; order: which of them read pages, first that answers wins."""

    def __init__(self, providers: Mapping[str, LlmProvider], order: list[str]) -> None:
        self._providers = dict(providers)
        self._order = list(order)

    @property
    def known(self) -> list[str]:
        return sorted(self._providers)

    def provider_names(self, providers: list[str] | None = None) -> list[str]:
        names = list(providers or self._order)
        unknown = [name for name in names if name not in self._providers]
        if unknown:
            raise ValueError(f"Unknown LLM provider(s): {unknown} — known: {self.known}")
        return names

    def extract_from_image(self, image_path: str | Path, known_senders: list[str], providers: list[str] | None = None) -> dict[str, Any]:
        """The first usable answer from the providers, in order (`providers` overrides the configured order)."""
        names = self.provider_names(providers)
        resting: list[ModelsUnavailableError] = []
        failed: list[str] = []
        for name in names:
            try:
                result = self._providers[name].extract_from_image(image_path, known_senders)
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
