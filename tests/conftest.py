"""Pytest configuration and fixtures."""
import pytest
import asyncio
from typing import Generator


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_toy_state():
    """Sample ToyPack state."""
    return {
        "x": 0.0,
        "y": 0.0,
        "target_x": 10.0,
        "target_y": 10.0,
    }


@pytest.fixture
def sample_toy_actions():
    """Sample ToyPack actions."""
    return {
        "dx": 1.0,
        "dy": 1.0,
        "steps": 10,
    }


@pytest.fixture
def sample_finance_state():
    """Sample FinancePack state."""
    return {
        "initial_capital": 100000,
        "assets": ["SPY", "BND", "GLD", "CASH"],
        "expected_returns": {"SPY": 0.10, "BND": 0.03, "GLD": 0.05, "CASH": 0.02},
        "volatilities": {"SPY": 0.18, "BND": 0.05, "GLD": 0.15, "CASH": 0.0},
    }


@pytest.fixture
def sample_finance_actions():
    """Sample FinancePack actions."""
    return {
        "weights": {"SPY": 0.6, "BND": 0.3, "GLD": 0.1, "CASH": 0.0},
        "rebalance_frequency": "monthly",
    }


@pytest.fixture
def sample_rubric():
    """Sample rubric specification."""
    return {
        "id": "test-rubric",
        "name": "Test Rubric",
        "metric_weights": {"score": 1.0},
        "constraint_penalties": {},
        "feasibility_weight": 1.0,
        "confidence_penalty_rate": 0.1,
        "aggregation_method": "weighted_sum",
        "version": "1.0",
    }
