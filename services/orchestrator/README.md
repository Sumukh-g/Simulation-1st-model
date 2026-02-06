# GSIP Orchestrator Service

Temporal-based workflow orchestration for simulation runs.

## Overview

The Orchestrator manages the execution of simulation runs using Temporal
durable workflows, providing:
- Reliable execution with automatic retries
- Workflow state persistence
- Query and signal support
- Long-running optimization loops

## Workflows

### SimulationRunWorkflow

Main workflow for executing a complete simulation run:
1. Generate scenarios based on specification
2. Execute simulations in batches (via Sim Fabric)
3. Score outcomes (via Judge service)
4. Aggregate results
5. Seal run (make immutable)

### OptimizationLoopWorkflow

Iterative optimization workflow:
1. Initialize optimizer (Bayesian/evolutionary)
2. Loop until converged or budget exhausted:
   - Propose next batch of scenarios
   - Execute simulations
   - Score outcomes
   - Update optimizer model
   - Check convergence
3. Compute Pareto frontier (for multi-objective)

## Activities

### Simulation Activities
- `generate_scenarios`: Create scenarios from run spec
- `execute_simulation_batch`: Run simulations via Sim Fabric
- `score_outcomes`: Score results via Judge
- `aggregate_results`: Compute run summary
- `seal_run`: Make run immutable

### Optimization Activities
- `initialize_optimizer`: Setup optimizer state
- `propose_next_batch`: Get next scenarios to try
- `update_optimizer`: Update with new results
- `check_convergence`: Check if optimization converged
- `get_pareto_frontier`: Compute non-dominated solutions

## Running the Worker

```bash
cd services/orchestrator
python -m worker
```

## Configuration

Environment variables:
- `TEMPORAL_HOST`: Temporal server address
- `TEMPORAL_NAMESPACE`: Temporal namespace
- `TEMPORAL_TASK_QUEUE`: Task queue name

## Starting a Workflow

```python
from temporalio.client import Client

client = await Client.connect("localhost:7233")

run_spec = {
    "run_id": "run-001",
    "domain_pack_id": "toy-pack",
    "domain_pack_version": "1.0.0",
    "budget": 100,
    "objectives": {"type": "maximize", "metrics": ["score"]},
}

handle = await client.start_workflow(
    "SimulationRunWorkflow",
    run_spec,
    id=f"sim-run-{run_spec['run_id']}",
    task_queue="gsip-main",
)

result = await handle.result()
```
