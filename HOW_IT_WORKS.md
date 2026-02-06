# How It Works: AI Simulation & Solution Engine

This document explains how the system transforms a user's question into a complete simulation run with ranked solutions.

## End-to-End Flow

```
User Question → Objective Formalization → Scenario Generation → Simulation Execution → 
Scoring & Ranking → Optimization Loop → Final Report with Evidence
```

## 1. User Question Triggers a Run

When a user types a question like "reduce pollution in Delhi" or "find the best asset to predict daily price", the following happens:

### API Endpoint (`services/api/routers/runs.py`)

```python
POST /api/runs/start
{
    "prompt": "Maximize my portfolio returns while keeping risk low",
    "domain_pack": "FinancePack",
    "config": {
        "maxScenarios": 100,
        "maxWallTime": 3600
    }
}
```

1. Creates a `Run` record in PostgreSQL
2. Builds a `run_spec` containing the prompt and configuration
3. Starts a Temporal workflow in the background

## 2. Objective Formalization

The `formalize_objectives` activity (`services/orchestrator/activities/formalizer.py`) transforms the user's natural language question into a structured `ObjectiveSpec`:

### Input
```
"Maximize my portfolio returns while keeping risk low"
```

### Output (ObjectiveSpec)
```json
{
    "description": "Maximize my portfolio returns while keeping risk low",
    "metrics": [
        {"name": "sharpe_ratio", "direction": "maximize", "weight": 1.0},
        {"name": "total_return", "direction": "maximize", "weight": 0.8},
        {"name": "max_drawdown", "direction": "minimize", "weight": 0.6}
    ],
    "primary_direction": "maximize",
    "constraints": [
        {"name": "risk_level", "constraint_type": "max", "is_hard": false}
    ],
    "horizon": null,
    "context_tags": ["finance-pack", "portfolio", "risk"],
    "action_ranges": {
        "weight_spy": {"min": 0.0, "max": 1.0},
        "weight_bnd": {"min": 0.0, "max": 1.0}
    }
}
```

### How It Works

1. **Domain Detection**: Analyzes keywords to determine which domain pack to use
2. **Direction Detection**: Identifies whether to minimize or maximize
3. **Metric Selection**: Maps domain-specific metrics based on the question
4. **Constraint Extraction**: Identifies budget, time, risk constraints
5. **LLM Enhancement** (optional): Uses GPT-4 for more accurate parsing

## 3. Scenario Generation

The `generate_structured_scenarios` activity creates at least 50 diverse scenarios:

### Strategies Used

1. **Grid Sampling (20%)**: Systematic exploration of the parameter space
2. **Latin Hypercube (30%)**: Space-filling design for better coverage
3. **Random Sampling (40%)**: Exploration diversity
4. **Boundary Scenarios (10%)**: Extreme values for objective-aware exploration

### Each Scenario Contains
```json
{
    "run_id": "uuid",
    "state": {"initial_capital": 100000},
    "actions": {"weight_spy": 0.6, "weight_bnd": 0.3},
    "fidelity": "cheap",
    "seed": 12345,
    "scenario_hash": "sha256...",
    "generation_strategy": "lhs"
}
```

### Reproducibility Guarantee

- Same `seed_policy.base_seed` → Same scenarios
- Each scenario has a deterministic hash for caching and replay

## 4. Simulation Execution

The SimFabric (`services/sim_fabric/executor.py`) runs simulations using Ray:

### Domain Packs

Each domain pack implements:
```python
class DomainPackBase:
    def state_schema(self) -> Type[BaseModel]    # Input state validation
    def action_schema(self) -> Type[BaseModel]   # Action validation
    def simulate(state, actions, fidelity, seed) -> OutcomeBundle
    def score(outcome, objectives) -> MetricBundle
    def feasibility(state, actions) -> FeasibilityResult
```

### Available Domain Packs

1. **ToyPack**: Simple 2D random walk (testing)
2. **FinancePack**: Portfolio backtesting with Sharpe ratio
3. **SpatialPack**: Grid diffusion simulation (pollution, heat)

### Simulation Fidelity

- **cheap**: Fast approximation (10-100ms)
- **mid**: Standard precision (100-500ms)
- **high**: Full fidelity (500ms-2s)

## 5. Scoring & Ranking

The Judge service scores each simulation outcome:

### Deterministic Scoring
- Uses rubric weights stored in the database
- Computes weighted sum of metrics
- Checks constraint violations
- Compares against benchmarks

### Example Score Breakdown
```json
{
    "scenario_id": "uuid",
    "score": 0.85,
    "breakdown": [
        {"metric": "sharpe_ratio", "value": 1.2, "contribution": 0.5},
        {"metric": "total_return", "value": 0.15, "contribution": 0.35}
    ],
    "benchmark_results": [
        {"name": "min_sharpe", "passed": true}
    ]
}
```

## 6. Optimization Loop

The optimizer (`services/orchestrator/activities/optimization.py`) iteratively improves:

1. **Initialize**: Set up Bayesian/evolutionary optimizer
2. **Propose**: Generate next batch of scenarios based on results
3. **Evaluate**: Run simulations and score
4. **Update**: Update surrogate model with new results
5. **Check Convergence**: Stop if plateau detected

### Stopping Conditions
- Max scenarios reached
- Max wall time exceeded
- Score plateau detected
- Manual cancellation

## 7. Final Report

After optimization:

1. **Promote Finalists**: Top 5 scenarios run at higher fidelity
2. **Robustness Tests**: Sensitivity and stress scenarios
3. **Report Assembly**: Generate structured summary

### Report Contents
```json
{
    "run_id": "uuid",
    "summary": {
        "best_score": 0.92,
        "best_scenario_id": "uuid",
        "total_scenarios": 150,
        "completed": 148,
        "failed": 2
    },
    "top_scenarios": [...],
    "evidence_pack_id": "uuid",
    "benchmarks": [...],
    "stop_reason": "converged"
}
```

## Non-Negotiable Truth Rule

**LLMs/agents may propose objectives, scenarios, and reasoning, but they must NEVER fabricate simulation results.**

Every numeric outcome shown to the user:
1. Is produced by the actual simulation/calculation code
2. Is stored in the run ledger (`metric_results` table)
3. Has a reproducible hash and seed
4. Can be verified by replay

## Run Ledger (Audit Trail)

All results are stored in PostgreSQL:

| Table | Contents |
|-------|----------|
| `runs` | Run configuration and status |
| `scenarios` | Scenario definitions with hashes |
| `scenario_instances` | Execution instances |
| `simulation_jobs` | Job tracking |
| `metric_results` | Computed metrics |
| `uncertainty_results` | Confidence intervals |
| `judge_scores` | Final scores |
| `artifacts` | MinIO object keys and checksums |

## How to Run

### 1. Start a Run via API

```bash
curl -X POST http://localhost:8000/api/runs/start \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "prompt": "Find the best asset allocation for maximum returns",
    "domain_pack": "FinancePack",
    "config": {
      "maxScenarios": 100,
      "maxWallTime": 600
    }
  }'
```

### 2. Monitor Progress

```bash
# SSE stream
curl http://localhost:8000/api/runs/<run_id>/stream

# Or poll status
curl http://localhost:8000/api/runs/<run_id>
```

### 3. View Results

The response includes:
- `status`: "running" | "completed" | "failed"
- `stages`: List of completed pipeline stages
- `counters`: Scenarios proposed/simulated/promoted
- `candidates`: Top ranked scenarios with scores
- `current_best`: Best scenario so far

## Proving the System Works

Run the smoke tests:

```bash
pytest tests/test_smoke_e2e.py -v
```

These tests prove:
1. Different prompts → Different ObjectiveSpecs
2. Different prompts → Different scenario rankings
3. Runs have scenarios > 0, simulations > 0, results > 0
4. Same seed → Reproducible outputs

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                         User Question                             │
│         "Reduce pollution in Delhi" / "Maximize returns"         │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                    API Gateway (FastAPI)                          │
│                    POST /api/runs/start                           │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                 Orchestrator (Temporal Workflow)                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐   │
│  │ Formalize   │→ │ Generate    │→ │ Execute Simulations    │   │
│  │ Objectives  │  │ Scenarios   │  │ (Ray Workers)          │   │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘   │
│         │                                      │                  │
│         ▼                                      ▼                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐   │
│  │ Evidence    │  │ Optimizer   │← │ Score & Rank            │   │
│  │ Pack        │  │ Loop        │  │ (Judge Service)         │   │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘   │
│                          │                                        │
│                          ▼                                        │
│                 ┌─────────────────┐                              │
│                 │ Final Report    │                              │
│                 │ + Top Scenarios │                              │
│                 └─────────────────┘                              │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Storage Layer                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │PostgreSQL│  │  MinIO   │  │  Redis   │  │     Milvus       │  │
│  │ (Ledger) │  │(Artifacts)│ │ (Cache)  │  │   (Embeddings)   │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## Files Changed in This Update

1. **Created**: `compute/domain_packs/sdk/` - Core SDK with types and registry
2. **Created**: `compute/domain_packs/toy_pack/` - Minimal test domain pack
3. **Updated**: `services/orchestrator/activities/pipeline.py` - Real objective formalization
4. **Updated**: `services/orchestrator/activities/formalizer.py` - NEW: Question parsing
5. **Updated**: `services/api/routers/runs.py` - Proper run_spec wiring
6. **Updated**: `services/orchestrator/workflows/simulation_run.py` - Handle run_spec dict
7. **Created**: `tests/test_smoke_e2e.py` - Comprehensive smoke tests
8. **Created**: `compute/domain_packs/__init__.py` - Pack imports
9. **Created**: `compute/domain_packs/finance_pack/__init__.py` - Package init
