# FinancePack

Portfolio backtesting domain pack with risk metrics and leakage detection.

## Overview

FinancePack simulates portfolio performance over historical periods with:
- Multi-asset allocation
- Transaction costs
- Various rebalancing strategies
- Comprehensive risk metrics

## State Schema

```python
class FinanceState:
    initial_capital: float      # Starting capital (default: 100000)
    start_date: str            # Backtest start date
    end_date: str              # Backtest end date
    assets: List[str]          # Available assets
    expected_returns: Dict     # Annualized expected returns
    volatilities: Dict         # Annualized volatilities
    transaction_cost_bps: float # Transaction cost in basis points
```

## Action Schema

```python
class FinanceActions:
    weights: Dict[str, float]  # Portfolio weights (must sum to 1.0)
    rebalance_frequency: str   # daily, weekly, monthly, quarterly
```

## Metrics

- `total_return`: Total portfolio return
- `annualized_return`: Annualized return
- `sharpe_ratio`: Risk-adjusted return measure
- `max_drawdown`: Maximum peak-to-trough decline
- `volatility`: Annualized standard deviation
- `sortino_ratio`: Downside risk-adjusted return
- `final_value`: Final portfolio value

## Fidelity Levels

- **CHEAP**: Monthly simulation (~36 periods)
- **MID**: Weekly simulation (~156 periods)
- **HIGH**: Daily simulation (~756 periods)

## Leakage Detection

The pack includes a `check_leakage()` method to detect if the backtest
is accidentally using future data:

```python
pack = FinancePack()
leakage = pack.check_leakage(state, actions, "2023-01-01")
if leakage:
    print("Warning: Data leakage detected!")
```

## Example

```python
from domain_packs.finance_pack import FinancePack
from domain_packs.sdk import Fidelity

pack = FinancePack()

state = pack.validate_state({
    "initial_capital": 100000,
    "assets": ["SPY", "BND", "GLD", "CASH"],
})

actions = pack.validate_actions({
    "weights": {"SPY": 0.6, "BND": 0.3, "GLD": 0.1, "CASH": 0.0},
    "rebalance_frequency": "monthly",
})

outcome = pack.simulate(
    state=state,
    actions=actions,
    fidelity=Fidelity.MID,
    seed=42,
    scenario_id="backtest-001",
    run_id="run-001",
)

metrics = pack.score(outcome, None)
for m in metrics.metrics:
    print(f"{m.name}: {m.value:.4f}")
```
