"""OpenAI: the same page extraction as gemini.py, done by an OpenAI model.

Same prompt file, same field list and the same output shape as Gemini, so both answers go through the same
verification rules and can be compared fairly. Talks to the REST API with httpx (no extra SDK). The API key never
appears in errors or logs.

WARNING: Page images are transmitted to OpenAI's servers.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from integrations.llm.errors import ExtractionError, MissingApiKeyError
from integrations.llm.page_image import PageImageSettings, page_as_jpeg
from integrations.llm.prompt import ExtractionPrompt
from integrations.llm.schema import response_schema
from integrations.llm.tls import TlsSettings, ssl_context


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str
    model: str
    api_url: str
    timeout_seconds: int


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
    leaf: dict[str, Any] = {"type": kind}
    if "enum" in node:
        leaf["enum"] = node["enum"]
    return leaf


@lru_cache(maxsize=1)
def strict_schema() -> dict[str, Any]:
    return _to_strict_json_schema(response_schema())


def drop_nulls(value: Any) -> Any:
    """Strict mode returns null for absent optional properties; Gemini simply omits them — make them match."""
    if isinstance(value, dict):
        return {k: drop_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [drop_nulls(v) for v in value]
    return value


class OpenAIProvider:
    name = "openai"

    def __init__(self, settings: OpenAISettings, prompt: ExtractionPrompt, image: PageImageSettings,
                 tls: TlsSettings | None = None) -> None:
        self._settings = settings
        self._prompt = prompt
        self._image = image
        self._tls = tls

    def extract_from_image(self, image_path: str | Path, known_senders: list[str] | None = None, model: str | None = None) -> dict[str, Any]:
        """Return OpenAI's JSON for one page in the same shape as Gemini's.
        Adds _model, _seconds and _usage (token counts) for the comparison."""
        settings = self._settings
        if not settings.api_key:
            raise MissingApiKeyError("OPENAI_API_KEY is not set (backend/.env).")
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Page image not found: {path}")

        model = model or settings.model
        image_b64 = base64.b64encode(page_as_jpeg(path, self._image)).decode("ascii")
        body = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": self._prompt.build(known_senders or [])},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}", "detail": "high"}},
                ],
            }],
            "response_format": {"type": "json_schema", "json_schema": {"name": "form_extraction", "strict": True, "schema": strict_schema()}},
        }

        started = time.time()
        try:
            response = httpx.post(
                settings.api_url,
                json=body,
                headers={"Authorization": f"Bearer {settings.api_key}"},
                timeout=settings.timeout_seconds,
                verify=ssl_context(self._tls) or True,
            )
        except httpx.HTTPError as exc:
            raise ExtractionError(f"OpenAI request failed: {type(exc).__name__}") from None
        if response.status_code != 200:
            detail = response.text[:300].replace(settings.api_key, "<KEY>")
            raise ExtractionError(f"OpenAI API error {response.status_code}: {detail}")

        payload = response.json()
        content = payload["choices"][0]["message"].get("content") or ""
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            raise ExtractionError(f"OpenAI returned invalid JSON ({len(content)} chars)") from None

        result = drop_nulls(result)
        result["_model"] = model
        result["_seconds"] = round(time.time() - started, 1)
        result["_usage"] = payload.get("usage", {})
        return result
