"""SpatialPack - Grid-based diffusion simulation with heatmap output."""
import time
from typing import Dict, List, Optional, Type

import numpy as np
from pydantic import BaseModel, Field

from ..sdk import (
    DomainPackBase,
    DomainPackRegistry,
    Fidelity,
    OutcomeBundle,
    MetricBundle,
    FeasibilityResult,
    CostEstimate,
    ObjectiveSpec,
)
from ..sdk.types import MetricValue


class GridSource(BaseModel):
    """A pollution/concentration source on the grid."""
    x: int = Field(..., ge=0, description="X coordinate")
    y: int = Field(..., ge=0, description="Y coordinate")
    intensity: float = Field(default=1.0, ge=0, description="Source intensity")
    radius: float = Field(default=1.0, ge=0, description="Initial spread radius")


class SpatialState(BaseModel):
    """State for SpatialPack: grid configuration."""
    grid_size: int = Field(default=100, ge=10, le=500, description="Grid size (NxN)")
    
    # Environmental parameters
    diffusion_rate: float = Field(default=0.1, ge=0, le=1, description="Diffusion coefficient")
    decay_rate: float = Field(default=0.01, ge=0, le=1, description="Natural decay rate")
    wind_x: float = Field(default=0.0, ge=-1, le=1, description="Wind in X direction")
    wind_y: float = Field(default=0.0, ge=-1, le=1, description="Wind in Y direction")
    
    # Simulation duration
    time_steps: int = Field(default=100, ge=1, le=1000, description="Number of time steps")
    
    # Thresholds for evaluation
    safe_threshold: float = Field(default=0.5, description="Safe concentration level")
    warning_threshold: float = Field(default=0.8, description="Warning level")
    critical_threshold: float = Field(default=1.0, description="Critical level")


class SpatialActions(BaseModel):
    """Actions for SpatialPack: source placement."""
    sources: List[GridSource] = Field(
        default_factory=list,
        description="List of pollution sources to place"
    )
    
    # Optional mitigation zones
    mitigation_zones: List[Dict] = Field(
        default_factory=list,
        description="Zones with reduced diffusion"
    )


@DomainPackRegistry.register
class SpatialPack(DomainPackBase):
    """
    SpatialPack: Grid-based diffusion simulation.
    
    Simulates the spread of a quantity (e.g., air pollution, heat)
    across a 2D grid using diffusion equations with:
    - Multiple sources
    - Wind advection
    - Natural decay
    - Threshold violations
    
    Outputs masked heatmaps for visualization.
    """
    
    name = "spatial-pack"
    version = "1.0.0"
    description = "Grid diffusion simulation with heatmap output (air quality, heat, etc.)"
    metrics = [
        "coverage_ratio",
        "max_concentration",
        "mean_concentration",
        "safe_area_ratio",
        "warning_area_ratio",
        "critical_area_ratio",
        "threshold_violations",
    ]
    fidelity_modes = [Fidelity.CHEAP, Fidelity.MID, Fidelity.HIGH]
    
    def state_schema(self) -> Type[BaseModel]:
        return SpatialState
    
    def action_schema(self) -> Type[BaseModel]:
        return SpatialActions
    
    def _initialize_grid(
        self,
        state: SpatialState,
        actions: SpatialActions,
    ) -> np.ndarray:
        """Initialize grid with sources."""
        grid = np.zeros((state.grid_size, state.grid_size))
        
        for source in actions.sources:
            if 0 <= source.x < state.grid_size and 0 <= source.y < state.grid_size:
                # Apply Gaussian-like source
                for i in range(state.grid_size):
                    for j in range(state.grid_size):
                        dist = np.sqrt((i - source.x) ** 2 + (j - source.y) ** 2)
                        if dist <= source.radius * 3:
                            contribution = source.intensity * np.exp(-dist ** 2 / (2 * source.radius ** 2))
                            grid[i, j] += contribution
        
        return grid
    
    def _diffusion_step(
        self,
        grid: np.ndarray,
        state: SpatialState,
        rng: np.random.RandomState,
        noise_level: float,
    ) -> np.ndarray:
        """Perform one diffusion step."""
        n = grid.shape[0]
        new_grid = np.zeros_like(grid)
        
        # Diffusion using finite differences
        for i in range(n):
            for j in range(n):
                # Get neighbors with boundary handling
                up = grid[max(0, i-1), j]
                down = grid[min(n-1, i+1), j]
                left = grid[i, max(0, j-1)]
                right = grid[i, min(n-1, j+1)]
                center = grid[i, j]
                
                # Laplacian for diffusion
                laplacian = up + down + left + right - 4 * center
                
                # Advection (wind effect)
                advection = 0.0
                if state.wind_x > 0 and i > 0:
                    advection += state.wind_x * (center - grid[i-1, j])
                elif state.wind_x < 0 and i < n-1:
                    advection += state.wind_x * (grid[i+1, j] - center)
                    
                if state.wind_y > 0 and j > 0:
                    advection += state.wind_y * (center - grid[i, j-1])
                elif state.wind_y < 0 and j < n-1:
                    advection += state.wind_y * (grid[i, j+1] - center)
                
                # Update with diffusion, advection, and decay
                new_value = center + state.diffusion_rate * laplacian - advection - state.decay_rate * center
                
                # Add noise
                new_value += rng.normal(0, noise_level)
                
                # Ensure non-negative
                new_grid[i, j] = max(0, new_value)
        
        return new_grid
    
    def simulate(
        self,
        state: SpatialState,
        actions: SpatialActions,
        fidelity: Fidelity,
        seed: int,
        scenario_id: str,
        run_id: str,
    ) -> OutcomeBundle:
        """Run diffusion simulation."""
        start_time = time.perf_counter()
        
        rng = np.random.RandomState(seed)
        
        # Adjust resolution based on fidelity
        resolution_factor = {
            Fidelity.CHEAP: 0.25,
            Fidelity.MID: 0.5,
            Fidelity.HIGH: 1.0,
        }[fidelity]
        
        effective_size = max(10, int(state.grid_size * resolution_factor))
        
        # Scale sources
        scaled_actions = SpatialActions(
            sources=[
                GridSource(
                    x=int(s.x * resolution_factor),
                    y=int(s.y * resolution_factor),
                    intensity=s.intensity,
                    radius=s.radius * resolution_factor,
                )
                for s in actions.sources
            ]
        )
        
        scaled_state = state.model_copy(update={"grid_size": effective_size})
        
        # Initialize grid
        grid = self._initialize_grid(scaled_state, scaled_actions)
        
        # Noise levels
        noise_levels = {
            Fidelity.CHEAP: 0.01,
            Fidelity.MID: 0.005,
            Fidelity.HIGH: 0.001,
        }
        
        # Run simulation
        time_step_factor = {
            Fidelity.CHEAP: 10,
            Fidelity.MID: 5,
            Fidelity.HIGH: 1,
        }[fidelity]
        
        actual_steps = max(1, state.time_steps // time_step_factor)
        
        trajectory = []
        for t in range(actual_steps):
            grid = self._diffusion_step(grid, scaled_state, rng, noise_levels[fidelity])
            
            # Record every 10th step for trajectory
            if t % 10 == 0:
                trajectory.append({
                    "step": t,
                    "max": float(np.max(grid)),
                    "mean": float(np.mean(grid)),
                })
        
        # Upscale result if needed
        if effective_size != state.grid_size:
            from scipy.ndimage import zoom
            try:
                scale_factor = state.grid_size / effective_size
                grid = zoom(grid, scale_factor, order=1)
            except ImportError:
                # Fallback: simple repeat
                grid = np.repeat(np.repeat(grid, int(1/resolution_factor), axis=0), int(1/resolution_factor), axis=1)
                grid = grid[:state.grid_size, :state.grid_size]
        
        execution_time = max((time.perf_counter() - start_time) * 1000, 0.001)
        
        # Create heatmap data
        heatmap = grid.tolist()
        
        return OutcomeBundle(
            scenario_id=scenario_id,
            run_id=run_id,
            final_state={
                "heatmap": heatmap,
                "grid_size": state.grid_size,
                "max_concentration": float(np.max(grid)),
                "mean_concentration": float(np.mean(grid)),
            },
            trajectory=trajectory,
            fidelity=fidelity,
            seed=seed,
            execution_time_ms=execution_time,
            domain_pack_name=self.name,
            domain_pack_version=self.version,
            artifacts={
                "safe_threshold": state.safe_threshold,
                "warning_threshold": state.warning_threshold,
                "critical_threshold": state.critical_threshold,
            },
            raw_output={"grid": grid},
        )
    
    def score(
        self,
        outcome: OutcomeBundle,
        objectives: Optional[ObjectiveSpec] = None,
    ) -> MetricBundle:
        """Compute spatial metrics."""
        grid = outcome.raw_output.get("grid")
        if grid is None:
            grid = np.array(outcome.final_state.get("heatmap", [[0]]))
        
        total_cells = grid.size
        
        # Thresholds from artifacts
        safe_t = outcome.artifacts.get("safe_threshold", 0.5)
        warn_t = outcome.artifacts.get("warning_threshold", 0.8)
        crit_t = outcome.artifacts.get("critical_threshold", 1.0)
        
        # Compute areas
        safe_cells = np.sum(grid < safe_t)
        warning_cells = np.sum((grid >= safe_t) & (grid < warn_t))
        critical_cells = np.sum(grid >= crit_t)
        
        # Coverage (cells with any concentration > 0.01)
        coverage = np.sum(grid > 0.01) / total_cells
        
        # Threshold violations
        violations = np.sum(grid >= crit_t)
        
        metrics = [
            MetricValue(name="coverage_ratio", value=float(coverage)),
            MetricValue(name="max_concentration", value=float(np.max(grid))),
            MetricValue(name="mean_concentration", value=float(np.mean(grid))),
            MetricValue(name="safe_area_ratio", value=float(safe_cells / total_cells)),
            MetricValue(name="warning_area_ratio", value=float(warning_cells / total_cells)),
            MetricValue(name="critical_area_ratio", value=float(critical_cells / total_cells)),
            MetricValue(name="threshold_violations", value=float(violations)),
        ]
        
        # Feasible if critical area is below 10%
        is_feasible = (critical_cells / total_cells) < 0.1
        
        return MetricBundle(
            scenario_id=outcome.scenario_id,
            run_id=outcome.run_id,
            metrics=metrics,
            is_feasible=is_feasible,
            constraint_violations={"critical_area": float(critical_cells / total_cells)} if not is_feasible else {},
        )
    
    def feasibility(
        self,
        state: SpatialState,
        actions: SpatialActions,
    ) -> FeasibilityResult:
        """Check spatial configuration feasibility."""
        violations = []
        magnitudes = {}
        warnings = []
        
        # Check sources are within grid
        for i, source in enumerate(actions.sources):
            if source.x < 0 or source.x >= state.grid_size:
                violations.append(f"Source {i} x={source.x} out of grid bounds")
            if source.y < 0 or source.y >= state.grid_size:
                violations.append(f"Source {i} y={source.y} out of grid bounds")
            if source.intensity > 10:
                warnings.append(f"Source {i} has very high intensity ({source.intensity})")
        
        # Check for excessive sources
        if len(actions.sources) > 100:
            violations.append(f"Too many sources ({len(actions.sources)} > 100)")
        
        return FeasibilityResult(
            is_feasible=len(violations) == 0,
            violations=violations,
            violation_magnitudes=magnitudes,
            warnings=warnings,
        )
    
    def cost_model(self, fidelity: Fidelity) -> CostEstimate:
        """Estimate simulation cost."""
        times = {
            Fidelity.CHEAP: 100.0,
            Fidelity.MID: 500.0,
            Fidelity.HIGH: 2000.0,
        }
        memory = {
            Fidelity.CHEAP: 50.0,
            Fidelity.MID: 100.0,
            Fidelity.HIGH: 400.0,
        }
        return CostEstimate(
            fidelity=fidelity,
            estimated_time_ms=times[fidelity],
            estimated_memory_mb=memory[fidelity],
        )
    
    def generate_masked_heatmap(
        self,
        outcome: OutcomeBundle,
        mask_type: str = "threshold",
        **kwargs,
    ) -> Dict:
        """
        Generate masked heatmap for visualization.
        
        Mask types:
        - threshold: Show cells above a threshold
        - delta: Show change from baseline
        - top_k: Show top K values
        - violations: Show threshold violations
        - confidence: Mask by confidence level
        """
        grid = outcome.raw_output.get("grid")
        if grid is None:
            grid = np.array(outcome.final_state.get("heatmap", [[0]]))
        
        mask = np.ones_like(grid, dtype=bool)
        
        if mask_type == "threshold":
            threshold = kwargs.get("threshold", 0.5)
            mask = grid >= threshold
            
        elif mask_type == "delta":
            baseline = kwargs.get("baseline", 0.0)
            delta = kwargs.get("delta", 0.1)
            mask = np.abs(grid - baseline) >= delta
            
        elif mask_type == "top_k":
            k = kwargs.get("k", 100)
            threshold = np.sort(grid.flatten())[-k] if grid.size >= k else 0
            mask = grid >= threshold
            
        elif mask_type == "violations":
            critical = outcome.artifacts.get("critical_threshold", 1.0)
            mask = grid >= critical
            
        elif mask_type == "confidence":
            # For demonstration - would need actual confidence data
            mask = np.ones_like(grid, dtype=bool)
        
        # Apply mask
        masked_grid = np.where(mask, grid, np.nan)
        
        return {
            "heatmap": masked_grid.tolist(),
            "mask": mask.tolist(),
            "mask_type": mask_type,
            "masked_cells": int(np.sum(mask)),
            "total_cells": int(grid.size),
            "grid_size": grid.shape[0],
        }
