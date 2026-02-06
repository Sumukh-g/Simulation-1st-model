"""FinancePack - Portfolio backtesting with leakage detection."""
import math
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Type

import numpy as np
from pydantic import BaseModel, Field, field_validator

from ..sdk import (
    DomainPackBase,
    DomainPackRegistry,
    Fidelity,
    OutcomeBundle,
    MetricBundle,
    UncertaintyBundle,
    FeasibilityResult,
    CostEstimate,
    ObjectiveSpec,
)
from ..sdk.types import MetricValue


class FinanceState(BaseModel):
    """State for FinancePack: portfolio and market snapshot."""
    initial_capital: float = Field(default=100000.0, gt=0)
    start_date: str = Field(default="2020-01-01")
    end_date: str = Field(default="2023-12-31")
    
    # Asset universe (simplified)
    assets: List[str] = Field(default=["SPY", "BND", "GLD", "CASH"])
    
    # Historical returns (annualized, for simulation)
    expected_returns: Dict[str, float] = Field(
        default={"SPY": 0.10, "BND": 0.03, "GLD": 0.05, "CASH": 0.02}
    )
    volatilities: Dict[str, float] = Field(
        default={"SPY": 0.18, "BND": 0.05, "GLD": 0.15, "CASH": 0.0}
    )
    
    # Transaction costs
    transaction_cost_bps: float = Field(default=10.0)  # 10 basis points


class FinanceActions(BaseModel):
    """Actions for FinancePack: portfolio allocation."""
    weights: Dict[str, float] = Field(
        default={"SPY": 0.6, "BND": 0.3, "GLD": 0.1, "CASH": 0.0}
    )
    rebalance_frequency: str = Field(default="monthly")  # daily, weekly, monthly, quarterly
    
    @field_validator('weights')
    @classmethod
    def weights_sum_to_one(cls, v):
        total = sum(v.values())
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total}")
        return v


@DomainPackRegistry.register
class FinancePack(DomainPackBase):
    """
    FinancePack: Portfolio backtesting domain pack.
    
    Simulates portfolio performance with:
    - Multi-asset allocation
    - Transaction costs
    - Rebalancing strategies
    - Risk metrics (Sharpe, drawdown)
    - Leakage detection for future data
    """
    
    name = "finance-pack"
    version = "1.0.0"
    description = "Portfolio backtesting with risk metrics and leakage detection"
    metrics = [
        "total_return",
        "annualized_return",
        "sharpe_ratio",
        "max_drawdown",
        "volatility",
        "sortino_ratio",
        "final_value",
    ]
    fidelity_modes = [Fidelity.CHEAP, Fidelity.MID, Fidelity.HIGH]
    
    def state_schema(self) -> Type[BaseModel]:
        return FinanceState
    
    def action_schema(self) -> Type[BaseModel]:
        return FinanceActions
    
    def _generate_returns(
        self,
        state: FinanceState,
        fidelity: Fidelity,
        seed: int,
        n_periods: int,
    ) -> Dict[str, np.ndarray]:
        """Generate synthetic returns based on fidelity."""
        rng = np.random.RandomState(seed)
        
        # Periods per year based on fidelity
        periods_per_year = {
            Fidelity.CHEAP: 12,   # Monthly
            Fidelity.MID: 52,    # Weekly
            Fidelity.HIGH: 252,  # Daily
        }[fidelity]
        
        returns = {}
        for asset in state.assets:
            mu = state.expected_returns.get(asset, 0.05) / periods_per_year
            sigma = state.volatilities.get(asset, 0.15) / math.sqrt(periods_per_year)
            
            # Generate returns
            asset_returns = rng.normal(mu, sigma, n_periods)
            returns[asset] = asset_returns
        
        return returns
    
    def simulate(
        self,
        state: FinanceState,
        actions: FinanceActions,
        fidelity: Fidelity,
        seed: int,
        scenario_id: str,
        run_id: str,
    ) -> OutcomeBundle:
        """Run portfolio backtest simulation."""
        start_time = time.time()
        
        # Determine simulation periods based on fidelity
        periods_config = {
            Fidelity.CHEAP: 36,   # 3 years monthly
            Fidelity.MID: 156,   # 3 years weekly
            Fidelity.HIGH: 756,  # 3 years daily
        }
        n_periods = periods_config[fidelity]
        
        # Generate synthetic returns
        returns = self._generate_returns(state, fidelity, seed, n_periods)
        
        # Rebalancing frequency
        rebal_periods = {
            "daily": 1,
            "weekly": 5 if fidelity == Fidelity.HIGH else 1,
            "monthly": 21 if fidelity == Fidelity.HIGH else (4 if fidelity == Fidelity.MID else 1),
            "quarterly": 63 if fidelity == Fidelity.HIGH else (13 if fidelity == Fidelity.MID else 3),
        }
        rebal_freq = rebal_periods.get(actions.rebalance_frequency, 21)
        
        # Simulate portfolio
        portfolio_value = state.initial_capital
        values = [portfolio_value]
        weights = {a: actions.weights.get(a, 0.0) for a in state.assets}
        
        transaction_cost = state.transaction_cost_bps / 10000
        
        for t in range(n_periods):
            # Compute period return
            period_return = sum(
                weights[asset] * returns[asset][t]
                for asset in state.assets
            )
            
            # Update portfolio value
            portfolio_value *= (1 + period_return)
            
            # Rebalance if needed
            if (t + 1) % rebal_freq == 0:
                # Apply transaction cost (simplified: proportional to turnover)
                turnover = 0.1  # Simplified assumption
                portfolio_value *= (1 - turnover * transaction_cost)
            
            values.append(portfolio_value)
        
        # Compute statistics
        values_array = np.array(values)
        returns_array = np.diff(values_array) / values_array[:-1]
        
        execution_time = (time.time() - start_time) * 1000
        
        return OutcomeBundle(
            scenario_id=scenario_id,
            run_id=run_id,
            final_state={
                "final_value": portfolio_value,
                "values": values[-10:],  # Last 10 values for chart
                "total_return": (portfolio_value / state.initial_capital) - 1,
            },
            trajectory=[{"period": i, "value": v} for i, v in enumerate(values)],
            fidelity=fidelity,
            seed=seed,
            execution_time_ms=execution_time,
            domain_pack_name=self.name,
            domain_pack_version=self.version,
            artifacts={
                "returns": returns_array.tolist()[-20:],  # Last 20 returns
                "n_periods": n_periods,
            },
            raw_output={"returns_array": returns_array.tolist()},
        )
    
    def score(
        self,
        outcome: OutcomeBundle,
        objectives: ObjectiveSpec,
    ) -> MetricBundle:
        """Compute financial metrics."""
        returns = outcome.raw_output.get("returns_array", [])
        returns_array = np.array(returns)
        
        final_value = outcome.final_state["final_value"]
        total_return = outcome.final_state["total_return"]
        
        n_periods = outcome.artifacts.get("n_periods", 252)
        annualization_factor = 252 / max(len(returns_array), 1)  # Assume daily base
        
        # Annualized return
        annualized_return = (1 + total_return) ** annualization_factor - 1
        
        # Volatility (annualized)
        volatility = np.std(returns_array) * np.sqrt(252) if len(returns_array) > 0 else 0.0
        
        # Sharpe ratio (assuming 2% risk-free)
        risk_free = 0.02 / 252  # Daily
        excess_returns = returns_array - risk_free
        sharpe = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252) if np.std(excess_returns) > 0 else 0.0
        
        # Sortino ratio (downside deviation)
        downside_returns = returns_array[returns_array < 0]
        downside_dev = np.std(downside_returns) if len(downside_returns) > 0 else 0.001
        sortino = np.mean(excess_returns) / downside_dev * np.sqrt(252) if downside_dev > 0 else 0.0
        
        # Maximum drawdown
        cumulative = np.cumprod(1 + returns_array)
        rolling_max = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - rolling_max) / rolling_max
        max_drawdown = abs(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0
        
        metrics = [
            MetricValue(name="total_return", value=float(total_return), unit="%"),
            MetricValue(name="annualized_return", value=float(annualized_return), unit="%"),
            MetricValue(name="sharpe_ratio", value=float(sharpe)),
            MetricValue(name="max_drawdown", value=float(max_drawdown), unit="%"),
            MetricValue(name="volatility", value=float(volatility), unit="%"),
            MetricValue(name="sortino_ratio", value=float(sortino)),
            MetricValue(name="final_value", value=float(final_value), unit="USD"),
        ]
        
        return MetricBundle(
            scenario_id=outcome.scenario_id,
            run_id=outcome.run_id,
            metrics=metrics,
            is_feasible=True,
        )
    
    def feasibility(
        self,
        state: FinanceState,
        actions: FinanceActions,
    ) -> FeasibilityResult:
        """Check portfolio configuration feasibility."""
        violations = []
        magnitudes = {}
        warnings = []
        
        # Check weights sum to 1
        total_weight = sum(actions.weights.values())
        if abs(total_weight - 1.0) > 0.001:
            violations.append(f"Weights sum to {total_weight}, not 1.0")
            magnitudes["weight_sum"] = abs(total_weight - 1.0)
        
        # Check no negative weights (no shorting)
        for asset, weight in actions.weights.items():
            if weight < 0:
                violations.append(f"Negative weight for {asset}")
                magnitudes[f"weight_{asset}"] = abs(weight)
        
        # Check all assets exist
        for asset in actions.weights.keys():
            if asset not in state.assets:
                violations.append(f"Unknown asset: {asset}")
        
        # Warnings for concentrated positions
        for asset, weight in actions.weights.items():
            if weight > 0.8:
                warnings.append(f"Concentrated position in {asset} ({weight:.0%})")
        
        return FeasibilityResult(
            is_feasible=len(violations) == 0,
            violations=violations,
            violation_magnitudes=magnitudes,
            warnings=warnings,
        )
    
    def cost_model(self, fidelity: Fidelity) -> CostEstimate:
        """Estimate backtest cost."""
        times = {
            Fidelity.CHEAP: 50.0,    # Monthly simulation
            Fidelity.MID: 200.0,     # Weekly simulation
            Fidelity.HIGH: 1000.0,   # Daily simulation
        }
        return CostEstimate(
            fidelity=fidelity,
            estimated_time_ms=times[fidelity],
            estimated_memory_mb=50.0,
        )
    
    def check_leakage(
        self,
        state: FinanceState,
        actions: FinanceActions,
        current_date: str,
    ) -> Dict[str, bool]:
        """
        Check for data leakage - using future information.
        
        This is called during validation to ensure the simulation
        doesn't accidentally use data from after current_date.
        """
        leakage_detected = {}
        
        # Check if end_date is in the future relative to current_date
        try:
            end = datetime.strptime(state.end_date, "%Y-%m-%d")
            current = datetime.strptime(current_date, "%Y-%m-%d")
            
            if end > current:
                leakage_detected["future_end_date"] = True
        except ValueError:
            pass
        
        return leakage_detected
