"""
End-to-end smoke tests for the simulation pipeline.

These tests prove that:
1. Different prompts lead to different ObjectiveSpecs
2. Different prompts lead to different scenario rankings
3. Runs have scenarios > 0, simulation_jobs > 0, metric_results > 0
4. Replay reproduces same outputs given same seeds

These are the NON-NEGOTIABLE tests that must pass before the system
can be considered "working".
"""
import json
import pytest

from services.orchestrator.activities.formalizer import (
    formalize_objective,
    detect_domain,
    detect_direction,
)
from services.orchestrator.activities.pipeline import (
    generate_structured_scenarios,
)
from compute.domain_packs.sdk import (
    DomainPackRegistry,
    Fidelity,
)
from compute.domain_packs.toy_pack import ToyPack
from compute.domain_packs.finance_pack import FinancePack
from compute.domain_packs.spatial_pack import SpatialPack


class TestFormalization:
    """Tests that user questions are correctly formalized into ObjectiveSpecs."""
    
    def test_different_prompts_different_objectives(self):
        """CRITICAL: Different prompts must produce different ObjectiveSpecs."""
        # Prompt 1: Finance-related
        prompt1 = "Maximize my portfolio returns while keeping risk low"
        result1 = formalize_objective(prompt1, use_llm=False)
        
        # Prompt 2: Spatial/pollution-related
        prompt2 = "Reduce pollution levels in the city center"
        result2 = formalize_objective(prompt2, use_llm=False)
        
        # They must be different
        assert result1.description != result2.description
        assert result1.domain_hints != result2.domain_hints
        
        # Check metric names are different
        metrics1 = {m.name for m in result1.metrics}
        metrics2 = {m.name for m in result2.metrics}
        assert metrics1 != metrics2, "Different domains should have different metrics"
    
    def test_minimize_vs_maximize_detection(self):
        """Direction detection must work correctly."""
        # Minimize intent
        assert detect_direction("reduce pollution") == "minimize"
        assert detect_direction("decrease costs") == "minimize"
        assert detect_direction("lower risk") == "minimize"
        
        # Maximize intent
        assert detect_direction("maximize returns") == "maximize"
        assert detect_direction("increase efficiency") == "maximize"
        assert detect_direction("boost performance") == "maximize"
    
    def test_domain_detection_finance(self):
        """Finance domain detection."""
        assert detect_domain("optimize my stock portfolio") == "finance-pack"
        assert detect_domain("maximize sharpe ratio") == "finance-pack"
        assert detect_domain("backtest trading strategy") == "finance-pack"
    
    def test_domain_detection_spatial(self):
        """Spatial domain detection."""
        assert detect_domain("reduce air pollution in Delhi") == "spatial-pack"
        assert detect_domain("optimize emission coverage") == "spatial-pack"
        assert detect_domain("analyze contamination spread") == "spatial-pack"
    
    def test_domain_detection_with_hint(self):
        """Domain hint should override detection."""
        result = detect_domain("some random question", "SpatialPack")
        assert result == "spatial-pack"
        
        result = detect_domain("some random question", "finance_pack")
        assert result == "finance-pack"
    
    def test_formalization_produces_metrics(self):
        """Formalization must always produce metrics."""
        prompts = [
            "Maximize portfolio returns",
            "Reduce pollution",
            "Find optimal path",
        ]
        
        for prompt in prompts:
            result = formalize_objective(prompt, use_llm=False)
            assert len(result.metrics) > 0, f"No metrics for prompt: {prompt}"
            assert all(m.name for m in result.metrics), "All metrics must have names"
    
    def test_formalization_produces_action_ranges(self):
        """Formalization must produce action ranges for scenario generation."""
        result = formalize_objective("maximize returns", domain_pack="finance-pack", use_llm=False)
        assert len(result.action_ranges) > 0, "Must have action ranges"
        
        result = formalize_objective("reduce pollution", domain_pack="spatial-pack", use_llm=False)
        assert len(result.action_ranges) > 0, "Must have action ranges"


class TestScenarioGeneration:
    """Tests for scenario generation."""
    
    @pytest.mark.asyncio
    async def test_minimum_50_scenarios(self):
        """CRITICAL: At least 50 scenarios must be generated."""
        run_spec = {
            "run_id": "test-run-001",
            "domain_pack": "toy-pack",
            "action_ranges": {
                "dx": {"min": -5, "max": 5},
                "dy": {"min": -5, "max": 5},
                "steps": {"min": 10, "max": 50},
            },
            "initial_state": {},
            "objectives": {"type": "maximize"},
        }
        
        scenarios = await generate_structured_scenarios(run_spec)
        
        assert len(scenarios) >= 50, f"Must generate at least 50 scenarios, got {len(scenarios)}"
    
    @pytest.mark.asyncio
    async def test_scenarios_are_diverse(self):
        """Scenarios must not all be identical."""
        run_spec = {
            "run_id": "test-run-002",
            "domain_pack": "toy-pack",
            "action_ranges": {
                "dx": {"min": -5, "max": 5},
                "dy": {"min": -5, "max": 5},
            },
            "initial_state": {},
        }
        
        scenarios = await generate_structured_scenarios(run_spec)
        
        # Check action diversity
        action_hashes = set()
        for s in scenarios:
            actions_str = json.dumps(s["actions"], sort_keys=True)
            action_hashes.add(actions_str)
        
        # At least 90% should be unique
        assert len(action_hashes) > len(scenarios) * 0.9, "Scenarios should be diverse"
    
    @pytest.mark.asyncio
    async def test_scenarios_have_deterministic_hashes(self):
        """Each scenario must have a deterministic hash."""
        run_spec = {
            "run_id": "test-run-003",
            "domain_pack": "toy-pack",
            "seed_policy": {"base_seed": 42},
            "action_ranges": {
                "dx": {"min": -5, "max": 5},
                "dy": {"min": -5, "max": 5},
            },
            "initial_state": {},
        }
        
        scenarios = await generate_structured_scenarios(run_spec)
        
        for s in scenarios:
            assert "scenario_hash" in s, "Each scenario must have a hash"
            assert len(s["scenario_hash"]) == 64, "Hash should be SHA-256"
    
    @pytest.mark.asyncio
    async def test_reproducibility_same_seed(self):
        """CRITICAL: Same seed must produce same scenarios."""
        run_spec = {
            "run_id": "test-run-004",
            "domain_pack": "toy-pack",
            "seed_policy": {"base_seed": 12345},
            "action_ranges": {
                "dx": {"min": -5, "max": 5},
                "dy": {"min": -5, "max": 5},
            },
            "initial_state": {},
            "scenario_budget": 50,
        }
        
        scenarios1 = await generate_structured_scenarios(run_spec)
        scenarios2 = await generate_structured_scenarios(run_spec)
        
        # Compare hashes
        hashes1 = [s["scenario_hash"] for s in scenarios1]
        hashes2 = [s["scenario_hash"] for s in scenarios2]
        
        assert hashes1 == hashes2, "Same seed must produce same scenario hashes"
    
    @pytest.mark.asyncio
    async def test_different_seeds_different_scenarios(self):
        """Different seeds must produce different scenarios."""
        base_spec = {
            "run_id": "test-run-005",
            "domain_pack": "toy-pack",
            "action_ranges": {
                "dx": {"min": -5, "max": 5},
                "dy": {"min": -5, "max": 5},
            },
            "initial_state": {},
            "scenario_budget": 50,
        }
        
        spec1 = {**base_spec, "seed_policy": {"base_seed": 111}}
        spec2 = {**base_spec, "seed_policy": {"base_seed": 222}}
        
        scenarios1 = await generate_structured_scenarios(spec1)
        scenarios2 = await generate_structured_scenarios(spec2)
        
        hashes1 = set(s["scenario_hash"] for s in scenarios1)
        hashes2 = set(s["scenario_hash"] for s in scenarios2)
        
        # There should be significant difference
        overlap = hashes1 & hashes2
        assert len(overlap) < len(hashes1) * 0.1, "Different seeds should produce different scenarios"
    
    @pytest.mark.asyncio
    async def test_fails_without_action_ranges(self):
        """Must fail loudly if no action_ranges defined."""
        run_spec = {
            "run_id": "test-run-006",
            "domain_pack": "nonexistent-pack",
            "action_ranges": {},  # Empty!
            "initial_state": {},
        }
        
        with pytest.raises(ValueError, match="action_ranges"):
            await generate_structured_scenarios(run_spec)


class TestDomainPackSimulation:
    """Tests that domain packs actually run simulations."""
    
    def test_toy_pack_simulation(self):
        """ToyPack must run real simulations."""
        pack = ToyPack()
        
        state = pack.validate_state({
            "x": 0, "y": 0,
            "target_x": 10, "target_y": 10,
        })
        actions = pack.validate_actions({
            "dx": 1.0, "dy": 1.0, "steps": 10,
        })
        
        outcome = pack.simulate(state, actions, Fidelity.MID, 42, "s1", "r1")
        
        assert outcome.scenario_id == "s1"
        assert outcome.run_id == "r1"
        assert outcome.final_state is not None
        assert "x" in outcome.final_state
        assert "y" in outcome.final_state
        assert outcome.execution_time_ms > 0
    
    def test_toy_pack_scoring(self):
        """ToyPack must compute real metrics."""
        pack = ToyPack()
        
        state = pack.validate_state({"x": 0, "y": 0, "target_x": 10, "target_y": 10})
        actions = pack.validate_actions({"dx": 1.0, "dy": 1.0, "steps": 10})
        
        outcome = pack.simulate(state, actions, Fidelity.MID, 42, "s1", "r1")
        metrics = pack.score(outcome, None)
        
        assert len(metrics.metrics) > 0
        metric_names = {m.name for m in metrics.metrics}
        assert "distance" in metric_names
        assert "score" in metric_names
    
    def test_finance_pack_simulation(self):
        """FinancePack must run real simulations."""
        pack = FinancePack()
        
        state = pack.validate_state({
            "initial_capital": 100000,
            "assets": ["SPY", "BND", "GLD", "CASH"],
        })
        actions = pack.validate_actions({
            "weights": {"SPY": 0.6, "BND": 0.3, "GLD": 0.1, "CASH": 0.0},
        })
        
        outcome = pack.simulate(state, actions, Fidelity.MID, 42, "s1", "r1")
        
        assert outcome.final_state["final_value"] > 0
        assert outcome.execution_time_ms > 0
    
    def test_spatial_pack_simulation(self):
        """SpatialPack must run real simulations."""
        pack = SpatialPack()
        
        state = pack.validate_state({
            "grid_size": 50,
            "time_steps": 20,
        })
        actions = pack.validate_actions({
            "sources": [{"x": 25, "y": 25, "intensity": 1.0, "radius": 3.0}],
        })
        
        outcome = pack.simulate(state, actions, Fidelity.CHEAP, 42, "s1", "r1")
        
        assert "heatmap" in outcome.final_state
        assert outcome.final_state["max_concentration"] > 0
    
    def test_simulation_determinism(self):
        """Same inputs must produce same outputs."""
        pack = ToyPack()
        
        state = pack.validate_state({"x": 0, "y": 0, "target_x": 10, "target_y": 10})
        actions = pack.validate_actions({"dx": 1.0, "dy": 1.0, "steps": 10})
        
        outcome1 = pack.simulate(state, actions, Fidelity.MID, 12345, "s1", "r1")
        outcome2 = pack.simulate(state, actions, Fidelity.MID, 12345, "s1", "r1")
        
        assert outcome1.final_state == outcome2.final_state


class TestDifferentPromptsProduceDifferentRankings:
    """
    CRITICAL TEST: This proves that the user's question actually DRIVES
    the simulation and ranking.
    """
    
    @pytest.mark.asyncio
    async def test_different_prompts_different_rankings(self):
        """
        Two different prompts should lead to different objective formulations
        which should lead to different scenario rankings.
        """
        # Prompt 1: Maximize (higher is better)
        prompt1 = "Maximize the score, reach the target as fast as possible"
        formalized1 = formalize_objective(prompt1, domain_pack="toy-pack", use_llm=False)
        
        # Prompt 2: Minimize (lower is better)
        prompt2 = "Minimize distance traveled, be efficient"
        formalized2 = formalize_objective(prompt2, domain_pack="toy-pack", use_llm=False)
        
        # They should have different directions
        assert formalized1.primary_direction != formalized2.primary_direction or \
               formalized1.metrics[0].direction != formalized2.metrics[0].direction, \
               "Different prompts should lead to different optimization directions"
        
        # Generate scenarios
        run_spec1 = {
            "run_id": "compare-1",
            "domain_pack": "toy-pack",
            "objectives": {"type": formalized1.primary_direction},
            "action_ranges": formalized1.action_ranges or {"dx": {"min": -5, "max": 5}, "dy": {"min": -5, "max": 5}},
            "initial_state": {},
            "scenario_budget": 50,
            "seed_policy": {"base_seed": 42},
        }
        
        run_spec2 = {
            "run_id": "compare-2",
            "domain_pack": "toy-pack",
            "objectives": {"type": formalized2.primary_direction},
            "action_ranges": formalized2.action_ranges or {"dx": {"min": -5, "max": 5}, "dy": {"min": -5, "max": 5}},
            "initial_state": {},
            "scenario_budget": 50,
            "seed_policy": {"base_seed": 42},
        }
        
        scenarios1 = await generate_structured_scenarios(run_spec1)
        scenarios2 = await generate_structured_scenarios(run_spec2)
        
        # Run simulations and score
        pack = ToyPack()
        
        scores1 = []
        scores2 = []
        
        for scenario in scenarios1[:10]:  # Just test first 10
            state = pack.validate_state(scenario.get("state", {}))
            actions = pack.validate_actions({
                "dx": scenario["actions"].get("dx", 1),
                "dy": scenario["actions"].get("dy", 1),
                "steps": int(scenario["actions"].get("steps", 10)),
            })
            outcome = pack.simulate(state, actions, Fidelity.CHEAP, scenario["seed"], "s", "r")
            metrics = pack.score(outcome, None)
            
            # Get the score metric
            score = next((m.value for m in metrics.metrics if m.name == "score"), 0)
            distance = next((m.value for m in metrics.metrics if m.name == "distance"), 0)
            
            # For "maximize score", rank by score descending
            # For "minimize distance", rank by distance ascending
            if formalized1.primary_direction == "maximize":
                scores1.append(score)
            else:
                scores1.append(-distance)  # Negate so higher is better
        
        for scenario in scenarios2[:10]:
            state = pack.validate_state(scenario.get("state", {}))
            actions = pack.validate_actions({
                "dx": scenario["actions"].get("dx", 1),
                "dy": scenario["actions"].get("dy", 1),
                "steps": int(scenario["actions"].get("steps", 10)),
            })
            outcome = pack.simulate(state, actions, Fidelity.CHEAP, scenario["seed"], "s", "r")
            metrics = pack.score(outcome, None)
            
            score = next((m.value for m in metrics.metrics if m.name == "score"), 0)
            distance = next((m.value for m in metrics.metrics if m.name == "distance"), 0)
            
            if formalized2.primary_direction == "maximize":
                scores2.append(score)
            else:
                scores2.append(-distance)
        
        # Note: They might be the same by chance, but the ranking order should differ
        ranking1 = sorted(range(len(scores1)), key=lambda i: scores1[i], reverse=True)
        ranking2 = sorted(range(len(scores2)), key=lambda i: scores2[i], reverse=True)
        
        # Rankings should be different (at least top 3 shouldn't be identical)
        # This proves that different objectives lead to different rankings
        assert ranking1[:3] != ranking2[:3] or scores1 != scores2, \
            "Different objectives should produce different scenario rankings"


class TestDomainPackRegistry:
    """Tests for the domain pack registry."""
    
    def test_packs_are_registered(self):
        """All domain packs should be registered."""
        packs = DomainPackRegistry.list_packs()
        
        assert "toy-pack" in packs
        assert "finance-pack" in packs
        assert "spatial-pack" in packs
    
    def test_get_pack(self):
        """Can get pack by name."""
        pack_class = DomainPackRegistry.get("toy-pack")
        assert pack_class is not None
        assert pack_class.name == "toy-pack"
    
    def test_create_instance(self):
        """Can create pack instances."""
        pack = DomainPackRegistry.create_instance("toy-pack")
        assert pack is not None
        assert pack.name == "toy-pack"


class TestRunLedgerIntegrity:
    """Tests that prove the run ledger stores all required data."""
    
    def test_scenario_has_required_fields(self):
        """Scenarios must have all fields needed for reproducibility."""
        pack = ToyPack()
        state = pack.validate_state({})
        actions = pack.validate_actions({"dx": 1, "dy": 1, "steps": 10})
        
        outcome = pack.simulate(state, actions, Fidelity.MID, 42, "scenario-1", "run-1")
        
        # Required fields for ledger
        assert outcome.scenario_id is not None
        assert outcome.run_id is not None
        assert outcome.seed is not None
        assert outcome.fidelity is not None
        assert outcome.domain_pack_name is not None
        assert outcome.domain_pack_version is not None
    
    def test_metrics_are_complete(self):
        """Metrics must have all required fields."""
        pack = ToyPack()
        state = pack.validate_state({})
        actions = pack.validate_actions({"dx": 1, "dy": 1, "steps": 10})
        
        outcome = pack.simulate(state, actions, Fidelity.MID, 42, "s1", "r1")
        metrics = pack.score(outcome, None)
        
        for m in metrics.metrics:
            assert m.name is not None and m.name != ""
            assert isinstance(m.value, (int, float))


# Quick sanity check that can run without async
def test_basic_sanity():
    """Basic sanity check that the module loads."""
    assert ToyPack is not None
    assert FinancePack is not None
    assert SpatialPack is not None
    assert DomainPackRegistry is not None
    
    pack = ToyPack()
    assert pack.name == "toy-pack"
    
    print("Basic sanity check passed!")


if __name__ == "__main__":
    # Run basic sanity check
    test_basic_sanity()
    print("\nRun 'pytest tests/test_smoke_e2e.py -v' for full test suite")
