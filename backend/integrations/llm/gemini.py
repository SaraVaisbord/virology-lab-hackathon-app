"""Gemini: send one page image and get structured field candidates back.

Calls are routed over every (API key, model) pair:
- quota exhausted (429)          → that route rests until Google's retry time; the next route is tried at once
- model overloaded (5xx/timeout) → that route rests busy_cooldown_seconds; the next route (other model) is tried
- key rejected (400/401/403)     → that key's routes rest invalid_key_cooldown_seconds
Only when every route is resting does extraction raise ModelsUnavailableError, so the queue pauses until the
first route is available again. Keys never appear in logs or error messages — only their position ("key #2").

WARNING: Page images are transmitted to Google's Gemini API servers.
Review https://ai.google.dev/gemini-api/terms before processing real medical records.
"""

from __future__ import annotations

import json
import logging
import re
import ssl
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from integrations.llm.errors import ExtractionError, MissingApiKeyError, ModelsUnavailableError
from integrations.llm.page_image import PageImageSettings, page_as_jpeg
from integrations.llm.prompt import ExtractionPrompt
from integrations.llm.schema import response_schema

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeminiSettings:
    api_keys: list[str]
    models: list[str]  # primary first, then the fallbacks
    timeout_seconds: int
    max_attempts: int  # unusable answers tolerated for one page before it fails
    # How long a key+model route rests after a failure before it is tried again:
    quota_default_backoff_seconds: int  # 429 without a retry time
    busy_cooldown_seconds: int  # 500/503/504/timeout (model overloaded)
    invalid_key_cooldown_seconds: int  # 400/401/403 key rejected


# ── Error classification ─────────────────────────────────────────────────────

_RETRY_IN_PATTERN = re.compile(r"retry in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", re.IGNORECASE)
_BUSY_CODES = {500, 502, 503, 504}
_REJECTED_KEY_CODES = {401, 403}


def retry_after_seconds(message: str, default: float) -> float:
    match = _RETRY_IN_PATTERN.search(message)
    if not match or not any(match.groups()):
        return default
    hours, minutes, seconds = (float(group or 0) for group in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def _classify(exc: Exception) -> str | None:
    """'quota' / 'busy' / 'rejected_key' for route problems; None for errors another route can't fix."""
    code = getattr(exc, "code", None)
    text = str(exc)
    if code == 429 or "RESOURCE_EXHAUSTED" in text:
        return "quota"
    if code in _BUSY_CODES or "timed out" in text.lower() or "UNAVAILABLE" in text or "DEADLINE_EXCEEDED" in text:
        return "busy"
    # Google answers an invalid key with 400 INVALID_ARGUMENT, so it's recognised by the message, not the code.
    if code in _REJECTED_KEY_CODES or "API_KEY_INVALID" in text or "API key not valid" in text or "PERMISSION_DENIED" in text:
        return "rejected_key"
    return None


# ── Routing over keys × models ───────────────────────────────────────────────


@dataclass
class Route:
    key_index: int  # position in the key list (1-based in logs)
    model: str
    resting_until: float = 0.0
    last_problem: str | None = None

    @property
    def label(self) -> str:
        return f"key #{self.key_index + 1} / {self.model}"


class GeminiRouter:
    """Thread-safe choice of the next usable key+model route. Order: primary model on every key first,
    then the fallback models — so a fallback model is only used when the primary is out on all keys.
    new_client(key_index) creates the API client of one key (once; clients are reused)."""

    def __init__(self, key_count: int, models: list[str], new_client: Callable[[int], Any]) -> None:
        self._routes = [Route(key_index, model) for model in models for key_index in range(key_count)]
        self._new_client = new_client
        self._lock = threading.Lock()
        self._clients: dict[int, Any] = {}

    @property
    def routes(self) -> list[Route]:
        return self._routes

    def next_route(self, exclude: set[int]) -> Route | None:
        now = time.time()
        with self._lock:
            return next((r for i, r in enumerate(self._routes) if i not in exclude and r.resting_until <= now), None)

    def rest(self, route: Route, seconds: float, problem: str, whole_key: bool = False, whole_model: bool = False) -> None:
        """whole_key: the key itself is bad (every model on it rests). whole_model: the model is overloaded — that
        is Google's capacity, not the key's, so trying it with another key would only send the page again."""
        until = time.time() + seconds
        with self._lock:
            if whole_key:
                targets = [r for r in self._routes if r.key_index == route.key_index]
            elif whole_model:
                targets = [r for r in self._routes if r.model == route.model]
            else:
                targets = [route]
            for target in targets:
                target.resting_until = max(target.resting_until, until)
                target.last_problem = problem

    def all_resting(self) -> bool:
        now = time.time()
        with self._lock:
            return all(r.resting_until > now for r in self._routes)

    def unavailable_error(self) -> ModelsUnavailableError:
        now = time.time()
        with self._lock:
            resting = [r for r in self._routes if r.resting_until > now]
            wait = min(r.resting_until for r in resting) - now if resting else 1.0
            all_quota = bool(resting) and all(r.last_problem == "quota" for r in resting)
        return ModelsUnavailableError("All Gemini routes are resting", max(wait, 1.0), "quota" if all_quota else "busy")

    def client(self, key_index: int):
        with self._lock:
            if key_index not in self._clients:
                self._clients[key_index] = self._new_client(key_index)
            return self._clients[key_index]

    def status(self) -> dict[str, int]:
        now = time.time()
        with self._lock:
            return {"total": len(self._routes), "available": sum(r.resting_until <= now for r in self._routes)}


def _disable_ssl_verification_once() -> None:
    # MVP workaround for a CA-certificate issue on Python 3.14 / Windows (see config.GEMINI_INSECURE_SSL).
    if getattr(ssl, "_gemini_patched", False):
        return
    original = ssl.create_default_context

    def insecure_context(*args, **kwargs):
        ctx = original(*args, **kwargs)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    ssl.create_default_context = insecure_context
    ssl._gemini_patched = True  # type: ignore[attr-defined]


def _parse_response(response) -> dict[str, Any]:
    try:
        result = json.loads(response.text or "")
    except json.JSONDecodeError:
        # Never put the response text in the message: it may contain patient data and errors are logged.
        raise ExtractionError(f"Model returned invalid JSON ({len(response.text or '')} chars)") from None
    if not isinstance(result, dict):
        raise ExtractionError("Model returned JSON that is not an object.")
    return result


class GeminiProvider:
    name = "gemini"

    def __init__(self, settings: GeminiSettings, prompt: ExtractionPrompt, image: PageImageSettings,
                 verify_tls: bool = True, new_client: Callable[[int], Any] | None = None) -> None:
        self._settings = settings
        self._prompt = prompt
        self._image = image
        self._verify_tls = verify_tls
        self.router = GeminiRouter(len(settings.api_keys), settings.models, new_client or self._new_client)

    def _new_client(self, key_index: int):
        from google import genai
        from google.genai import types

        if not self._verify_tls:
            _disable_ssl_verification_once()
        return genai.Client(
            api_key=self._settings.api_keys[key_index],
            http_options=types.HttpOptions(timeout=self._settings.timeout_seconds * 1000),
        )

    def _cooldown_seconds(self, kind: str, exc: Exception) -> float:
        if kind == "quota":
            return retry_after_seconds(str(exc), self._settings.quota_default_backoff_seconds)
        if kind == "busy":
            return self._settings.busy_cooldown_seconds
        return self._settings.invalid_key_cooldown_seconds

    def extract_from_image(self, image_path: str | Path, known_senders: list[str] | None = None) -> dict[str, Any]:
        """Return the model's JSON for one page, trying routes until one answers.

        Raises ModelsUnavailableError (all routes resting), MissingApiKeyError, or ExtractionError (bad answers /
        errors no other route can fix)."""
        from google.genai import types

        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Page image not found: {path}")
        if not self._settings.api_keys:
            raise MissingApiKeyError("No Gemini API key configured (GEMINI_API_KEY / GEMINI_API_KEYS in backend/.env).")

        router = self.router
        contents = [
            types.Part.from_bytes(data=page_as_jpeg(path, self._image), mime_type="image/jpeg"),
            types.Part.from_text(text=self._prompt.build(known_senders or [])),
        ]
        request_config = types.GenerateContentConfig(response_mime_type="application/json", response_schema=response_schema(), temperature=0)
        tried: set[int] = set()
        bad_answers = 0

        while True:
            route = router.next_route(exclude=tried)
            if route is None:
                if router.all_resting():
                    raise router.unavailable_error()
                # Every usable route was already tried for this page and none gave a usable answer: a page problem,
                # not a capacity one — fail the form instead of re-queueing it (which would burn tokens in a loop).
                raise ExtractionError("No route returned a usable answer for this page")
            tried.add(router.routes.index(route))
            try:
                response = router.client(route.key_index).models.generate_content(model=route.model, contents=contents, config=request_config)
            except Exception as exc:
                kind = _classify(exc)
                if kind is None:
                    raise ExtractionError(f"Gemini API error: {exc}") from exc
                seconds = self._cooldown_seconds(kind, exc)
                router.rest(route, seconds, kind, whole_key=(kind == "rejected_key"), whole_model=(kind == "busy"))
                logger.warning("Gemini route %s: %s — resting %.0fs, trying next route", route.label, kind, seconds)
                continue

            try:
                result = _parse_response(response)
            except ExtractionError:
                bad_answers += 1
                if bad_answers >= self._settings.max_attempts:
                    raise
                logger.warning("Gemini route %s returned an unusable answer — trying next route", route.label)
                continue

            result["_model"] = route.model
            return result
