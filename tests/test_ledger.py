"""Tests for Run Ledger."""
import pytest
from libs.ledger.gsip_ledger.hashing import (
    compute_scenario_hash,
    compute_run_hash,
    compute_artifact_checksum,
    verify_hash,
)


class TestHashing:
    """Tests for deterministic hashing."""
    
    def test_scenario_hash_determinism(self):
        """Test scenario hash is deterministic."""
        hash1 = compute_scenario_hash(
            run_id="r1",
            input_state={"x": 1, "y": 2},
            actions={"dx": 0.5},
            fidelity="mid",
            seed=42,
        )
        
        hash2 = compute_scenario_hash(
            run_id="r1",
            input_state={"x": 1, "y": 2},
            actions={"dx": 0.5},
            fidelity="mid",
            seed=42,
        )
        
        assert hash1 == hash2
    
    def test_scenario_hash_differs_with_seed(self):
        """Test different seeds produce different hashes."""
        hash1 = compute_scenario_hash(
            run_id="r1",
            input_state={"x": 1},
            actions={"dx": 0.5},
            fidelity="mid",
            seed=42,
        )
        
        hash2 = compute_scenario_hash(
            run_id="r1",
            input_state={"x": 1},
            actions={"dx": 0.5},
            fidelity="mid",
            seed=123,
        )
        
        assert hash1 != hash2
    
    def test_run_hash_determinism(self):
        """Test run hash is deterministic."""
        spec = {
            "domain_pack_id": "toy-pack",
            "domain_pack_version": "1.0.0",
            "objective_spec": {"type": "maximize", "metrics": ["score"]},
            "constraints": [],
            "seed_policy": "auto",
        }
        
        hash1 = compute_run_hash(spec)
        hash2 = compute_run_hash(spec)
        
        assert hash1 == hash2
    
    def test_run_hash_differs_with_spec(self):
        """Test different specs produce different hashes."""
        spec1 = {
            "domain_pack_id": "toy-pack",
            "objective_spec": {"type": "maximize", "metrics": ["score"]},
        }
        
        spec2 = {
            "domain_pack_id": "finance-pack",
            "objective_spec": {"type": "maximize", "metrics": ["score"]},
        }
        
        assert compute_run_hash(spec1) != compute_run_hash(spec2)
    
    def test_artifact_checksum(self):
        """Test artifact checksum computation."""
        data = b"test artifact content"
        checksum = compute_artifact_checksum(data)
        
        assert len(checksum) == 64  # SHA-256 hex
        assert compute_artifact_checksum(data) == checksum  # Deterministic
    
    def test_verify_hash(self):
        """Test hash verification."""
        data = {"key": "value", "number": 42}
        hash_value = compute_run_hash(data)
        
        assert verify_hash(data, hash_value, "run")
        assert not verify_hash({"key": "different"}, hash_value, "run")
