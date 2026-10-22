"""Failover between LLM providers (services/llm_router.py) and the Claude provider (claude_extractor.py).
No network: provider functions and the Anthropic client are replaced with fakes."""

from __future__ import annotations

import types

import anthropic
import httpx2
import pytest

import ai_extractor
import claude_extractor
import config
from ai_extractor import ExtractionError, MissingApiKeyError, ModelsUnavailableError
from services import llm_router

_ANSWER = {"all_numbers": [], "commitment_number": [{"value": "47381"}]}


def _provider(answer=None, error=None, calls=None, name=""):
    def extract(image_path, known_senders):
        if calls is not None:
            calls.append(name)
        if error is not None:
            raise error
        return dict(answer or _ANSWER)
    return extract


@pytest.fixture
def providers(monkeypatch):
    """Install fake gemini / claude providers: providers(gemini=..., claude=...)."""
    def install(**fakes):
        modules = {"gemini": ai_extractor, "claude": claude_extractor}
        for name, fake in fakes.items():
            monkeypatch.setattr(modules[name], "extract_from_image", fake)
        monkeypatch.setattr(config, "LLM_PROVIDERS", list(fakes))
    return install


# ── Failover ─────────────────────────────────────────────────────────────────


def test_first_provider_answers(providers):
    calls = []
    providers(gemini=_provider(calls=calls, name="gemini"), claude=_provider(calls=calls, name="claude"))
    result = llm_router.extract_from_image("page.png", [])
    assert result["_provider"] == "gemini" and calls == ["gemini"]


@pytest.mark.parametrize("gemini_error", [
    ModelsUnavailableError("quota", 300, "quota"),
    MissingApiKeyError("no key"),
    ExtractionError("invalid JSON"),
])
def test_next_provider_takes_over(providers, gemini_error):
    providers(gemini=_provider(error=gemini_error), claude=_provider())
    assert llm_router.extract_from_image("page.png", [])["_provider"] == "claude"


def test_all_resting_pauses_with_the_earliest_return(providers):
    providers(gemini=_provider(error=ModelsUnavailableError("q", 300, "quota")),
              claude=_provider(error=ModelsUnavailableError("b", 90, "busy")))
    with pytest.raises(ModelsUnavailableError) as info:
        llm_router.extract_from_image("page.png", [])
    assert (info.value.retry_after_seconds, info.value.reason) == (90, "quota")


def test_resting_plus_unconfigured_still_pauses(providers):
    providers(gemini=_provider(error=ModelsUnavailableError("q", 120, "quota")), claude=_provider(error=MissingApiKeyError("x")))
    with pytest.raises(ModelsUnavailableError):
        llm_router.extract_from_image("page.png", [])


def test_a_bad_answer_fails_the_page_instead_of_requeueing(providers):
    providers(gemini=_provider(error=ModelsUnavailableError("q", 120, "quota")), claude=_provider(error=ExtractionError("refused")))
    with pytest.raises(ExtractionError) as info:
        llm_router.extract_from_image("page.png", [])
    assert not isinstance(info.value, ModelsUnavailableError) and "claude" in str(info.value)


def test_nothing_configured(providers):
    providers(gemini=_provider(error=MissingApiKeyError("a")), claude=_provider(error=MissingApiKeyError("b")))
    with pytest.raises(MissingApiKeyError):
        llm_router.extract_from_image("page.png", [])


def test_one_provider_can_be_forced(providers):
    providers(gemini=_provider(), claude=_provider())
    assert llm_router.extract_from_image("page.png", [], providers=["claude"])["_provider"] == "claude"
    with pytest.raises(ValueError):
        llm_router.extract_from_image("page.png", [], providers=["gpt-9"])


# ── Claude provider ──────────────────────────────────────────────────────────


class _FakeClient:
    """errors: one per call, in order (None = answer); after the list runs out every call answers."""

    def __init__(self, response=None, error=None, errors=None):
        self.requests = []
        pending = list(errors or ([error] if error is not None else []))

        def create(**kwargs):
            self.requests.append(kwargs)
            failure = pending.pop(0) if pending else None
            if failure is not None:
                raise failure
            return response or _response()

        self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))


def _response(text='{"all_numbers": []}', stop_reason="end_turn"):
    return types.SimpleNamespace(
        stop_reason=stop_reason, model="claude-opus-5-5",
        content=[types.SimpleNamespace(type="thinking", thinking=""), types.SimpleNamespace(type="text", text=text)],
        usage=types.SimpleNamespace(input_tokens=1800, output_tokens=420),
    )


def _status_error(cls, code, headers=None):
    response = httpx2.Response(code, headers=headers or {}, request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    return cls("error", response=response, body=None)


@pytest.fixture
def claude(monkeypatch, tmp_path):
    """A page image, configured keys, none resting; returns install(client, keys=1) → page path.
    The fake client records, per request, which key index sent it (`client.keys`)."""
    from PIL import Image

    page = tmp_path / "page.png"
    Image.new("RGB", (40, 30), "white").save(page)
    monkeypatch.setattr(claude_extractor, "_resting", {})

    def install(client, keys=1):
        claude_extractor._resting.clear()  # each install starts with fresh keys
        monkeypatch.setattr(config, "ANTHROPIC_API_KEYS", [f"test-key-{i}" for i in range(keys)])
        client.keys = []

        def client_for(key_index):
            client.keys.append(key_index)
            return client
        monkeypatch.setattr(claude_extractor, "_client", client_for)
        return page
    return install


def test_claude_request_and_answer(claude):
    client = _FakeClient(_response('{"all_numbers": [], "first_name": [{"value": "x"}]}'))
    result = claude_extractor.extract_from_image(claude(client), ["כללית"])
    assert result["first_name"] == [{"value": "x"}] and result["_model"] == "claude-opus-5-5"
    assert result["_usage"] == {"input_tokens": 1800, "output_tokens": 420}
    request = client.requests[0]
    assert request["model"] == config.CLAUDE_MODEL
    assert request["output_config"]["effort"] == config.CLAUDE_EFFORT
    assert request["output_config"]["format"] == {"type": "json_schema", "schema": claude_extractor.json_schema()}
    assert request["fallbacks"] == "default" and request["betas"] == ["server-side-fallback-2026-07-01"]
    assert [block["type"] for block in request["messages"][0]["content"]] == ["image", "text"]
    assert "temperature" not in request


def test_claude_schema_is_closed_json_schema():
    schema = claude_extractor.json_schema()
    assert schema["type"] == "object" and schema["additionalProperties"] is False
    assert set(schema["required"]) <= set(schema["properties"])
    assert "OBJECT" not in str(schema) and "STRING" not in str(schema)


def _optional_count(node, defs):
    """Optional properties as Claude counts them: every repetition, a $ref'd definition once."""
    if "$ref" in node:
        return 0
    count = 0
    if node.get("type") == "object":
        count += len(set(node["properties"]) - set(node.get("required", [])))
        count += sum(_optional_count(child, defs) for child in node["properties"].values())
    if node.get("type") == "array":
        count += _optional_count(node["items"], defs)
    return count


def test_claude_schema_stays_within_the_optional_property_limit():
    """Claude rejects a schema with more than 24 optional properties (measured: the plain schema had 25)."""
    schema = claude_extractor.json_schema()
    defs = schema.get("$defs", {})
    total = _optional_count(schema, defs) + sum(_optional_count(item, defs) for item in defs.values())
    assert total <= 24
    for name in ("first_name", "commitment_number", "sender"):
        assert schema["properties"][name]["items"] == {"$ref": "#/$defs/candidate"}


def test_claude_without_key_is_not_configured(claude, monkeypatch):
    page = claude(_FakeClient(_response()))
    monkeypatch.setattr(config, "ANTHROPIC_API_KEYS", [])
    with pytest.raises(MissingApiKeyError):
        claude_extractor.extract_from_image(page, [])


@pytest.mark.parametrize(("error", "reason", "seconds"), [
    (_status_error(anthropic.RateLimitError, 429, {"retry-after": "30"}), "quota", 30),
    (_status_error(anthropic.OverloadedError, 529), "busy", None),
    (_status_error(anthropic.InternalServerError, 500), "busy", None),
])
def test_claude_capacity_errors_rest_it(claude, error, reason, seconds):
    client = _FakeClient(error=error)
    page = claude(client)
    with pytest.raises(ModelsUnavailableError) as info:
        claude_extractor.extract_from_image(page, [])
    assert info.value.reason == reason
    assert info.value.retry_after_seconds == pytest.approx(seconds or config.CLAUDE_BUSY_COOLDOWN_SECONDS, abs=1)
    # While resting, the next page doesn't call the API at all.
    with pytest.raises(ModelsUnavailableError):
        claude_extractor.extract_from_image(page, [])
    assert len(client.requests) == 1


def test_claude_rejected_key_and_bad_request(claude):
    with pytest.raises(MissingApiKeyError):
        claude_extractor.extract_from_image(claude(_FakeClient(error=_status_error(anthropic.AuthenticationError, 401))), [])
    with pytest.raises(ExtractionError) as info:
        claude_extractor.extract_from_image(claude(_FakeClient(error=_status_error(anthropic.BadRequestError, 400))), [])
    assert not isinstance(info.value, (MissingApiKeyError, ModelsUnavailableError))


@pytest.mark.parametrize("response", [_response(stop_reason="refusal"), _response(stop_reason="max_tokens"), _response("not json")])
def test_claude_unusable_answers(claude, response):
    with pytest.raises(ExtractionError) as info:
        claude_extractor.extract_from_image(claude(_FakeClient(response)), [])
    assert "not json" not in str(info.value)  # the answer itself is never put in the error


# ── Several Claude keys ──────────────────────────────────────────────────────


def test_claude_keys_are_read_like_gemini_keys(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_2", "ANTHROPIC_API_KEY_10", "ANTHROPIC_API_KEYS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("ANTHROPIC_API_KEY_10", "c")
    monkeypatch.setenv("ANTHROPIC_API_KEY_2", "b")
    monkeypatch.setenv("ANTHROPIC_API_KEYS", "d, a")
    assert config._api_keys("ANTHROPIC_API_KEY") == ["a", "b", "c", "d"]


@pytest.mark.parametrize("first_key_error", [
    _status_error(anthropic.RateLimitError, 429, {"retry-after": "30"}),
    _status_error(anthropic.AuthenticationError, 401),
])
def test_next_claude_key_takes_over(claude, first_key_error):
    client = _FakeClient(errors=[first_key_error])
    page = claude(client, keys=3)
    assert claude_extractor.extract_from_image(page, [])["_key"] == 2
    assert client.keys == [0, 1]
    # The first key rests: the next page starts at the second one.
    claude_extractor.extract_from_image(page, [])
    assert client.keys == [0, 1, 1]


def test_claude_overload_rests_every_key(claude):
    client = _FakeClient(errors=[_status_error(anthropic.OverloadedError, 529)])
    page = claude(client, keys=3)
    with pytest.raises(ModelsUnavailableError) as info:
        claude_extractor.extract_from_image(page, [])
    assert info.value.reason == "busy" and client.keys == [0]  # another key can't help an overloaded model


def test_every_claude_key_rate_limited(claude):
    limited = [_status_error(anthropic.RateLimitError, 429, {"retry-after": str(s)}) for s in (300, 60, 120)]
    client = _FakeClient(errors=limited)
    with pytest.raises(ModelsUnavailableError) as info:
        claude_extractor.extract_from_image(claude(client, keys=3), [])
    assert info.value.reason == "quota" and 59 <= info.value.retry_after_seconds <= 60  # the first key back
    assert client.keys == [0, 1, 2]


def test_every_claude_key_rejected_counts_as_not_configured(claude):
    client = _FakeClient(errors=[_status_error(anthropic.AuthenticationError, 401)] * 3)
    with pytest.raises(MissingApiKeyError):
        claude_extractor.extract_from_image(claude(client, keys=3), [])
