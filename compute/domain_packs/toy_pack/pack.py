"""ToyPack - A minimal domain pack for testing the simulation pipeline."""
import math
import time
from typing import Dict, Optional, Type

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


class ToyState(BaseModel):
    """State for ToyPack: simple 2D position."""
    x: float = Field(default=0.0, description="Current X position")
    y: float = Field(default=0.0, description="Current Y position")
    target_x: float = Field(default=10.0, description="Target X position")
    target_y: float = Field(default=10.0, description="Target Y position")
    noise_level: float = Field(default=0.1, ge=0.0, le=1.0, description="Noise level")


class ToyActions(BaseModel):
    """Actions for ToyPack: movement parameters."""
    dx: float = Field(default=1.0, ge=-10.0, le=10.0, description="X velocity")
    dy: float = Field(default=1.0, ge=-10.0, le=10.0, description="Y velocity")
    steps: int = Field(default=10, ge=1, le=1000, description="Number of steps")


@DomainPackRegistry.register
class ToyPack(DomainPackBase):
    """
    ToyPack: A minimal domain pack for testing.
    
    Simulates a simple 2D random walk toward a target.
    Metrics include:
    - distance: Final distance to target
    - efficiency: How efficiently the path reached the target
    - score: Combined score (lower distance = higher score)
    """
    
    name = "toy-pack"
    version = "1.0.0"
    description = "Minimal 2D random walk simulation for testing"
    metrics = ["distance", "efficiency", "score", "path_length", "steps_taken"]
    fidelity_modes = [Fidelity.CHEAP, Fidelity.MID, Fidelity.HIGH]
    
    def state_schema(self) -> Type[BaseModel]:
        return ToyState
    
    def action_schema(self) -> Type[BaseModel]:
        return ToyActions
    
    def simulate(
        self,
        state: ToyState,
        actions: ToyActions,
        fidelity: Fidelity,
        seed: int,
        scenario_id: str,
        run_id: str,
    ) -> OutcomeBundle:
        """Run the toy simulation."""
        start_time = time.perf_counter()
        rng = np.random.RandomState(seed)
        
        # Fidelity affects precision/noise
        noise_multipliers = {
            Fidelity.CHEAP: 2.0,
            Fidelity.MID: 1.0,
            Fidelity.HIGH: 0.5,
        }
        noise_mult = noise_multipliers[fidelity]
        
        # Time step resolution
        step_factors = {
            Fidelity.CHEAP: 1,
            Fidelity.MID: 5,
            Fidelity.HIGH: 10,
        }
        sub_steps = step_factors[fidelity]
        
        # Initialize position
        x, y = state.x, state.y
        trajectory = [{"step": 0, "x": x, "y": y}]
        path_length = 0.0
        
        # Simulate movement
        total_steps = actions.steps * sub_steps
        dx_per_step = actions.dx / sub_steps
        dy_per_step = actions.dy / sub_steps
        
        for step in range(1, total_steps + 1):
            # Add noise
            noise_x = rng.normal(0, state.noise_level * noise_mult)
            noise_y = rng.normal(0, state.noise_level * noise_mult)
            
            # Move
            new_x = x + dx_per_step + noise_x
            new_y = y + dy_per_step + noise_y
            
            # Track path length
            path_length += math.sqrt((new_x - x) ** 2 + (new_y - y) ** 2)
            
            x, y = new_x, new_y
            
            # Record trajectory at original step intervals
            if step % sub_steps == 0:
                trajectory.append({
                    "step": step // sub_steps,
                    "x": x,
                    "y": y,
                })
        
        # Compute final distance to target
        final_distance = math.sqrt(
            (x - state.target_x) ** 2 + (y - state.target_y) ** 2
        )
        
        # Compute ideal distance
        ideal_distance = math.sqrt(
            (state.target_x - state.x) ** 2 + (state.target_y - state.y) ** 2
        )
        
        execution_time = max((time.perf_counter() - start_time) * 1000, 0.001)
        
        return OutcomeBundle(
            scenario_id=scenario_id,
            run_id=run_id,
            final_state={
                "x": x,
                "y": y,
                "final_distance": final_distance,
                "path_length": path_length,
            },
            trajectory=trajectory,
            fidelity=fidelity,
            seed=seed,
            execution_time_ms=execution_time,
            domain_pack_name=self.name,
            domain_pack_version=self.version,
            artifacts={
                "target_x": state.target_x,
                "target_y": state.target_y,
                "ideal_distance": ideal_distance,
            },
            raw_output={
                "final_x": x,
                "final_y": y,
                "total_steps": total_steps,
            },
        )
    
    def score(
        self,
        outcome: OutcomeBundle,
        objectives: Optional[ObjectiveSpec] = None,
    ) -> MetricBundle:
        """Compute metrics from the simulation outcome."""
        final_state = outcome.final_state
        artifacts = outcome.artifacts
        
        final_distance = final_state.get("final_distance", 0.0)
        path_length = final_state.get("path_length", 1.0)
        ideal_distance = artifacts.get("ideal_distance", 1.0)
        
        # Efficiency: how close the path length is to ideal straight line
        efficiency = ideal_distance / max(path_length, 0.001)
        efficiency = min(1.0, efficiency)  # Cap at 1.0
        
        # Score: higher is better, so we invert distance
        max_expected_distance = ideal_distance * 2  # Reasonable upper bound
        score = max(0, 1 - (final_distance / max(max_expected_distance, 0.001)))
        
        metrics = [
            MetricValue(name="distance", value=float(final_distance)),
            MetricValue(name="efficiency", value=float(efficiency)),
            MetricValue(name="score", value=float(score)),
            MetricValue(name="path_length", value=float(path_length)),
            MetricValue(name="steps_taken", value=float(outcome.raw_output.get("total_steps", 0))),
        ]
        
        return MetricBundle(
            scenario_id=outcome.scenario_id,
            run_id=outcome.run_id,
            metrics=metrics,
            is_feasible=True,
        )
    
    def feasibility(
        self,
        state: ToyState,
        actions: ToyActions,
    ) -> FeasibilityResult:
        """Check feasibility of state/action combination."""
        violations = []
        warnings = []
        magnitudes = {}
        
        # Check for unreasonable step counts
        if actions.steps > 500:
            warnings.append(f"High step count ({actions.steps}) may be slow")
        
        # Check for extreme velocities
        total_velocity = math.sqrt(actions.dx ** 2 + actions.dy ** 2)
        if total_velocity > 15:
            violations.append(f"Velocity magnitude ({total_velocity:.2f}) exceeds limit")
            magnitudes["velocity"] = total_velocity - 15
        
        # Check for zero movement
        if actions.dx == 0 and actions.dy == 0:
            warnings.append("Zero velocity - position will only change due to noise")
        
        return FeasibilityResult(
            is_feasible=len(violations) == 0,
            violations=violations,
            violation_magnitudes=magnitudes,
            warnings=warnings,
        )
    
    def cost_model(self, fidelity: Fidelity) -> CostEstimate:
        """Estimate simulation cost."""
        times = {
            Fidelity.CHEAP: 10.0,
            Fidelity.MID: 50.0,
            Fidelity.HIGH: 200.0,
        }
        memory = {
            Fidelity.CHEAP: 5.0,
            Fidelity.MID: 10.0,
            Fidelity.HIGH: 20.0,
        }
        return CostEstimate(
            fidelity=fidelity,
            estimated_time_ms=times[fidelity],
            estimated_memory_mb=memory[fidelity],
        )
    
    def get_action_ranges(self) -> Dict:
        """Get action parameter ranges for scenario generation."""
        return {
            "dx": {"min": -10.0, "max": 10.0},
            "dy": {"min": -10.0, "max": 10.0},
            "steps": {"min": 1, "max": 100},
        }
