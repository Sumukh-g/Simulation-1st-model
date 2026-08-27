"""Tests for ephemeral domain pack execution."""
import pytest

from compute.domain_packs.ephemeral_pack import EphemeralDomainPack, sanitize_pack_schemas
from compute.domain_packs.sdk import Fidelity
from services.orchestrator.activities.pack_creation import materialize_for_execution, _heuristic_no_pack


def test_ephemeral_simulate_produces_metrics():
    spec = {
        "domain_pack": "ephemeral-delhi",
        "domain_pack_version": "0.1.0-illustrative",
        "ephemeral": True,
        "ephemeral_pack_spec": {
            "name": "ephemeral-delhi",
            "metrics": [
                {"name": "pollution_index", "direction": "minimize"},
                {"name": "cost", "direction": "minimize"},
            ],
            "action_schema": [
                {"name": "transit_shift", "type": "number"},
                {"name": "industry_abatement", "type": "number"},
            ],
            "state_schema": [{"name": "baseline", "type": "number"}],
        },
        "initial_state": {"baseline": 100.0, "pollution_index_baseline": 100.0},
    }
    pack = EphemeralDomainPack.from_run_spec(spec)
    state = pack.validate_state(spec["initial_state"])
    actions = pack.validate_actions({"transit_shift": 80, "industry_abatement": 60})
    outcome = pack.simulate(state, actions, Fidelity.MID, 42, "s1", "r1")
    scored = pack.score(outcome)
    names = {m.name for m in scored.metrics}
    assert "pollution_index" in names
    assert scored.metrics[0].value > 0


def test_materialize_no_pack_sets_executable_fields():
    bootstrap = _heuristic_no_pack("reduce pollution in Delhi by 5%")
    fields = materialize_for_execution(bootstrap=bootstrap, mode="no_pack", prompt="reduce pollution in Delhi")
    assert fields["ephemeral"] is True
    assert fields["domain_pack"].startswith("ephemeral-")
    assert fields["action_ranges"]
    assert fields["initial_state"]
    assert any(s["stage"] == "formalize" for s in fields["stages"])


def test_sanitize_drops_string_action_fields():
    pack = sanitize_pack_schemas({
        "name": "test",
        "action_schema": [
            {"name": "measure_id", "type": "string"},
            {"name": "intensity", "type": "number"},
        ],
        "metrics": [{"name": "pollution_index", "direction": "minimize"}],
    })
    names = [a["name"] for a in pack["action_schema"]]
    assert "measure_id" not in names
    assert "intensity" in names


def test_pdf_builder_produces_bytes():
    from services.report.pdf_builder import build_run_report_pdf

    data = {
        "title": "Delhi pollution",
        "simulation_mode": "no_pack",
        "status": "completed",
        "domain_pack": "ephemeral-delhi",
        "created_at": "2026-01-01T00:00:00",
        "narrative": {"text": "Summary here."},
        "summary": {"completed": 10, "best_score": 1.2},
        "counters": {"scenarios_simulated": 10, "scenarios_proposed": 15},
        "candidates": [],
    }
    pdf = build_run_report_pdf(data)
    assert pdf[:4] == b"%PDF"
    assert isinstance(pdf, bytes)


def test_pdf_returns_bytes_not_bytearray():
    from services.report.pdf_builder import build_run_report_pdf

    data = {"title": "Test", "status": "completed", "simulation_mode": "no_pack"}
    pdf = build_run_report_pdf(data)
    assert type(pdf) is bytes


def test_materialize_create_pack_auto_selects_method():
    from services.orchestrator.activities.pack_creation import _heuristic_create

    bootstrap = _heuristic_create("optimize warehouse throughput")
    fields = materialize_for_execution(bootstrap=bootstrap, mode="create_pack", prompt="optimize warehouse throughput")
    assert fields.get("selected_method_id")
    assert fields["domain_pack"].startswith("ephemeral-")
