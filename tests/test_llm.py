"""Tests for the shared multi-provider LLM client (services.common.llm).

All provider calls are mocked, so these run offline and deterministically.
"""
import pytest

from services.common import llm


# --------------------------------------------------------------------------- #
# Fakes                                                                        #
# --------------------------------------------------------------------------- #
class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class _Completions:
    def __init__(self, handler):
        self._handler = handler

    def create(self, **kwargs):
        return self._handler(kwargs)


class _Chat:
    def __init__(self, handler):
        self.completions = _Completions(handler)


class _FakeClient:
    def __init__(self, handler):
        self.chat = _Chat(handler)


def _install(monkeypatch, handlers):
    """Route _make_client to per-provider handlers keyed by base model name.

    ``handlers`` maps provider name -> callable(params)->_Resp (or raises).
    """
    def fake_make_client(provider, *, is_async, timeout=None, retries=None):
        handler = handlers[provider.name]
        return _FakeClient(handler)

    monkeypatch.setattr(llm, "_make_client", fake_make_client)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Give every test a clean breaker and only Groq configured by default."""
    llm.reset_breaker()
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_TIER_FAST", raising=False)
    monkeypatch.delenv("LLM_TIER_STANDARD", raising=False)
    monkeypatch.delenv("LLM_TIER_ADVANCED", raising=False)
    yield
    llm.reset_breaker()


# --------------------------------------------------------------------------- #
# Config / availability                                                        #
# --------------------------------------------------------------------------- #
def test_available_providers_reflects_env(monkeypatch):
    assert llm.available_providers() == ["groq"]
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    assert set(llm.available_providers()) == {"openai", "groq"}


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "false")
    assert llm.is_enabled() is False
    assert llm.available_providers() == []
    with pytest.raises(llm.LLMUnavailable):
        llm.chat([{"role": "user", "content": "hi"}], tier=llm.LLMTier.FAST)


def test_no_provider_raises_unavailable(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(llm.LLMUnavailable):
        llm.chat([{"role": "user", "content": "hi"}])


# --------------------------------------------------------------------------- #
# Routing + fallback                                                           #
# --------------------------------------------------------------------------- #
def test_fast_tier_falls_back_to_groq(monkeypatch):
    # Fast prefers gemini; only groq is configured, so it must be used.
    _install(monkeypatch, {"groq": lambda p: _Resp("hello from groq")})
    resp = llm.chat([{"role": "user", "content": "hi"}], tier=llm.LLMTier.FAST)
    assert resp.provider == "groq"
    assert resp.text == "hello from groq"


def test_fallback_when_primary_errors(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")

    def openai_fail(params):
        raise RuntimeError("429 quota")

    _install(
        monkeypatch,
        {
            "openai": openai_fail,
            "groq": lambda p: _Resp("groq answer"),
        },
    )
    # advanced prefers openai (fails) -> should fall back to groq
    resp = llm.chat([{"role": "user", "content": "hi"}], tier=llm.LLMTier.ADVANCED)
    assert resp.provider == "groq"


def test_all_providers_fail_raises_llmerror(monkeypatch):
    def boom(params):
        raise RuntimeError("network down")

    _install(monkeypatch, {"groq": boom})
    with pytest.raises(llm.LLMError):
        llm.chat([{"role": "user", "content": "hi"}])


# --------------------------------------------------------------------------- #
# Circuit breaker                                                              #
# --------------------------------------------------------------------------- #
def test_breaker_skips_failed_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    calls = {"openai": 0, "groq": 0}

    def openai_handler(params):
        calls["openai"] += 1
        raise RuntimeError("timeout")

    def groq_handler(params):
        calls["groq"] += 1
        return _Resp("ok")

    _install(monkeypatch, {"openai": openai_handler, "groq": groq_handler})

    # First advanced call: openai fails, groq succeeds -> breaker opens for openai
    llm.chat([{"role": "user", "content": "1"}], tier=llm.LLMTier.ADVANCED)
    # Second advanced call: openai should be skipped (cooling), only groq called
    llm.chat([{"role": "user", "content": "2"}], tier=llm.LLMTier.ADVANCED)

    assert calls["openai"] == 1  # not retried while cooling
    assert calls["groq"] == 2


# --------------------------------------------------------------------------- #
# JSON handling                                                                #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text,expected_key",
    [
        ('{"a": 1}', "a"),
        ('```json\n{"b": 2}\n```', "b"),
        ('Here you go:\n```\n{"c": 3}\n```\nThanks', "c"),
        ('Sure! {"d": 4} done', "d"),
    ],
)
def test_extract_json_variants(text, expected_key):
    parsed = llm.extract_json(text)
    assert expected_key in parsed


def test_extract_json_invalid_raises():
    with pytest.raises(llm.LLMError):
        llm.extract_json("no json here at all")


def test_complete_json_roundtrip(monkeypatch):
    _install(monkeypatch, {"groq": lambda p: _Resp('{"metrics": ["x"], "ok": true}')})
    result = llm.complete_json(system="s", user="u", tier=llm.LLMTier.FAST)
    assert result["ok"] is True
    assert result["metrics"] == ["x"]


def test_json_mode_retries_without_response_format(monkeypatch):
    """If a provider rejects response_format, we retry once without it."""
    state = {"n": 0}

    def handler(params):
        state["n"] += 1
        if "response_format" in params:
            raise RuntimeError("response_format is not supported by this model")
        return _Resp('{"ok": true}')

    _install(monkeypatch, {"groq": handler})
    result = llm.complete_json(system="s", user="u", tier=llm.LLMTier.STANDARD)
    assert result["ok"] is True
    assert state["n"] == 2  # first with json mode (fails), second without


# --------------------------------------------------------------------------- #
# Empty content is treated as a failure                                        #
# --------------------------------------------------------------------------- #
def test_empty_content_is_failure(monkeypatch):
    _install(monkeypatch, {"groq": lambda p: _Resp("")})
    with pytest.raises(llm.LLMError):
        llm.chat([{"role": "user", "content": "hi"}])
