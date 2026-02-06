# SpatialPack

Grid-based diffusion simulation with heatmap output.

## Overview

SpatialPack simulates the spread of a quantity (e.g., air pollution, heat, 
contamination) across a 2D grid using diffusion equations with:
- Multiple configurable sources
- Wind advection effects
- Natural decay
- Multi-level threshold analysis
- Masked heatmap visualization

## State Schema

```python
class SpatialState:
    grid_size: int           # Grid dimensions (NxN)
    diffusion_rate: float    # Diffusion coefficient [0-1]
    decay_rate: float        # Natural decay rate [0-1]
    wind_x: float            # Wind in X direction [-1, 1]
    wind_y: float            # Wind in Y direction [-1, 1]
    time_steps: int          # Simulation duration
    safe_threshold: float    # Safe concentration level
    warning_threshold: float # Warning level
    critical_threshold: float # Critical level
```

## Action Schema

```python
class GridSource:
    x: int           # X coordinate on grid
    y: int           # Y coordinate on grid
    intensity: float # Source strength
    radius: float    # Initial spread radius

class SpatialActions:
    sources: List[GridSource]  # Pollution sources
    mitigation_zones: List     # Zones with reduced diffusion
```

## Metrics

- `coverage_ratio`: Fraction of grid with non-zero concentration
- `max_concentration`: Maximum concentration value
- `mean_concentration`: Average concentration
- `safe_area_ratio`: Fraction of grid below safe threshold
- `warning_area_ratio`: Fraction in warning zone
- `critical_area_ratio`: Fraction above critical threshold
- `threshold_violations`: Count of critical cells

## Fidelity Levels

- **CHEAP**: 25% resolution, high noise, fast
- **MID**: 50% resolution, medium noise
- **HIGH**: Full resolution, low noise, accurate

## Masked Heatmaps

Generate various masked views of the results:

```python
pack = SpatialPack()

# Run simulation...

# Threshold mask (show cells above 0.5)
masked = pack.generate_masked_heatmap(
    outcome,
    mask_type="threshold",
    threshold=0.5
)

# Top-K mask (show top 100 values)
masked = pack.generate_masked_heatmap(
    outcome,
    mask_type="top_k",
    k=100
)

# Violations mask (show critical areas only)
masked = pack.generate_masked_heatmap(
    outcome,
    mask_type="violations"
)
```

## Example

```python
from domain_packs.spatial_pack import SpatialPack
from domain_packs.sdk import Fidelity

pack = SpatialPack()

state = pack.validate_state({
    "grid_size": 100,
    "diffusion_rate": 0.1,
    "wind_x": 0.05,
    "wind_y": 0.02,
    "time_steps": 100,
})

actions = pack.validate_actions({
    "sources": [
        {"x": 25, "y": 25, "intensity": 2.0, "radius": 5.0},
        {"x": 75, "y": 75, "intensity": 1.5, "radius": 3.0},
    ]
})

outcome = pack.simulate(
    state=state,
    actions=actions,
    fidelity=Fidelity.MID,
    seed=42,
    scenario_id="diffusion-001",
    run_id="run-001",
)

# Get metrics
metrics = pack.score(outcome, None)
for m in metrics.metrics:
    print(f"{m.name}: {m.value:.4f}")

# Generate heatmap for visualization
heatmap = pack.generate_masked_heatmap(outcome, mask_type="threshold", threshold=0.3)
print(f"Cells above threshold: {heatmap['masked_cells']}")
```

## Applications

- Air quality modeling
- Heat distribution analysis
- Contamination spread
- Urban planning simulations
- Environmental impact assessment
