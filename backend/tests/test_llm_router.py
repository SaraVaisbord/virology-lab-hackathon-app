"""Failover between LLM providers (integrations/llm/router.py) and the Claude provider (integrations/llm/claude.py).
No network: providers and the Anthropic client are replaced with fakes."""

from __future__ import annotations

import types

from pathlib import Path

import anthropic
import httpx2
import pytest

import config
from integrations.llm.claude import ClaudeProvider, ClaudeSettings, json_schema
from integrations.llm.errors import ExtractionError, MissingApiKeyError, ModelsUnavailableError
from integrations.llm.page_image import PageImageSettings
from integrations.llm.prompt import ExtractionPrompt
from integrations.llm.router import LlmRouter

_ANSWER = {"all_numbers": [], "commitment_number": [{"value": "47381"}]}


class _provider:
    def __init__(self, answer=None, error=None, calls=None, name=""):
        self.answer, self.error, self.calls, self.name = answer, error, calls, name

    def extract_from_image(self, image_path, known_senders=None):
        if self.calls is not None:
            self.calls.append(self.name)
        if self.error is not None:
            raise self.error
        return dict(self.answer or _ANSWER)


class _Providers:
    """providers(gemini=..., claude=...) installs fake providers, in that order; then use .extract_from_image."""

    router: LlmRouter

    def __call__(self, **fakes):
        self.router = LlmRouter(fakes, list(fakes))

    def extract_from_image(self, *args, **kwargs):
        return self.router.extract_from_image(*args, **kwargs)


@pytest.fixture
def providers():
    return _Providers()


# ── Failover ─────────────────────────────────────────────────────────────────


def test_first_provider_answers(providers):
    calls = []
    providers(gemini=_provider(calls=calls, name="gemini"), claude=_provider(calls=calls, name="claude"))
    result = providers.extract_from_image("page.png", [])
    assert result["_provider"] == "gemini" and calls == ["gemini"]


@pytest.mark.parametrize("gemini_error", [
    ModelsUnavailableError("quota", 300, "quota"),
    MissingApiKeyError("no key"),
    ExtractionError("invalid JSON"),
])
def test_next_provider_takes_over(providers, gemini_error):
    providers(gemini=_provider(error=gemini_error), claude=_provider())
    assert providers.extract_from_image("page.png", [])["_provider"] == "claude"


def test_all_resting_pauses_with_the_earliest_return(providers):
    providers(gemini=_provider(error=ModelsUnavailableError("q", 300, "quota")),
              claude=_provider(error=ModelsUnavailableError("b", 90, "busy")))
    with pytest.raises(ModelsUnavailableError) as info:
        providers.extract_from_image("page.png", [])
    assert (info.value.retry_after_seconds, info.value.reason) == (90, "quota")


def test_resting_plus_unconfigured_still_pauses(providers):
    providers(gemini=_provider(error=ModelsUnavailableError("q", 120, "quota")), claude=_provider(error=MissingApiKeyError("x")))
    with pytest.raises(ModelsUnavailableError):
        providers.extract_from_image("page.png", [])


def test_a_bad_answer_fails_the_page_instead_of_requeueing(providers):
    providers(gemini=_provider(error=ModelsUnavailableError("q", 120, "quota")), claude=_provider(error=ExtractionError("refused")))
    with pytest.raises(ExtractionError) as info:
        providers.extract_from_image("page.png", [])
    assert not isinstance(info.value, ModelsUnavailableError) and "claude" in str(info.value)


def test_nothing_configured(providers):
    providers(gemini=_provider(error=MissingApiKeyError("a")), claude=_provider(error=MissingApiKeyError("b")))
    with pytest.raises(MissingApiKeyError):
        providers.extract_from_image("page.png", [])


def test_one_provider_can_be_forced(providers):
    providers(gemini=_provider(), claude=_provider())
    assert providers.extract_from_image("page.png", [], providers=["claude"])["_provider"] == "claude"
    with pytest.raises(ValueError):
        providers.extract_from_image("page.png", [], providers=["gpt-9"])


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


CLAUDE_SETTINGS = ClaudeSettings(api_keys=[], model="claude-opus-5-5", effort="medium", max_tokens=16000, timeout_seconds=180,
                                 quota_default_backoff_seconds=60, busy_cooldown_seconds=90, invalid_key_cooldown_seconds=3600)
PROMPT = ExtractionPrompt(Path(__file__).resolve().parents[1] / "prompts" / "extraction_prompt.md")


class _Claude:
    """claude(client, keys=1) → a fresh provider (keys configured, none resting) that sends through `client`;
    claude.page is a page image. The fake client records, per request, which key index sent it (`client.keys`)."""

    def __init__(self, page):
        self.page = page
        self.provider: ClaudeProvider | None = None

    def __call__(self, client, keys=1):
        client.keys = []

        def client_for(key_index):
            return _KeyClient(client, key_index)
        settings = ClaudeSettings(**{**CLAUDE_SETTINGS.__dict__, "api_keys": [f"test-key-{i}" for i in range(keys)]})
        self.provider = ClaudeProvider(settings, PROMPT, PageImageSettings(max_side_px=1600, jpeg_quality=80), new_client=client_for)
        return self.page

    def extract_from_image(self, *args, **kwargs):
        return self.provider.extract_from_image(*args, **kwargs)


class _KeyClient:
    """The client of one key: every request goes to the shared fake client, noting the key."""

    def __init__(self, client, key_index):
        def create(**kwargs):
            client.keys.append(key_index)
            return client.beta.messages.create(**kwargs)
        self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))


@pytest.fixture
def claude(tmp_path):
    from PIL import Image

    page = tmp_path / "page.png"
    Image.new("RGB", (40, 30), "white").save(page)
    return _Claude(page)


def test_claude_request_and_answer(claude):
    client = _FakeClient(_response('{"all_numbers": [], "first_name": [{"value": "x"}]}'))
    result = claude.extract_from_image(claude(client), ["כללית"])
    assert result["first_name"] == [{"value": "x"}] and result["_model"] == "claude-opus-5-5"
    assert result["_usage"] == {"input_tokens": 1800, "output_tokens": 420}
    request = client.requests[0]
    assert request["model"] == CLAUDE_SETTINGS.model
    assert request["output_config"]["effort"] == CLAUDE_SETTINGS.effort
    assert request["output_config"]["format"] == {"type": "json_schema", "schema": json_schema()}
    assert request["fallbacks"] == "default" and request["betas"] == ["server-side-fallback-2026-07-01"]
    assert [block["type"] for block in request["messages"][0]["content"]] == ["image", "text"]
    assert "temperature" not in request


def test_claude_schema_is_closed_json_schema():
    schema = json_schema()
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
    schema = json_schema()
    defs = schema.get("$defs", {})
    total = _optional_count(schema, defs) + sum(_optional_count(item, defs) for item in defs.values())
    assert total <= 24
    for name in ("first_name", "commitment_number", "sender"):
        assert schema["properties"][name]["items"] == {"$ref": "#/$defs/candidate"}


def test_claude_without_key_is_not_configured(claude):
    page = claude(_FakeClient(_response()), keys=0)
    with pytest.raises(MissingApiKeyError):
        claude.extract_from_image(page, [])


@pytest.mark.parametrize(("error", "reason", "seconds"), [
    (_status_error(anthropic.RateLimitError, 429, {"retry-after": "30"}), "quota", 30),
    (_status_error(anthropic.OverloadedError, 529), "busy", None),
    (_status_error(anthropic.InternalServerError, 500), "busy", None),
])
def test_claude_capacity_errors_rest_it(claude, error, reason, seconds):
    client = _FakeClient(error=error)
    page = claude(client)
    with pytest.raises(ModelsUnavailableError) as info:
        claude.extract_from_image(page, [])
    assert info.value.reason == reason
    assert info.value.retry_after_seconds == pytest.approx(seconds or CLAUDE_SETTINGS.busy_cooldown_seconds, abs=1)
    # While resting, the next page doesn't call the API at all.
    with pytest.raises(ModelsUnavailableError):
        claude.extract_from_image(page, [])
    assert len(client.requests) == 1


def test_claude_rejected_key_and_bad_request(claude):
    with pytest.raises(MissingApiKeyError):
        claude.extract_from_image(claude(_FakeClient(error=_status_error(anthropic.AuthenticationError, 401))), [])
    with pytest.raises(ExtractionError) as info:
        claude.extract_from_image(claude(_FakeClient(error=_status_error(anthropic.BadRequestError, 400))), [])
    assert not isinstance(info.value, (MissingApiKeyError, ModelsUnavailableError))


@pytest.mark.parametrize("response", [_response(stop_reason="refusal"), _response(stop_reason="max_tokens"), _response("not json")])
def test_claude_unusable_answers(claude, response):
    with pytest.raises(ExtractionError) as info:
        claude.extract_from_image(claude(_FakeClient(response)), [])
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
    assert claude.extract_from_image(page, [])["_key"] == 2
    assert client.keys == [0, 1]
    # The first key rests: the next page starts at the second one.
    claude.extract_from_image(page, [])
    assert client.keys == [0, 1, 1]


def test_claude_overload_rests_every_key(claude):
    client = _FakeClient(errors=[_status_error(anthropic.OverloadedError, 529)])
    page = claude(client, keys=3)
    with pytest.raises(ModelsUnavailableError) as info:
        claude.extract_from_image(page, [])
    assert info.value.reason == "busy" and client.keys == [0]  # another key can't help an overloaded model


def test_every_claude_key_rate_limited(claude):
    limited = [_status_error(anthropic.RateLimitError, 429, {"retry-after": str(s)}) for s in (300, 60, 120)]
    client = _FakeClient(errors=limited)
    with pytest.raises(ModelsUnavailableError) as info:
        claude.extract_from_image(claude(client, keys=3), [])
    assert info.value.reason == "quota" and 59 <= info.value.retry_after_seconds <= 60  # the first key back
    assert client.keys == [0, 1, 2]


def test_every_claude_key_rejected_counts_as_not_configured(claude):
    client = _FakeClient(errors=[_status_error(anthropic.AuthenticationError, 401)] * 3)
    with pytest.raises(MissingApiKeyError):
        claude.extract_from_image(claude(client, keys=3), [])
