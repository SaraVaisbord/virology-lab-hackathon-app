"""TLS of the LLM clients: verified by default, a custom CA possible, and never a change to the whole process."""

from __future__ import annotations

import ssl
from pathlib import Path

import certifi

from config import load_settings
from integrations.llm.gemini import GeminiProvider, GeminiSettings
from integrations.llm.page_image import PageImageSettings
from integrations.llm.prompt import ExtractionPrompt
from integrations.llm.tls import TlsSettings, ssl_context


def test_certificates_are_verified_by_default():
    settings = load_settings({})
    assert settings.llm_insecure_ssl is False and settings.llm_ca_bundle == ""
    assert ssl_context(TlsSettings(ca_bundle="", insecure=False)) is None  # the library's own verified default


def test_a_custom_ca_bundle_is_trusted_and_verified():
    context = ssl_context(TlsSettings(ca_bundle=certifi.where(), insecure=False))
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname


def test_insecure_mode_stays_inside_the_llm_client():
    original = ssl.create_default_context
    tls = TlsSettings(ca_bundle="", insecure=True)
    assert ssl_context(tls).verify_mode == ssl.CERT_NONE

    settings = GeminiSettings(api_keys=["test-key"], models=["m"], timeout_seconds=1, max_attempts=1,
                              quota_default_backoff_seconds=1, busy_cooldown_seconds=1, invalid_key_cooldown_seconds=1)
    prompt = ExtractionPrompt(Path(__file__).resolve().parents[1] / "prompts" / "extraction_prompt.md")
    GeminiProvider(settings, prompt, PageImageSettings(max_side_px=100, jpeg_quality=80), tls).router.client(0)  # no request

    # Every other connection of the process (S3, SMTP, …) still verifies certificates.
    assert ssl.create_default_context is original
    assert ssl.create_default_context().verify_mode == ssl.CERT_REQUIRED
