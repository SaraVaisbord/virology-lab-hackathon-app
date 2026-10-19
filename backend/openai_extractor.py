"""
openai_extractor.py - The same page extraction as ai_extractor.py, done by an OpenAI model.

Same prompt file, same field list and the same output shape as Gemini, so both answers go through the same
verification rules (extraction_service.build_fields) and can be compared fairly. Talks to the REST API with
httpx (no extra SDK). The API key never appears in errors or logs.

WARNING: Page images are transmitted to OpenAI's servers.
"""

from __future__ import annotations

import base64
import json
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

import config
from ai_extractor import ExtractionError, MissingApiKeyError, _image_as_jpeg, build_prompt, response_schema


def _to_strict_json_schema(node: dict[str, Any]) -> dict[str, Any]:
    """Convert the Gemini-style schema (uppercase types) to OpenAI strict JSON Schema: every object property is
    required and closed, so originally-optional properties become nullable."""
    kind = node["type"].lower()
    if kind == "object":
        required = set(node.get("required", []))
        properties = {}
        for name, child in node["properties"].items():
            converted = _to_strict_json_schema(child)
            if name not in required:
                converted["type"] = [converted["type"], "null"]
            properties[name] = converted
        return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}
    if kind == "array":
        return {"type": "array", "items": _to_strict_json_schema(node["items"])}
    converted = {"type": kind}
    if "enum" in node:
        converted["enum"] = node["enum"]
    return converted


@lru_cache(maxsize=1)
def strict_schema() -> dict[str, Any]:
    return _to_strict_json_schema(response_schema())


def _drop_nulls(value: Any) -> Any:
    """Strict mode returns null for absent optional properties; Gemini simply omits them — make them match."""
    if isinstance(value, dict):
        return {k: _drop_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_drop_nulls(v) for v in value]
    return value


def extract_from_image(image_path: str | Path, known_senders: list[str] | None = None, model: str | None = None) -> dict[str, Any]:
    """Return OpenAI's JSON for one page in the same shape as ai_extractor.extract_from_image.
    Adds _model, _seconds and _usage (token counts) for the comparison."""
    if not config.OPENAI_API_KEY:
        raise MissingApiKeyError("OPENAI_API_KEY is not set (backend/.env).")
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Page image not found: {path}")

    model = model or config.OPENAI_MODEL
    image_b64 = base64.b64encode(_image_as_jpeg(path)).decode("ascii")
    body = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": build_prompt(known_senders or [])},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}", "detail": "high"}},
            ],
        }],
        "response_format": {"type": "json_schema", "json_schema": {"name": "form_extraction", "strict": True, "schema": strict_schema()}},
    }

    started = time.time()
    try:
        response = httpx.post(
            config.OPENAI_API_URL,
            json=body,
            headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
            timeout=config.OPENAI_TIMEOUT_SECONDS,
            verify=not config.GEMINI_INSECURE_SSL,
        )
    except httpx.HTTPError as exc:
        raise ExtractionError(f"OpenAI request failed: {type(exc).__name__}") from None
    if response.status_code != 200:
        detail = response.text[:300].replace(config.OPENAI_API_KEY, "<KEY>")
        raise ExtractionError(f"OpenAI API error {response.status_code}: {detail}")

    payload = response.json()
    content = payload["choices"][0]["message"].get("content") or ""
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        raise ExtractionError(f"OpenAI returned invalid JSON ({len(content)} chars)") from None

    result = _drop_nulls(result)
    result["_model"] = model
    result["_seconds"] = round(time.time() - started, 1)
    result["_usage"] = payload.get("usage", {})
    return result
