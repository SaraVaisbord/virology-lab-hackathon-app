"""
claude_extractor.py - The same page extraction as ai_extractor.py, done by Claude (Anthropic).

Same prompt file, same field list and the same output shape as Gemini (structured output from the same schema), so
the answer goes through the same verification rules and the provider can be switched freely (services/llm_router.py).
Several keys (config.ANTHROPIC_API_KEYS) are tried in turn. A key that hit its rate limit or was rejected rests for a
while; when Claude itself is overloaded every key rests (another key can't help), so the next pages go straight to
the next provider. The API keys and the model's answer never appear in errors or logs.

WARNING: Page images are transmitted to Anthropic's servers.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import anthropic

import config
from ai_extractor import ExtractionError, MissingApiKeyError, ModelsUnavailableError, _image_as_jpeg, build_prompt, response_schema

logger = logging.getLogger(__name__)

# Refusals are re-run on another Claude model inside the same call (server-side fallback, routed by category).
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

_rest_lock = threading.Lock()
_resting: dict[int, tuple[float, str]] = {}  # key index → (resting until, "quota" | "busy" | "rejected_key")


class _KeyProblem(Exception):
    """This key can't serve the request right now: rest it (or every key, for `all_keys`) and try the next one."""

    def __init__(self, seconds: float, reason: str, all_keys: bool = False):
        super().__init__(reason)
        self.seconds, self.reason, self.all_keys = seconds, reason, all_keys


def _to_json_schema(node: dict[str, Any]) -> dict[str, Any]:
    """The Gemini-style schema (uppercase types) as standard JSON Schema; objects closed, optional stays optional."""
    kind = node["type"].lower()
    if kind == "object":
        return {
            "type": "object",
            "properties": {name: _to_json_schema(child) for name, child in node["properties"].items()},
            "required": list(node.get("required", [])),
            "additionalProperties": False,
        }
    if kind == "array":
        return {"type": "array", "items": _to_json_schema(node["items"])}
    return {"type": kind, **({"enum": node["enum"]} if "enum" in node else {})}


@lru_cache(maxsize=1)
def json_schema() -> dict[str, Any]:
    """Claude allows at most 24 optional properties in a structured-output schema, counting every repetition — the
    per-field candidate (3 optional properties × 7 fields) alone is 21. So an item schema used by several fields is
    defined once in $defs and referenced; the answer has exactly the same shape."""
    schema = _to_json_schema(response_schema())
    arrays = [prop for prop in schema["properties"].values() if prop.get("type") == "array"]
    shared = next((prop["items"] for prop in arrays if sum(other["items"] == prop["items"] for other in arrays) > 1), None)
    if shared is not None:
        schema["$defs"] = {"candidate": shared}
        for prop in arrays:
            if prop["items"] == shared:
                prop["items"] = {"$ref": "#/$defs/candidate"}
    return schema


@lru_cache(maxsize=None)
def _client(key_index: int) -> anthropic.Anthropic:
    http_client = anthropic.DefaultHttpxClient(verify=False) if config.GEMINI_INSECURE_SSL else None
    return anthropic.Anthropic(
        api_key=config.ANTHROPIC_API_KEYS[key_index], timeout=config.CLAUDE_TIMEOUT_SECONDS, http_client=http_client,
    )


# ── Resting keys ─────────────────────────────────────────────────────────────


def _rest(key_index: int, problem: _KeyProblem) -> None:
    until = time.time() + problem.seconds
    targets = range(len(config.ANTHROPIC_API_KEYS)) if problem.all_keys else [key_index]
    with _rest_lock:
        for index in targets:
            if _resting.get(index, (0.0, ""))[0] < until:
                _resting[index] = (until, problem.reason)
    logger.warning("Claude key #%d: %s — resting %.0fs%s", key_index + 1, problem.reason, problem.seconds,
                   " (every key)" if problem.all_keys else "")


def _available_keys() -> list[int]:
    now = time.time()
    with _rest_lock:
        return [index for index in range(len(config.ANTHROPIC_API_KEYS)) if _resting.get(index, (0.0, ""))[0] <= now]


def _unavailable_error() -> ExtractionError:
    """Every key is resting: not configured if all were rejected, otherwise unavailable until the first one is back."""
    now = time.time()
    with _rest_lock:
        resting = [(until - now, reason) for until, reason in _resting.values() if until > now]
    reasons = {reason for _, reason in resting}
    if reasons == {"rejected_key"}:
        return MissingApiKeyError("Anthropic rejected every API key.")
    usable = [(seconds, reason) for seconds, reason in resting if reason != "rejected_key"]
    if not usable:  # a rest ran out in the meantime: the next page simply tries again
        return ModelsUnavailableError("All Claude keys were busy", 1.0, "busy")
    reason = "quota" if all(reason == "quota" for _, reason in usable) else "busy"
    return ModelsUnavailableError("All Claude keys are resting", max(min(seconds for seconds, _ in usable), 1.0), reason)


# ── Request ──────────────────────────────────────────────────────────────────


def _retry_after(exc: anthropic.APIStatusError) -> float:
    try:
        return float(exc.response.headers.get("retry-after", ""))
    except ValueError:
        return config.CLAUDE_QUOTA_DEFAULT_BACKOFF_SECONDS


def _request(key_index: int, image_b64: str, prompt: str):
    try:
        return _client(key_index).beta.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=config.CLAUDE_MAX_TOKENS,
            betas=[_FALLBACK_BETA],
            fallbacks="default",
            output_config={"effort": config.CLAUDE_EFFORT, "format": {"type": "json_schema", "schema": json_schema()}},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
    # Most specific first. Key problems → the next key; Claude overloaded → every key rests; anything else is a
    # problem with this request, which another key won't fix.
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
        raise _KeyProblem(config.CLAUDE_INVALID_KEY_COOLDOWN_SECONDS, "rejected_key") from None
    except anthropic.RateLimitError as exc:
        raise _KeyProblem(_retry_after(exc), "quota") from None
    except anthropic.APIStatusError as exc:
        # 5xx — overloaded (529), unavailable, internal: not a SDK subclass of one another, so judged by the code.
        if exc.status_code >= 500:
            raise _KeyProblem(config.CLAUDE_BUSY_COOLDOWN_SECONDS, "busy", all_keys=True) from None
        raise ExtractionError(f"Claude API error {exc.status_code}") from None
    except anthropic.APIConnectionError:  # includes timeouts
        raise _KeyProblem(config.CLAUDE_BUSY_COOLDOWN_SECONDS, "busy", all_keys=True) from None


def extract_from_image(image_path: str | Path, known_senders: list[str] | None = None) -> dict[str, Any]:
    """Return Claude's JSON for one page, in the same shape as ai_extractor.extract_from_image (plus _model, _usage).

    Raises MissingApiKeyError (no key / every key rejected), ModelsUnavailableError (every key resting: quota or
    overload) or ExtractionError (refusal, cut-off or unusable answer)."""
    if not config.ANTHROPIC_API_KEYS:
        raise MissingApiKeyError("ANTHROPIC_API_KEY is not set (backend/.env).")
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Page image not found: {path}")

    image_b64 = base64.standard_b64encode(_image_as_jpeg(path)).decode("ascii")
    prompt = build_prompt(known_senders or [])
    for key_index in _available_keys():
        try:
            response = _request(key_index, image_b64, prompt)
        except _KeyProblem as problem:
            _rest(key_index, problem)
            if problem.all_keys:
                break
            continue
        result = _parse(response)
        result["_key"] = key_index + 1  # which key answered (1-based, as in the logs)
        return result
    raise _unavailable_error()


def _parse(response) -> dict[str, Any]:
    if response.stop_reason == "refusal":
        raise ExtractionError("Claude declined the page")
    if response.stop_reason == "max_tokens":
        raise ExtractionError(f"Claude's answer was cut off at {config.CLAUDE_MAX_TOKENS} tokens")
    text = next((block.text for block in response.content if block.type == "text"), "")
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        raise ExtractionError(f"Claude returned invalid JSON ({len(text)} chars)") from None
    if not isinstance(result, dict):
        raise ExtractionError("Claude returned JSON that is not an object.")
    result["_model"] = response.model
    result["_usage"] = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    return result
