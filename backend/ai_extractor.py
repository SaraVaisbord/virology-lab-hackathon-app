"""
ai_extractor.py - Send one page image to Gemini and get structured field candidates back.

WARNING: Page images are transmitted to Google's Gemini API servers.
Review https://ai.google.dev/gemini-api/terms before processing real medical records.
"""

from __future__ import annotations

import io
import json
import logging
import re
import ssl
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image

import config
from db.constants import CONFIDENCE_LEVELS, FIELDS

logger = logging.getLogger(__name__)
_client_lock = threading.Lock()
_client = None


class ExtractionError(RuntimeError):
    """Raised when the model call fails or returns something unusable."""


class MissingApiKeyError(ExtractionError):
    """GEMINI_API_KEY is not configured."""


class QuotaExceededError(ExtractionError):
    """Gemini rate limit / quota hit (HTTP 429). Not the form's fault — the queue should pause and retry later."""

    def __init__(self, message: str, retry_after_seconds: float):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


_RETRY_IN_PATTERN = re.compile(r"retry in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", re.IGNORECASE)


def _retry_after_seconds(message: str) -> float:
    match = _RETRY_IN_PATTERN.search(message)
    if not match or not any(match.groups()):
        return config.GEMINI_QUOTA_DEFAULT_BACKOFF_SECONDS
    hours, minutes, seconds = (float(group or 0) for group in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def _is_quota_error(exc: Exception) -> bool:
    return getattr(exc, "code", None) == 429 or "RESOURCE_EXHAUSTED" in str(exc)


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
    ssl._gemini_patched = True


def _get_client():
    global _client
    with _client_lock:
        if _client is None:
            if not config.GEMINI_API_KEY or config.GEMINI_API_KEY == "your-key-here":
                raise MissingApiKeyError("GEMINI_API_KEY is not set (backend/.env).")
            from google import genai
            from google.genai import types

            if config.GEMINI_INSECURE_SSL:
                _disable_ssl_verification_once()
            _client = genai.Client(
                api_key=config.GEMINI_API_KEY,
                http_options=types.HttpOptions(timeout=config.GEMINI_TIMEOUT_SECONDS * 1000),
            )
        return _client


@lru_cache(maxsize=1)
def _prompt_template() -> str:
    return config.EXTRACTION_PROMPT_FILE.read_text(encoding="utf-8")


def build_prompt(known_senders: list[str]) -> str:
    senders = "\n".join(f"- {name}" for name in known_senders) or "- (none)"
    return _prompt_template().replace("{{known_senders}}", senders)


def _image_as_jpeg(image_path: Path) -> bytes:
    with Image.open(image_path) as image:
        image = image.convert("RGB")
        image.thumbnail((config.GEMINI_IMAGE_MAX_SIDE_PX, config.GEMINI_IMAGE_MAX_SIDE_PX))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=config.GEMINI_IMAGE_JPEG_QUALITY)
        return buffer.getvalue()


@lru_cache(maxsize=1)
def response_schema() -> dict[str, Any]:
    """Structured-output schema, generated from the field list so the model can only return valid JSON with our keys."""
    candidate = {
        "type": "OBJECT",
        "properties": {
            "value": {"type": "STRING"},
            "confidence": {"type": "STRING", "enum": sorted(CONFIDENCE_LEVELS)},
            "box_2d": {"type": "ARRAY", "items": {"type": "INTEGER"}},
            "label": {"type": "STRING"},
            "reason": {"type": "STRING"},
        },
        "required": ["value", "confidence"],
    }
    properties = {name: {"type": "ARRAY", "items": candidate} for name in FIELDS}
    properties["notes"] = {"type": "STRING"}
    return {"type": "OBJECT", "properties": properties, "required": list(FIELDS)}


def _call_model(path: Path, known_senders: list[str]) -> dict[str, Any]:
    from google.genai import types

    try:
        response = _get_client().models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=_image_as_jpeg(path), mime_type="image/jpeg"),
                types.Part.from_text(text=build_prompt(known_senders)),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema(),
                temperature=0,
            ),
        )
    except Exception as exc:
        if _is_quota_error(exc):
            raise QuotaExceededError(f"Gemini quota exceeded: {exc}", _retry_after_seconds(str(exc))) from exc
        raise ExtractionError(f"Gemini API error: {exc}") from exc

    try:
        result = json.loads(response.text or "")
    except json.JSONDecodeError as exc:
        # Never put the response text in the message: it may contain patient data and errors are logged.
        raise ExtractionError(f"Model returned invalid JSON ({len(response.text or '')} chars)") from None
    if not isinstance(result, dict):
        raise ExtractionError("Model returned JSON that is not an object.")
    return result


def extract_from_image(image_path: str | Path, known_senders: list[str] | None = None) -> dict[str, Any]:
    """Return the model's JSON for one page. Raises ExtractionError (or one of its subclasses)."""
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Page image not found: {path}")

    for attempt in range(1, config.GEMINI_MAX_ATTEMPTS + 1):
        try:
            result = _call_model(path, known_senders or [])
            break
        except (QuotaExceededError, MissingApiKeyError):
            raise  # retrying immediately can't help (and would burn quota)
        except ExtractionError:
            if attempt == config.GEMINI_MAX_ATTEMPTS:
                raise
            logger.warning("Gemini attempt %d/%d failed for %s, retrying", attempt, config.GEMINI_MAX_ATTEMPTS, path.name)

    result["_model"] = config.GEMINI_MODEL
    return result
