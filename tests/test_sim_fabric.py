"""Tests for Simulation Fabric components."""
import hashlib
import json
import math

import pytest

from services.sim_fabric.invariants import InvariantChecker, InvariantViolation
from services.sim_fabric.cache import ResultCache


class TestInvariantChecker:
    """Tests for invariant checks."""

    def test_bounds_check_passes(self):
        checker = InvariantChecker("toy-pack")
        outcome = {
            "metrics": [
                {"name": "score", "value": 0.85},
                {"name": "distance", "value": 5.2},
            ]
        }
        report = checker.check_all(outcome)
        bounds_violations = [v for v in report.violations if v.check_name == "bounds_check"]
        assert len(bounds_violations) == 0

    def test_bounds_check_fails_on_extreme_value(self):
        checker = InvariantChecker("toy-pack")
        outcome = {
            "metrics": [
                {"name": "score", "value": 1e20},
            ]
        }
        report = checker.check_all(outcome)
        bounds_violations = [v for v in report.violations if v.check_name == "bounds_check"]
        assert len(bounds_violations) > 0

    def test_nan_detection(self):
        checker = InvariantChecker("toy-pack")
        outcome = {
            "metrics": [
                {"name": "score", "value": float("nan")},
            ]
        }
        report = checker.check_all(outcome)
        nan_violations = [v for v in report.violations if v.check_name == "nan_check"]
        assert len(nan_violations) > 0
        assert not report.passed

    def test_inf_detection(self):
        checker = InvariantChecker("toy-pack")
        outcome = {
            "metrics": [
                {"name": "score", "value": float("inf")},
            ]
        }
        report = checker.check_all(outcome)
        inf_violations = [v for v in report.violations if v.check_name == "inf_check"]
        assert len(inf_violations) > 0
        assert not report.passed

    def test_spatial_conservation_negative_values(self):
        checker = InvariantChecker("spatial-pack")
        outcome = {
            "metrics": [],
            "arrays": {
                "concentration_grid": [
                    [1.0, 2.0, 3.0],
                    [-1.0, 0.5, 0.5],  # Negative value
                ]
            },
        }
        report = checker.check_all(outcome)
        spatial_violations = [
            v for v in report.violations if v.check_name == "spatial_non_negative"
        ]
        assert len(spatial_violations) > 0

    def test_spatial_conservation_nan_in_grid(self):
        checker = InvariantChecker("spatial-pack")
        outcome = {
            "metrics": [],
            "arrays": {
                "concentration_grid": [
                    [1.0, float("nan"), 3.0],
                    [0.5, 0.5, 0.5],
                ]
            },
        }
        report = checker.check_all(outcome)
        nan_violations = [v for v in report.violations if v.check_name == "spatial_nan"]
        assert len(nan_violations) > 0

    def test_schema_completeness_warning(self):
        checker = InvariantChecker("toy-pack")
        outcome = {}  # Missing required 'metrics' field
        report = checker.check_all(outcome)
        schema_warnings = [w for w in report.warnings if w.check_name == "schema_completeness"]
        assert len(schema_warnings) > 0


class TestResultCache:
    """Tests for result caching (mock Redis)."""

    def test_compute_scenario_hash_deterministic(self):
        cache = ResultCache.__new__(ResultCache)
        cache._redis = None  # Skip Redis init

        hash1 = cache.compute_scenario_hash(
            domain_pack_id="toy-pack",
            domain_pack_version="1.0.0",
            state={"x": 0, "y": 0},
            actions={"dx": 1, "dy": 1},
            fidelity="mid",
            seed=42,
        )
        hash2 = cache.compute_scenario_hash(
            domain_pack_id="toy-pack",
            domain_pack_version="1.0.0",
            state={"x": 0, "y": 0},
            actions={"dx": 1, "dy": 1},
            fidelity="mid",
            seed=42,
        )
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex

    def test_compute_scenario_hash_differs_with_seed(self):
        cache = ResultCache.__new__(ResultCache)
        cache._redis = None

        hash1 = cache.compute_scenario_hash(
            domain_pack_id="toy-pack",
            domain_pack_version="1.0.0",
            state={"x": 0},
            actions={"dx": 1},
            fidelity="mid",
            seed=42,
        )
        hash2 = cache.compute_scenario_hash(
            domain_pack_id="toy-pack",
            domain_pack_version="1.0.0",
            state={"x": 0},
            actions={"dx": 1},
            fidelity="mid",
            seed=123,
        )
        assert hash1 != hash2

    def test_compute_scenario_hash_differs_with_fidelity(self):
        cache = ResultCache.__new__(ResultCache)
        cache._redis = None

        hash1 = cache.compute_scenario_hash(
            domain_pack_id="toy-pack",
            domain_pack_version="1.0.0",
            state={"x": 0},
            actions={"dx": 1},
            fidelity="cheap",
            seed=42,
        )
        hash2 = cache.compute_scenario_hash(
            domain_pack_id="toy-pack",
            domain_pack_version="1.0.0",
            state={"x": 0},
            actions={"dx": 1},
            fidelity="high",
            seed=42,
        )
        assert hash1 != hash2
