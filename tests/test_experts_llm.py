"""Tests for LLM-backed MoE experts (mocked LLM)."""
import pytest

from services.common import llm
from services.api.moe.experts import CauseModeler, Critic, RedTeam, ExpertInput


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    llm.reset_breaker()
    yield
    llm.reset_breaker()


def _mock_acomplete(monkeypatch, payload):
    async def fake(**kwargs):
        return payload

    monkeypatch.setattr(llm, "acomplete_json", fake)


@pytest.mark.asyncio
async def test_cause_modeler_uses_llm(monkeypatch):
    _mock_acomplete(
        monkeypatch,
        {
            "causal_graph": {"weight_spy": ["sharpe_ratio"], "leverage": ["max_drawdown"]},
            "key_drivers": ["weight_spy", "leverage"],
            "uncertainties": {"leverage": 0.4},
        },
    )
    out = await CauseModeler().execute(
        ExpertInput(task="maximize returns", context={"stakes": 0.5}, constraints=["risk_level"])
    )
    assert out.payload["key_drivers"] == ["weight_spy", "leverage"]
    assert "weight_spy" in out.payload["causal_graph"]
    assert out.confidence == pytest.approx(0.7)
    assert out.requires_escalation is False


@pytest.mark.asyncio
async def test_cause_modeler_ensemble_merges(monkeypatch):
    responses = [
        llm.LLMResponse(text='{"causal_graph": {"a": ["m1"]}, "key_drivers": ["a"], "uncertainties": {"a": 0.2}}', provider="groq", model="x", tier="ensemble"),
        llm.LLMResponse(text='{"causal_graph": {"b": ["m2"]}, "key_drivers": ["b"], "uncertainties": {"a": 0.4}}', provider="openai", model="y", tier="ensemble"),
    ]

    async def fake_ensemble(messages, **kwargs):
        return responses

    monkeypatch.setattr(llm, "ensemble", fake_ensemble)

    out = await CauseModeler().execute(
        ExpertInput(task="reduce pollution", context={"use_ensemble": True, "stakes": 0.9})
    )
    # Union of drivers from both providers, averaged uncertainty for 'a'.
    assert set(out.payload["key_drivers"]) == {"a", "b"}
    assert out.payload["uncertainties"]["a"] == pytest.approx(0.3)
    assert out.confidence > 0.7  # more providers -> higher confidence


@pytest.mark.asyncio
async def test_cause_modeler_fallback_without_llm(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "false")
    out = await CauseModeler().execute(ExpertInput(task="x", context={}))
    assert out.payload["key_drivers"] == []
    assert out.requires_escalation is True
    assert out.confidence < 0.5


@pytest.mark.asyncio
async def test_critic_uses_llm(monkeypatch):
    _mock_acomplete(
        monkeypatch,
        {
            "issues": [{"description": "Overfits to seed", "severity": "high"}],
            "recommendations": ["Add more replicates"],
            "overall_quality": 0.6,
        },
    )
    out = await Critic().execute(ExpertInput(task="review plan", context={}))
    assert out.payload["overall_quality"] == pytest.approx(0.6)
    assert "Overfits to seed" in out.risks


@pytest.mark.asyncio
async def test_red_team_uses_llm(monkeypatch):
    _mock_acomplete(
        monkeypatch,
        {
            "attack_vectors": [{"description": "Gaming the metric"}],
            "failure_modes": [{"description": "Regime shift", "likelihood": "high"}],
            "mitigations": ["Stress test across regimes"],
        },
    )
    out = await RedTeam().execute(ExpertInput(task="attack plan", context={}))
    assert out.payload["mitigations"] == ["Stress test across regimes"]
    assert "Regime shift" in out.risks
