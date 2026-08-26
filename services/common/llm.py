"""Shared multi-provider LLM client with tiered routing.

All providers are reached through the OpenAI-compatible Chat Completions API, so
a single dependency (`openai`) drives OpenAI, Groq Cloud, and Google Gemini.

Tiers
-----
- ``fast``      cheap/low-latency work (e.g. formalizing a question)
- ``standard``  mid-weight reasoning
- ``advanced``  the strongest model, used for high-stakes reasoning + arbitration

Design principles
-----------------
- **Never leak secrets.** API keys are never logged or returned.
- **Degrade gracefully.** If a tier's provider is missing or fails, we fall back
  to the next configured provider; if none are usable, callers get a typed
  :class:`LLMUnavailable` so they can use deterministic heuristics instead.
- **Configurable.** Every model name, base URL, and the tier→provider mapping can
  be overridden with environment variables, so operators can retune without code
  changes.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# Modules import this lazily; keep the heavy SDK import inside functions so the
# rest of the platform works even if `openai` is absent.


# --------------------------------------------------------------------------- #
# .env loading                                                                 #
# --------------------------------------------------------------------------- #
_ENV_LOADED = False
_ENV_LOCK = threading.Lock()


def load_env() -> None:
    """Load the repo-root ``.env`` into ``os.environ`` exactly once.

    Real environment variables always win (``override=False``) so container /
    CI configuration is never clobbered by a local ``.env``.
    """
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    with _ENV_LOCK:
        if _ENV_LOADED:
            return
        try:
            from dotenv import load_dotenv
        except Exception:  # pragma: no cover - dotenv is a declared dependency
            _ENV_LOADED = True
            return
        # services/common/llm.py -> parents[2] == repo root
        root = Path(__file__).resolve().parents[2]
        env_path = root / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
        else:  # pragma: no cover - fallback for unusual layouts
            load_dotenv(override=False)
        _ENV_LOADED = True


load_env()


# --------------------------------------------------------------------------- #
# Types                                                                        #
# --------------------------------------------------------------------------- #
class LLMTier(str, Enum):
    """Routing tiers, ordered from cheapest to strongest."""

    FAST = "fast"
    STANDARD = "standard"
    ADVANCED = "advanced"


class LLMError(RuntimeError):
    """A provider call failed."""


class LLMUnavailable(LLMError):
    """No provider is configured/usable for the request (caller should fall back)."""


@dataclass(frozen=True)
class LLMResponse:
    """A successful completion, annotated with which provider produced it."""

    text: str
    provider: str
    model: str
    tier: str


@dataclass(frozen=True)
class _Provider:
    name: str
    api_key: str
    base_url: Optional[str]
    model: str

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model)


# Default per-provider endpoints + model names. Every value is overridable via env.
_PROVIDER_DEFAULTS = {
    "openai": {
        "base_url": None,  # SDK default (https://api.openai.com/v1)
        "model": "gpt-4o",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-120b",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        # Primary; GEMINI_FALLBACK_MODELS lists alternates tried on failure.
        "model": "gemini-2.0-flash",
    },
}

# Which provider each tier prefers, and the ordered fallback chain if that
# provider is unavailable. Overridable via LLM_TIER_<TIER> env vars.
_TIER_DEFAULT_PROVIDER = {
    LLMTier.FAST: "gemini",
    LLMTier.STANDARD: "groq",
    LLMTier.ADVANCED: "openai",
}
_TIER_FALLBACK_ORDER = {
    LLMTier.FAST: ["gemini", "groq", "openai"],
    LLMTier.STANDARD: ["groq", "openai", "gemini"],
    LLMTier.ADVANCED: ["openai", "groq", "gemini"],
}


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def is_enabled() -> bool:
    """Global kill switch. Set ``LLM_ENABLED=false`` to force heuristic behavior."""
    return _env("LLM_ENABLED", "true").lower() not in {"false", "0", "no", "off"}


def _build_provider(name: str) -> _Provider:
    defaults = _PROVIDER_DEFAULTS[name]
    prefix = name.upper()
    api_key = _env(f"{prefix}_API_KEY", "") or ""
    base_url = _env(f"{prefix}_BASE_URL", defaults["base_url"])
    model = _env(f"{prefix}_MODEL", defaults["model"]) or defaults["model"]
    return _Provider(name=name, api_key=api_key, base_url=base_url, model=model)


def _providers() -> Dict[str, _Provider]:
    """Resolve all providers from the current environment (not cached, for tests)."""
    return {name: _build_provider(name) for name in _PROVIDER_DEFAULTS}


def available_providers() -> List[str]:
    """Names of providers that have an API key configured (safe to log)."""
    if not is_enabled():
        return []
    return [name for name, provider in _providers().items() if provider.configured]


def _tier_provider_chain(tier: LLMTier) -> List[_Provider]:
    """Ordered, de-duplicated list of configured providers to try for a tier."""
    providers = _providers()
    order: List[str] = []

    preferred = _env(f"LLM_TIER_{tier.value.upper()}")
    if preferred and preferred in providers:
        order.append(preferred)
    order.append(_TIER_DEFAULT_PROVIDER[tier])
    order.extend(_TIER_FALLBACK_ORDER[tier])

    seen: set[str] = set()
    chain: List[_Provider] = []
    for name in order:
        if name in seen or name not in providers:
            continue
        seen.add(name)
        provider = providers[name]
        if provider.configured:
            chain.append(provider)
    return chain


def _timeout() -> float:
    try:
        return float(_env("LLM_TIMEOUT_SECONDS", "20") or 20)
    except ValueError:
        return 20.0


def _max_retries() -> int:
    try:
        return max(0, int(_env("LLM_MAX_RETRIES", "1") or 1))
    except ValueError:
        return 1


def _default_max_tokens() -> int:
    try:
        return int(_env("LLM_MAX_TOKENS", "1024") or 1024)
    except ValueError:
        return 1024


# --------------------------------------------------------------------------- #
# Circuit breaker: skip providers that just failed so one dead endpoint can    #
# never stall the whole pipeline behind repeated timeouts. Cooldown grows      #
# exponentially with consecutive failures so a persistently-dead provider is   #
# retried rarely instead of on every request.                                  #
# --------------------------------------------------------------------------- #
_COOLDOWN_UNTIL: Dict[str, float] = {}
_FAILURE_STREAK: Dict[str, int] = {}
_COOLDOWN_LOCK = threading.Lock()


def _cooldown_base() -> float:
    try:
        return float(_env("LLM_COOLDOWN_SECONDS", "60") or 60)
    except ValueError:
        return 60.0


def _cooldown_max() -> float:
    try:
        return float(_env("LLM_COOLDOWN_MAX_SECONDS", "900") or 900)
    except ValueError:
        return 900.0


def _is_cooling(name: str) -> bool:
    with _COOLDOWN_LOCK:
        return _COOLDOWN_UNTIL.get(name, 0.0) > time.monotonic()


def _mark_failure(name: str) -> None:
    with _COOLDOWN_LOCK:
        streak = _FAILURE_STREAK.get(name, 0) + 1
        _FAILURE_STREAK[name] = streak
        cooldown = min(_cooldown_base() * (2 ** (streak - 1)), _cooldown_max())
        _COOLDOWN_UNTIL[name] = time.monotonic() + cooldown


def _mark_success(name: str) -> None:
    with _COOLDOWN_LOCK:
        _FAILURE_STREAK.pop(name, None)
        _COOLDOWN_UNTIL.pop(name, None)


def reset_breaker() -> None:
    """Clear all breaker state (used by tests)."""
    with _COOLDOWN_LOCK:
        _COOLDOWN_UNTIL.clear()
        _FAILURE_STREAK.clear()


def _order_by_health(chain: List["_Provider"]) -> List["_Provider"]:
    """Try healthy providers first; keep cooling ones only as a last resort."""
    healthy = [p for p in chain if not _is_cooling(p.name)]
    cooling = [p for p in chain if _is_cooling(p.name)]
    return healthy + cooling


# --------------------------------------------------------------------------- #
# Client construction (isolated so tests can monkeypatch)                      #
# --------------------------------------------------------------------------- #
def _make_client(provider: _Provider, *, is_async: bool, timeout: Optional[float] = None, retries: Optional[int] = None):
    from openai import AsyncOpenAI, OpenAI

    kwargs: Dict[str, Any] = {
        "api_key": provider.api_key,
        "timeout": timeout if timeout is not None else _timeout(),
        "max_retries": retries if retries is not None else _max_retries(),
    }
    if provider.base_url:
        kwargs["base_url"] = provider.base_url
    return AsyncOpenAI(**kwargs) if is_async else OpenAI(**kwargs)


def _is_json_param_error(exc: Exception) -> bool:
    """True if the error looks like the provider rejecting json response_format."""
    text = str(exc).lower()
    if "response_format" in text:
        return True
    return "json" in text and ("not" in text or "unsupported" in text or "invalid" in text)


def _model_candidates(provider: _Provider) -> List[str]:
    """Primary model plus optional per-provider fallbacks (esp. Gemini)."""
    models: List[str] = [provider.model]
    raw = ""
    if provider.name == "gemini":
        raw = (
            _env(
                "GEMINI_FALLBACK_MODELS",
                "gemini-2.0-flash-lite,gemini-1.5-flash,gemini-1.5-pro,gemini-2.5-flash",
            )
            or ""
        )
    else:
        raw = _env(f"{provider.name.upper()}_FALLBACK_MODELS", "") or ""
    for part in raw.split(","):
        name = part.strip()
        if name and name not in models:
            models.append(name)
    return models


def _call_sync(provider: _Provider, messages, temperature, max_tokens, json_mode, *, timeout=None, retries=None) -> str:
    client = _make_client(provider, is_async=False, timeout=timeout, retries=retries)
    last_exc: Optional[Exception] = None
    for model in _model_candidates(provider):
        params: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            params["response_format"] = {"type": "json_object"}
        try:
            try:
                resp = client.chat.completions.create(**params)
            except Exception as exc:  # noqa: BLE001
                if json_mode and _is_json_param_error(exc):
                    params.pop("response_format", None)
                    resp = client.chat.completions.create(**params)
                else:
                    raise
            text = (resp.choices[0].message.content or "").strip()
            if text:
                if model != provider.model:
                    logger.info("Provider '%s' succeeded with alternate model '%s'", provider.name, model)
                return text
            last_exc = LLMError(f"{provider.name}/{model} returned empty content")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning(
                "Provider '%s' model '%s' failed (%s); trying next model",
                provider.name,
                model,
                type(exc).__name__,
            )
    if last_exc:
        raise last_exc
    raise LLMError(f"{provider.name} returned empty content")


async def _call_async(provider: _Provider, messages, temperature, max_tokens, json_mode) -> str:
    client = _make_client(provider, is_async=True)
    last_exc: Optional[Exception] = None
    for model in _model_candidates(provider):
        params: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            params["response_format"] = {"type": "json_object"}
        try:
            try:
                resp = await client.chat.completions.create(**params)
            except Exception as exc:  # noqa: BLE001
                if json_mode and _is_json_param_error(exc):
                    params.pop("response_format", None)
                    resp = await client.chat.completions.create(**params)
                else:
                    raise
            text = (resp.choices[0].message.content or "").strip()
            if text:
                if model != provider.model:
                    logger.info("Provider '%s' succeeded with alternate model '%s'", provider.name, model)
                return text
            last_exc = LLMError(f"{provider.name}/{model} returned empty content")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning(
                "Provider '%s' model '%s' failed (%s); trying next model",
                provider.name,
                model,
                type(exc).__name__,
            )
    if last_exc:
        raise last_exc
    raise LLMError(f"{provider.name} returned empty content")


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #
def chat(
    messages: Sequence[Dict[str, str]],
    *,
    tier: LLMTier = LLMTier.STANDARD,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    json_mode: bool = False,
) -> LLMResponse:
    """Synchronous chat completion with tier routing + provider fallback.

    Raises :class:`LLMUnavailable` if no provider is configured, or
    :class:`LLMError` if every configured provider failed.
    """
    if not is_enabled():
        raise LLMUnavailable("LLM disabled via LLM_ENABLED")
    chain = _tier_provider_chain(tier)
    if not chain:
        raise LLMUnavailable(f"No provider configured for tier '{tier.value}'")

    max_tokens = max_tokens or _default_max_tokens()
    last_error: Optional[Exception] = None
    for provider in _order_by_health(chain):
        try:
            text = _call_sync(provider, list(messages), temperature, max_tokens, json_mode)
            if text:
                _mark_success(provider.name)
                return LLMResponse(text=text, provider=provider.name, model=provider.model, tier=tier.value)
            last_error = LLMError(f"{provider.name} returned empty content")
            _mark_failure(provider.name)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            _mark_failure(provider.name)
            logger.warning("LLM provider '%s' failed (%s); trying fallback", provider.name, type(exc).__name__)
    raise LLMError(f"All providers failed for tier '{tier.value}': {last_error}")


async def achat(
    messages: Sequence[Dict[str, str]],
    *,
    tier: LLMTier = LLMTier.STANDARD,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    json_mode: bool = False,
) -> LLMResponse:
    """Async counterpart to :func:`chat`."""
    if not is_enabled():
        raise LLMUnavailable("LLM disabled via LLM_ENABLED")
    chain = _tier_provider_chain(tier)
    if not chain:
        raise LLMUnavailable(f"No provider configured for tier '{tier.value}'")

    max_tokens = max_tokens or _default_max_tokens()
    last_error: Optional[Exception] = None
    for provider in _order_by_health(chain):
        try:
            text = await _call_async(provider, list(messages), temperature, max_tokens, json_mode)
            if text:
                _mark_success(provider.name)
                return LLMResponse(text=text, provider=provider.name, model=provider.model, tier=tier.value)
            last_error = LLMError(f"{provider.name} returned empty content")
            _mark_failure(provider.name)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            _mark_failure(provider.name)
            logger.warning("LLM provider '%s' failed (%s); trying fallback", provider.name, type(exc).__name__)
    raise LLMError(f"All providers failed for tier '{tier.value}': {last_error}")


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Dict[str, Any]:
    """Best-effort JSON extraction from a model response.

    Handles bare JSON, ```json fenced blocks, and leading/trailing prose.
    Raises :class:`LLMError` if nothing parseable is found.
    """
    candidates: List[str] = []
    stripped = text.strip()
    candidates.append(stripped)

    fence = _JSON_FENCE_RE.search(text)
    if fence:
        candidates.insert(0, fence.group(1).strip())

    # Fall back to the outermost {...} span.
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(stripped[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            continue
    raise LLMError("Model response did not contain valid JSON")


def complete_json(
    *,
    system: str,
    user: str,
    tier: LLMTier = LLMTier.STANDARD,
    temperature: float = 0.1,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Request a JSON object and parse it robustly. Synchronous."""
    response = chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        tier=tier,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=True,
    )
    return extract_json(response.text)


async def acomplete_json(
    *,
    system: str,
    user: str,
    tier: LLMTier = LLMTier.STANDARD,
    temperature: float = 0.1,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Async counterpart to :func:`complete_json`."""
    response = await achat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        tier=tier,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=True,
    )
    return extract_json(response.text)


async def ensemble(
    messages: Sequence[Dict[str, str]],
    *,
    providers: Optional[Sequence[str]] = None,
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    json_mode: bool = False,
) -> List[LLMResponse]:
    """Fan a single prompt out to multiple providers concurrently ("best of N").

    Returns every successful response; failed providers are dropped (and logged
    without secrets). Returns an empty list if nothing is configured/succeeds.
    Callers arbitrate/synthesize across the returned candidates.
    """
    import asyncio

    if not is_enabled():
        return []
    all_providers = _providers()
    names = list(providers) if providers else [n for n, p in all_providers.items() if p.configured]
    targets = [all_providers[n] for n in names if n in all_providers and all_providers[n].configured]
    if not targets:
        return []

    max_tokens = max_tokens or _default_max_tokens()

    async def _run(provider: _Provider) -> Optional[LLMResponse]:
        try:
            text = await _call_async(provider, list(messages), temperature, max_tokens, json_mode)
            if not text:
                _mark_failure(provider.name)
                return None
            _mark_success(provider.name)
            return LLMResponse(text=text, provider=provider.name, model=provider.model, tier="ensemble")
        except Exception as exc:  # noqa: BLE001
            _mark_failure(provider.name)
            logger.warning("Ensemble provider '%s' failed (%s)", provider.name, type(exc).__name__)
            return None

    results = await asyncio.gather(*[_run(p) for p in targets])
    return [r for r in results if r is not None]


def preflight(probe_timeout: float = 6.0) -> Dict[str, str]:
    """Quickly health-check each configured provider and warm the breaker.

    Called at service startup so the first *user* request never eats a long
    timeout for a dead provider. Uses a short timeout and no retries. Returns a
    ``{provider: status}`` map suitable for logging (no secrets).
    """
    status: Dict[str, str] = {}
    if not is_enabled():
        return {"_": "disabled"}
    for name, provider in _providers().items():
        if not provider.configured:
            status[name] = "not_configured"
            continue
        try:
            # Reachability check only: any non-exception response means the
            # endpoint + credentials work. Content may be empty for reasoning
            # models given a tiny budget, which is not a failure.
            _call_sync(
                provider,
                [{"role": "user", "content": "ping"}],
                0.0,
                64,
                False,
                timeout=probe_timeout,
                retries=0,
            )
            _mark_success(name)
            status[name] = "ok"
        except Exception as exc:  # noqa: BLE001
            _mark_failure(name)
            status[name] = f"unavailable ({type(exc).__name__})"
    return status
