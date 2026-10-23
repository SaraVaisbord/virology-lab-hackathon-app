"""Gemini key/model routing (integrations/llm/gemini.py) — no real API calls (a fake client simulates Google's
answers and errors)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pytest

from integrations.llm.errors import ExtractionError, ModelsUnavailableError
from integrations.llm.gemini import GeminiProvider, GeminiSettings
from integrations.llm.page_image import PageImageSettings
from integrations.llm.prompt import ExtractionPrompt
from tests.conftest import png_bytes

KEYS = ["SECRET-KEY-ONE", "SECRET-KEY-TWO"]
MODELS = ["primary-model", "fallback-model"]
GOOD_JSON = json.dumps({"central_number": [{"value": "12345", "confidence": "high"}]})


class FakeApiError(Exception):
    def __init__(self, code: int, message: str = ""):
        super().__init__(f"{code} {message}")
        self.code = code


class FakeResponse:
    def __init__(self, text: str):
        self.text = text


def _gemini(behaviour: dict) -> tuple[GeminiProvider, list]:
    """behaviour[(key_index, model)] = Exception to raise or response text; missing → good JSON.
    Returns the provider (its routes: provider.router.routes) and the (key_index, model) of every call."""
    calls = []

    class Models:
        def __init__(self, key_index):
            self.key_index = key_index

        def generate_content(self, model, contents, config):
            calls.append((self.key_index, model))
            outcome = behaviour.get((self.key_index, model), GOOD_JSON)
            if isinstance(outcome, Exception):
                raise outcome
            return FakeResponse(outcome)

    class Client:
        def __init__(self, key_index):
            self.models = Models(key_index)

    settings = GeminiSettings(api_keys=KEYS, models=MODELS, timeout_seconds=120, max_attempts=2,
                              quota_default_backoff_seconds=60, busy_cooldown_seconds=90, invalid_key_cooldown_seconds=3600)
    prompt = ExtractionPrompt(Path(__file__).resolve().parents[1] / "prompts" / "extraction_prompt.md")
    provider = GeminiProvider(settings, prompt, PageImageSettings(max_side_px=1600, jpeg_quality=80), new_client=Client)
    return provider, calls


@pytest.fixture
def page(tmp_path):
    path = tmp_path / "page.png"
    path.write_bytes(png_bytes())
    return path


def test_quota_on_first_key_moves_to_second_key(monkeypatch, page):
    gemini, calls = _gemini({(0, "primary-model"): FakeApiError(429, "RESOURCE_EXHAUSTED retry in 30s")})

    result = gemini.extract_from_image(page)
    assert calls == [(0, "primary-model"), (1, "primary-model")]
    assert result["_model"] == "primary-model"
    first = gemini.router.routes[0]
    assert first.last_problem == "quota" and 25 < first.resting_until - time.time() <= 30


def test_overloaded_model_falls_back_to_next_model(monkeypatch, page):
    busy = FakeApiError(503, "UNAVAILABLE high demand")
    gemini, calls = _gemini({(0, "primary-model"): busy, (1, "primary-model"): busy})

    assert gemini.extract_from_image(page)["_model"] == "fallback-model"
    # An overloaded model is Google's capacity, not the key's: the page is not sent to it again with key #2.
    assert calls == [(0, "primary-model"), (0, "fallback-model")]


def test_resting_routes_are_skipped_on_the_next_page(monkeypatch, page):
    gemini, calls = _gemini({(0, "primary-model"): FakeApiError(429, "RESOURCE_EXHAUSTED")})
    gemini.extract_from_image(page)
    calls.clear()

    gemini.extract_from_image(page)
    assert calls == [(1, "primary-model")]  # key #1 is still resting (quota is per key)


def test_overloaded_model_rests_on_every_key(monkeypatch, page):
    gemini, calls = _gemini({(0, "primary-model"): FakeApiError(504, "DEADLINE_EXCEEDED")})
    gemini.extract_from_image(page)
    calls.clear()

    gemini.extract_from_image(page)
    assert calls == [(0, "fallback-model")]  # the primary model rests on both keys


def test_all_routes_out_of_quota_pauses_until_the_earliest(monkeypatch, page):
    behaviour = {(k, m): FakeApiError(429, f"retry in {10 + 10 * k}s") for k in range(2) for m in MODELS}
    gemini, _ = _gemini(behaviour)

    with pytest.raises(ModelsUnavailableError) as info:
        gemini.extract_from_image(page)
    assert info.value.reason == "quota"
    assert 5 < info.value.retry_after_seconds <= 10


def test_mixed_quota_and_overload_is_reported_as_busy(monkeypatch, page):
    behaviour = {(k, m): FakeApiError(429 if m == "primary-model" else 503) for k in range(2) for m in MODELS}
    gemini, _ = _gemini(behaviour)

    with pytest.raises(ModelsUnavailableError) as info:
        gemini.extract_from_image(page)
    assert info.value.reason == "busy"


def test_rejected_key_rests_all_its_models(monkeypatch, page):
    gemini, calls = _gemini({(0, "primary-model"): FakeApiError(403, "PERMISSION_DENIED")})
    gemini.extract_from_image(page)

    resting_key_one = [r.resting_until > time.time() for r in gemini.router.routes if r.key_index == 0]
    assert resting_key_one == [True, True]


def test_non_route_error_fails_immediately(monkeypatch, page):
    gemini, calls = _gemini({(0, "primary-model"): FakeApiError(400, "INVALID_ARGUMENT bad schema")})
    with pytest.raises(ExtractionError) as info:
        gemini.extract_from_image(page)
    assert not isinstance(info.value, ModelsUnavailableError)
    assert calls == [(0, "primary-model")]


def test_unusable_answers_fail_the_page_instead_of_looping(monkeypatch, page):
    """A page that keeps producing broken JSON must not be re-queued forever (that would burn tokens)."""
    behaviour = {(k, m): '{"broken' for k in range(2) for m in MODELS}
    gemini, calls = _gemini(behaviour)

    with pytest.raises(ExtractionError) as info:
        gemini.extract_from_image(page)
    assert not isinstance(info.value, ModelsUnavailableError)
    assert len(calls) == 2  # GEMINI_MAX_ATTEMPTS


def test_keys_and_model_output_never_reach_logs_or_errors(monkeypatch, page, caplog):
    leak = '{"first_name": [{"value": "ישראל ישראלי"'
    behaviour = {(0, "primary-model"): FakeApiError(429), (1, "primary-model"): leak, (0, "fallback-model"): leak}
    gemini, _ = _gemini(behaviour)

    with caplog.at_level(logging.WARNING), pytest.raises(ExtractionError) as info:
        gemini.extract_from_image(page)
    everything = caplog.text + str(info.value)
    assert "key #1" in caplog.text
    assert not any(key in everything for key in KEYS)
    assert "ישראל" not in everything


def test_key_list_config():
    from config import load_settings

    settings = load_settings({
        "GEMINI_API_KEY": "a",
        "GEMINI_API_KEY_10": "n10",  # numeric (not alphabetical) order: _2 before _10
        "GEMINI_API_KEY_2": "n2",
        "GEMINI_API_KEYS": "b, a ,your-key-here,,c",
        "GEMINI_FALLBACK_MODELS": "m2, m3",
        "GEMINI_MODEL": "m1",
    })
    # single key first, then numbered keys, then the list; deduplicated, placeholder dropped
    assert settings.gemini_api_keys == ["a", "n2", "n10", "b", "c"]
    assert settings.gemini_models == ["m1", "m2", "m3"]


def test_invalid_key_answered_with_400_is_treated_as_rejected(monkeypatch, page):
    invalid = FakeApiError(400, "INVALID_ARGUMENT API key not valid. Please pass a valid API key.")
    gemini, calls = _gemini({(0, "primary-model"): invalid})

    assert gemini.extract_from_image(page)["_model"] == "primary-model"
    assert calls == [(0, "primary-model"), (1, "primary-model")]
    assert all(r.last_problem == "rejected_key" for r in gemini.router.routes if r.key_index == 0)


def test_tests_never_see_real_api_keys():
    """conftest sets APP_ENV=test before the settings load, so backend/.env secrets can't leak into test output."""
    import os

    from config import load_settings

    assert os.environ.get("APP_ENV") == "test"
    assert load_settings().openai_api_key == ""
    assert not [n for n in os.environ if n.startswith("GEMINI_API_KEY")]
