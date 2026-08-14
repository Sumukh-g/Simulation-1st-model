"""Tests for Domain Packs."""
from compute.domain_packs.sdk import Fidelity, DomainPackRegistry
from compute.domain_packs.toy_pack import ToyPack
from compute.domain_packs.finance_pack import FinancePack
from compute.domain_packs.spatial_pack import SpatialPack


class TestToyPack:
    """Tests for ToyPack."""
    
    def test_initialization(self):
        """Test pack initialization."""
        pack = ToyPack()
        assert pack.name == "toy-pack"
        assert pack.version == "1.0.0"
    
    def test_state_validation(self, sample_toy_state):
        """Test state validation."""
        pack = ToyPack()
        state = pack.validate_state(sample_toy_state)
        assert state.x == 0.0
        assert state.target_x == 10.0
    
    def test_action_validation(self, sample_toy_actions):
        """Test action validation."""
        pack = ToyPack()
        actions = pack.validate_actions(sample_toy_actions)
        assert actions.dx == 1.0
        assert actions.steps == 10
    
    def test_simulation_determinism(self, sample_toy_state, sample_toy_actions):
        """Test that simulation is deterministic with same seed."""
        pack = ToyPack()
        state = pack.validate_state(sample_toy_state)
        actions = pack.validate_actions(sample_toy_actions)
        
        result1 = pack.simulate(state, actions, Fidelity.MID, 42, "s1", "r1")
        result2 = pack.simulate(state, actions, Fidelity.MID, 42, "s1", "r1")
        
        assert result1.final_state == result2.final_state
    
    def test_simulation_different_seeds(self, sample_toy_state, sample_toy_actions):
        """Test that different seeds produce different results."""
        pack = ToyPack()
        state = pack.validate_state(sample_toy_state)
        actions = pack.validate_actions(sample_toy_actions)
        
        result1 = pack.simulate(state, actions, Fidelity.MID, 42, "s1", "r1")
        result2 = pack.simulate(state, actions, Fidelity.MID, 123, "s2", "r1")
        
        # Results should be different due to noise
        assert result1.final_state != result2.final_state
    
    def test_feasibility_valid(self, sample_toy_state, sample_toy_actions):
        """Test feasibility check with valid inputs."""
        pack = ToyPack()
        state = pack.validate_state(sample_toy_state)
        actions = pack.validate_actions(sample_toy_actions)
        
        result = pack.feasibility(state, actions)
        assert result.is_feasible
    
    def test_cost_model(self):
        """Test cost estimation."""
        pack = ToyPack()
        
        cheap = pack.cost_model(Fidelity.CHEAP)
        mid = pack.cost_model(Fidelity.MID)
        high = pack.cost_model(Fidelity.HIGH)
        
        assert cheap.estimated_time_ms < mid.estimated_time_ms
        assert mid.estimated_time_ms < high.estimated_time_ms


class TestFinancePack:
    """Tests for FinancePack."""
    
    def test_initialization(self):
        """Test pack initialization."""
        pack = FinancePack()
        assert pack.name == "finance-pack"
        assert "sharpe_ratio" in pack.metrics
    
    def test_simulation(self, sample_finance_state, sample_finance_actions):
        """Test simulation runs."""
        pack = FinancePack()
        state = pack.validate_state(sample_finance_state)
        actions = pack.validate_actions(sample_finance_actions)
        
        result = pack.simulate(state, actions, Fidelity.MID, 42, "s1", "r1")
        
        assert result.final_state["final_value"] > 0
        assert "total_return" in result.final_state


class TestSpatialPack:
    """Tests for SpatialPack."""
    
    def test_initialization(self):
        """Test pack initialization."""
        pack = SpatialPack()
        assert pack.name == "spatial-pack"
        assert "coverage_ratio" in pack.metrics
    
    def test_simulation(self):
        """Test simulation runs."""
        pack = SpatialPack()
        
        state = pack.validate_state({
            "grid_size": 50,
            "time_steps": 50,
        })
        actions = pack.validate_actions({
            "sources": [
                {"x": 25, "y": 25, "intensity": 1.0, "radius": 3.0},
            ],
        })
        
        result = pack.simulate(state, actions, Fidelity.CHEAP, 42, "s1", "r1")
        
        assert "heatmap" in result.final_state
        assert result.final_state["max_concentration"] > 0


class TestDomainPackRegistry:
    """Tests for domain pack registry."""
    
    def test_registration(self):
        """Test pack registration."""
        packs = DomainPackRegistry.list_packs()
        assert "toy-pack" in packs
        assert "finance-pack" in packs
        assert "spatial-pack" in packs
    
    def test_get_pack(self):
        """Test getting pack by name."""
        pack_class = DomainPackRegistry.get("toy-pack")
        assert pack_class is not None
    
    def test_create_instance(self):
        """Test creating pack instance."""
        pack = DomainPackRegistry.create_instance("toy-pack")
        assert pack.name == "toy-pack"
