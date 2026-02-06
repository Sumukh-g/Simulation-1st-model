# GSIP Optimizer Service

Multi-objective, multi-fidelity optimization with constraint handling.

## Overview

The Optimizer Service provides:
- **Bayesian Optimization**: GP-based surrogate with Expected Improvement
- **Evolutionary Optimization**: NSGA-II for multi-objective Pareto frontiers
- **Bandit Allocation**: Thompson Sampling for multi-fidelity scheduling
- **Constraint Handling**: Hard filters + soft penalties
- **Stopping Rules**: Plateau, budget, confidence, convergence

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    UnifiedOptimizer                          │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    API Layer                             ││
│  │  init | propose_batch | update | get_frontier | explain ││
│  └─────────────────────────────────────────────────────────┘│
│              │                                               │
│  ┌───────────┼───────────┬───────────┬───────────┐          │
│  ▼           ▼           ▼           ▼           ▼          │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐│
│ │Bayesian │ │Evolution│ │Bandit   │ │Constraint│ │Stopping ││
│ │Optimizer│ │Optimizer│ │Allocator│ │Handler  │ │Rules    ││
│ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘│
└─────────────────────────────────────────────────────────────┘
```

## Modules

### optimizer.py
Unified optimizer with complete API:
- `propose_batch(n)`: Get next batch of candidates
- `update(results)`: Update with simulation outcomes
- `get_frontier()`: Get current Pareto frontier
- `get_best(objective)`: Get best candidate
- `explain_choice(id)`: Explain why candidate was proposed
- `should_promote(candidate)`: Check for fidelity promotion

### bayesian.py
Gaussian Process-based Bayesian optimization:
- Matern kernel for smooth surrogate
- Expected Improvement acquisition
- Multi-restart optimization

### evolutionary.py
NSGA-II multi-objective evolutionary algorithm:
- Non-dominated sorting
- Crowding distance for diversity
- SBX crossover + polynomial mutation

### bandit.py
Multi-fidelity Thompson Sampling:
- Cost-aware arm selection
- Correlation tracking between fidelities
- Budget governance

### constraints.py
Constraint handling:
- `HARD` constraints: Filter infeasible candidates
- `SOFT` constraints: Penalty added to objectives
- Built-in: bounds, metric thresholds

### stopping.py
Stopping conditions:
- Plateau detection
- Budget exhaustion
- Confidence threshold
- Max iterations/evaluations
- Convergence detection

## Usage

### Basic Multi-Objective Optimization

```python
from services.optimizer import (
    UnifiedOptimizer,
    OptimizerConfig,
    Objective,
    Constraint,
    ConstraintType,
    StoppingConfig,
)

# Define objectives
objectives = [
    Objective(name="impact", maximize=True, weight=1.0),
    Objective(name="cost", maximize=False, weight=1.0),
    Objective(name="feasibility", maximize=True, weight=0.5),
]

# Configure optimizer
config = OptimizerConfig(
    bounds={
        "investment": (0, 1000000),
        "duration": (1, 52),
        "intensity": (0.1, 1.0),
    },
    objectives=objectives,
    strategy=OptimizerStrategy.HYBRID,
    batch_size=10,
    budget=1000,
)

# Add constraints
constraints = [
    Constraint(
        name="min_roi",
        type=ConstraintType.HARD,
        check_fn=lambda p, o: o.get("metrics", {}).get("roi", 0) > 0.05,
    ),
    Constraint(
        name="max_risk",
        type=ConstraintType.SOFT,
        check_fn=lambda p, o: o.get("metrics", {}).get("risk", 1) < 0.3,
        penalty_fn=lambda p, o: max(0, o.get("metrics", {}).get("risk", 0) - 0.3),
        penalty_weight=10.0,
    ),
]

# Stopping config
stopping = StoppingConfig(
    plateau_window=5,
    plateau_threshold=0.01,
    max_iterations=100,
    max_budget=500,
)

# Initialize
optimizer = UnifiedOptimizer(config, constraints, stopping)

# Optimization loop
while True:
    # Get batch of candidates
    candidates = optimizer.propose_batch(10)
    
    # Run simulations (your code)
    results = []
    for c in candidates:
        outcome = run_simulation(c.params, c.fidelity)
        results.append({
            "params": c.params,
            "outcome": outcome,
            "fidelity": c.fidelity,
            "candidate_id": c.id,
        })
    
    # Update optimizer
    should_stop, reason = optimizer.update(results)
    
    if should_stop:
        print(optimizer.explain_stopping())
        break

# Get Pareto frontier
frontier = optimizer.get_frontier()
for point in frontier:
    print(f"Candidate: {point.candidate.params}")
    print(f"Objectives: {point.candidate.objectives}")
```

### Multi-Fidelity Scheduling

The optimizer automatically schedules fidelity levels:

1. Early iterations: Use `cheap` fidelity for broad exploration
2. Middle iterations: Use Thompson Sampling to balance cost/quality
3. Late iterations: Promote top candidates to `high` fidelity

```python
# Get candidates to promote
promotions = optimizer.get_promotion_candidates(top_k=3)
for c in promotions:
    # Re-run at higher fidelity
    high_outcome = run_simulation(c.params, "high")
    optimizer.update([{
        "params": c.params,
        "outcome": high_outcome,
        "fidelity": "high",
    }])
```

### Explaining Choices

```python
# Get explanation for why a candidate was proposed
candidates = optimizer.propose_batch()
for c in candidates:
    explanation = optimizer.explain_choice(c.id)
    print(f"Candidate {c.id}:")
    print(f"  Source: {explanation['source']}")
    print(f"  Reasoning: {explanation['reasoning']}")
```

## Constraint Types

### Hard Constraints
Filter out infeasible candidates before simulation:

```python
Constraint(
    name="budget_limit",
    type=ConstraintType.HARD,
    check_fn=lambda p, o: p.get("cost", 0) <= 100000,
)
```

### Soft Constraints
Add penalties to objectives when violated:

```python
Constraint(
    name="preference_zone",
    type=ConstraintType.SOFT,
    check_fn=lambda p, o: 10 <= p.get("x", 0) <= 20,
    penalty_fn=lambda p, o: abs(p.get("x", 15) - 15),
    penalty_weight=0.1,
)
```

## Stopping Rules

| Rule | Trigger |
|------|---------|
| Plateau | No improvement > threshold in N iterations |
| Budget | Budget exhausted |
| Confidence | Confidence score meets threshold |
| Max Iterations | Iteration limit reached |
| Max Evaluations | Evaluation limit reached |
| Convergence | Best score stabilized |

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `bounds` | required | Parameter bounds |
| `objectives` | `[score]` | Objective definitions |
| `strategy` | `HYBRID` | `BAYESIAN`, `EVOLUTIONARY`, or `HYBRID` |
| `batch_size` | 10 | Candidates per batch |
| `budget` | 1000 | Total compute budget |
| `population_size` | 50 | Evolutionary population |
| `mutation_rate` | 0.1 | Mutation probability |
