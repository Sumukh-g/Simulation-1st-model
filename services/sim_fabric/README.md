# GSIP Simulation Fabric

Ray-based distributed simulation execution service with full observability.

## Overview

The Simulation Fabric provides:
- Distributed simulation execution using Ray worker pools
- Domain pack loading by name and version
- Isolation strategies (none, subprocess, container stub)
- Batch execution API with deterministic seeds
- Result caching via Redis (keyed by scenario hash)
- Artifact pipeline storing to MinIO with checksums
- Downsampled previews and PNG heatmap generation
- Built-in invariant checks (bounds, NaN/Inf, conservation)
- Prometheus metrics and tracing for every job

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Simulation Fabric                         │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              SimulationFabric                          │ │
│  │   - Worker pool management                             │ │
│  │   - Batch execution                                    │ │
│  │   - Caching layer                                      │ │
│  └────────────────────────────────────────────────────────┘ │
│              │                                               │
│  ┌───────────┼────────────┬────────────┐                    │
│  ▼           ▼            ▼            ▼                    │
│ ┌─────┐   ┌─────┐     ┌─────┐     ┌─────┐                  │
│ │Worker│  │Worker│    │Worker│    │Worker│  (per pack)      │
│ │Pool 1│  │Pool 2│    │Pool 3│    │Pool N│                  │
│ └─────┘   └─────┘     └─────┘     └─────┘                  │
│     │                                                        │
│     ▼                                                        │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │               Per-Job Pipeline                          │ │
│ │  ┌──────────┐  ┌──────────┐  ┌──────────┐              │ │
│ │  │ Invariant│  │ Artifact │  │ Metrics/ │              │ │
│ │  │ Checks   │  │ Storage  │  │ Tracing  │              │ │
│ │  └──────────┘  └──────────┘  └──────────┘              │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   ┌────────┐  ┌────────┐  ┌────────┐
   │  Ray   │  │  Redis │  │  MinIO │
   │Cluster │  │ Cache  │  │Artifacts│
   └────────┘  └────────┘  └────────┘
```

## Modules

### executor.py
Main simulation fabric and worker pool management.

### invariants.py
Built-in invariant checks:
- **Bounds checks**: Detect values outside reasonable ranges
- **NaN/Inf detection**: Find invalid floating point values
- **Spatial conservation**: Validate mass/energy conservation for SpatialPack
- **Schema completeness**: Ensure required fields are present

### artifacts.py
Artifact pipeline for MinIO storage:
- Store raw bytes, JSON, numpy arrays
- Compute SHA-256 checksums
- Downsample 2D arrays for preview
- Generate PNG heatmaps with colormaps
- Tile generation for large arrays

### cache.py
Redis-based result caching:
- Scenario hash computation (deterministic)
- TTL-based expiration (7 days default)
- Batch get/set operations

### tracing.py
Prometheus metrics and tracing:
- Simulation duration histogram
- Active simulations gauge
- Invariant violation counter
- Cache hit/miss counters
- Artifact size histogram
- Span-based tracing

### isolation.py
Isolation strategies for domain pack execution:
- **None**: Run in current process (default)
- **Subprocess**: Fresh Python process per simulation
- **Container**: Docker container stub (for production)

## Usage

### Basic Batch Execution

```python
from services.sim_fabric import get_fabric

fabric = get_fabric()

scenarios = [
    {
        "state": {"x": 0, "y": 0, "target_x": 10, "target_y": 10},
        "actions": {"dx": 1, "dy": 1, "steps": 10},
        "fidelity": "mid",
        "seed": i,
        "scenario_id": f"s-{i}",
        "run_id": "run-001",
    }
    for i in range(100)
]

results = await fabric.run_batch(
    domain_pack_name="toy-pack",
    domain_pack_version="1.0.0",
    scenarios=scenarios,
    store_artifacts=True,
)

for result in results:
    print(f"Scenario {result['scenario_id']}: {result['status']}")
    if result.get("invariant_report"):
        print(f"  Invariants passed: {result['invariant_report']['passed']}")
    if result.get("cached"):
        print("  (from cache)")
```

### Single Simulation

```python
result = await fabric.run_single(
    domain_pack_name="spatial-pack",
    domain_pack_version="1.0.0",
    state={"grid_size": 100, "diffusion_rate": 0.1},
    actions={"sources": [{"x": 50, "y": 50, "intensity": 1.0}]},
    fidelity="high",
    seed=42,
    scenario_id="s-001",
    run_id="r-001",
)
```

### With Custom Isolation

```python
fabric = SimulationFabric(
    pool_size=8,
    isolation_mode="subprocess",  # or "container"
)
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `RAY_ADDRESS` | `ray://localhost:10001` | Ray cluster address |
| `RAY_NUM_CPUS` | `4` | CPUs per worker |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis cache URL |
| `MINIO_ENDPOINT` | `localhost:9000` | MinIO endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `MINIO_BUCKET` | `gsip-artifacts` | Artifacts bucket |
| `MAX_CONCURRENT_SIMULATIONS` | `100` | Max concurrent sims |
| `DEFAULT_TIMEOUT_SECONDS` | `300` | Simulation timeout |

## Metrics

Prometheus metrics exposed:
- `sim_fabric_simulation_duration_seconds` - Duration histogram
- `sim_fabric_simulations_total` - Counter by status
- `sim_fabric_active_simulations` - Gauge of running sims
- `sim_fabric_invariant_violations_total` - Violation counter
- `sim_fabric_cache_hits_total` / `cache_misses_total`
- `sim_fabric_artifact_size_bytes` - Artifact size histogram

## Worker Lifecycle

1. Workers are created on-demand per domain pack version
2. Workers load pack once and reuse across simulations
3. Worker pools are sized based on configuration
4. Shutdown cleans up all workers gracefully
