"""Tests for MoE Committee arbitration and escalation."""
from services.api.moe import ArbitrationEngine, EscalationPolicy, RouterPolicy, TaskStage
from services.api.moe.experts import ExpertContract


def make_contract(expert_id, payload, confidence=0.9, assumptions=None):
    return ExpertContract(
        expert_id=expert_id,
        output_type="test",
        payload=payload,
        confidence=confidence,
        assumptions=assumptions or [],
        evidence_refs=[],
        risks=[],
        requires_escalation=False,
    )


def test_router_policy_stage_mapping():
    policy = RouterPolicy()
    decision = policy.route(
        task="Generate scenarios", stage=TaskStage.SCENARIO_GENERATION, stakes=0.4
    )
    assert "scenario_generator" in decision.experts
    assert decision.k_candidates >= 5


def test_arbitration_consensus_assumptions():
    engine = ArbitrationEngine(consensus_threshold=0.6)
    outputs = [
        make_contract("e1", payload={}, assumptions=["A", "B"]),
        make_contract("e2", payload={}, assumptions=["A"]),
        make_contract("e3", payload={}, assumptions=["C"]),
    ]
    result = engine.arbitrate(outputs, k_candidates=2)
    assert "A" in result.assumptions
    assert "B" not in result.assumptions


def test_arbitration_union_scenarios_and_scores():
    engine = ArbitrationEngine()
    outputs = [
        make_contract(
            "e1",
            payload={
                "scenario_ideas": [
                    {"scenario_id": "s1", "summary": "Idea 1", "parameters": {}, "priority": 0.9}
                ]
            },
            confidence=0.9,
        ),
        make_contract(
            "e2",
            payload={
                "scenario_ideas": [
                    {"scenario_id": "s2", "summary": "Idea 2", "parameters": {}, "priority": 0.6}
                ]
            },
            confidence=0.7,
        ),
    ]
    result = engine.arbitrate(outputs, k_candidates=2)
    ids = {s["scenario_id"] for s in result.scenario_candidates}
    assert ids == {"s1", "s2"}
    assert result.score_by_scenario["s1"] > result.score_by_scenario["s2"]


def test_tournament_selection():
    engine = ArbitrationEngine()
    outputs = [
        make_contract(
            "e1",
            payload={
                "scenario_ideas": [
                    {"scenario_id": "s1", "summary": "Idea 1", "parameters": {}, "priority": 0.5},
                    {"scenario_id": "s2", "summary": "Idea 2", "parameters": {}, "priority": 0.5},
                    {"scenario_id": "s3", "summary": "Idea 3", "parameters": {}, "priority": 0.5},
                ]
            },
        )
    ]
    simulation_results = [
        {"scenario_id": "s1", "score": 0.9},
        {"scenario_id": "s2", "score": 0.85},
        {"scenario_id": "s3", "score": 0.2},
    ]
    result = engine.arbitrate(outputs, k_candidates=1, simulation_results=simulation_results)
    assert result.selected_scenarios[0]["scenario_id"] == "s1"


def test_escalation_triggers():
    policy = EscalationPolicy(
        disagreement_threshold=0.3,
        uncertainty_threshold=0.4,
        top_gap_threshold=0.05,
        high_stakes_threshold=0.8,
        low_confidence_threshold=0.6,
    )
    decision = policy.decide(
        disagreement=0.5,
        uncertainty=0.2,
        stakes=0.4,
        average_confidence=0.9,
        top_candidate_gap=0.2,
        expert_escalations=False,
    )
    assert "upgrade_llm_tier" in decision.actions

    decision = policy.decide(
        disagreement=0.1,
        uncertainty=0.6,
        stakes=0.4,
        average_confidence=0.9,
        top_candidate_gap=0.02,
        expert_escalations=False,
    )
    assert "upgrade_simulation_fidelity" in decision.actions

    decision = policy.decide(
        disagreement=0.1,
        uncertainty=0.1,
        stakes=0.9,
        average_confidence=0.4,
        top_candidate_gap=0.2,
        expert_escalations=False,
    )
    assert "human_review" in decision.actions
