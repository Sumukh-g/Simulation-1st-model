"""Tests for on-demand pack bootstrap heuristics."""
from services.orchestrator.activities.pack_creation import (
    bootstrap_create_pack,
    bootstrap_no_pack,
    _heuristic_create,
    _heuristic_no_pack,
)


def test_heuristic_create_pollution_differs_from_finance():
    air = _heuristic_create("reduce 5% pollution in Delhi in 1 year")
    fin = _heuristic_create("maximize portfolio sharpe while limiting drawdown")
    assert air["domain"] != fin["domain"]
    assert "pollution" in air["assistant_message"].lower() or "air" in air["domain"]
    assert "finance" in fin["domain"] or "portfolio" in fin["domain"]
    assert air["draft_pack"]["name"] != fin["draft_pack"]["name"]
    assert len(air["candidate_methods"]) >= 2


def test_heuristic_no_pack_builds_ephemeral(monkeypatch):
    data = _heuristic_no_pack("optimize warehouse layout for throughput")
    assert data["ephemeral_pack"]["fidelity"] == "ILLUSTRATIVE"
    assert "ephemeral" in data["assistant_message"].lower() or "illustrative" in data["assistant_message"].lower()


def test_bootstrap_falls_back_when_llm_disabled(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "false")
    # Force reload of enable check via is_enabled reading env each time — llm.is_enabled reads live.
    from services.common import llm

    monkeypatch.setattr(llm, "is_enabled", lambda: False)

    out = bootstrap_create_pack("cut CO2 from city buses by 10%")
    assert out["candidate_methods"]
    assert out["assistant_message"]
    assert out.get("generated_by") == "heuristic"

    out2 = bootstrap_no_pack("design a one-off pricing experiment")
    assert out2["ephemeral_pack"]
    assert out2["assistant_message"]
