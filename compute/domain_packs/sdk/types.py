"""Core types for Domain Pack SDK."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Fidelity(str, Enum):
    """Simulation fidelity levels."""
    CHEAP = "cheap"
    MID = "mid"
    HIGH = "high"


class MetricValue(BaseModel):
    """A single metric measurement."""
    name: str
    value: float
    unit: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class OutcomeBundle(BaseModel):
    """Output from a simulation run."""
    scenario_id: str
    run_id: str
    final_state: Dict[str, Any]
    trajectory: List[Dict[str, Any]] = Field(default_factory=list)
    fidelity: Fidelity
    seed: int
    execution_time_ms: float
    domain_pack_name: str
    domain_pack_version: str
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    raw_output: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)


class MetricBundle(BaseModel):
    """Scored metrics from a simulation outcome."""
    scenario_id: str
    run_id: str
    metrics: List[MetricValue]
    is_feasible: bool = True
    constraint_violations: Dict[str, float] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)


class UncertaintyBundle(BaseModel):
    """Uncertainty quantification results."""
    scenario_id: str
    run_id: str
    metric_name: str
    mean: Optional[float] = None
    std: Optional[float] = None
    p05: Optional[float] = None
    p50: Optional[float] = None
    p90: Optional[float] = None
    p95: Optional[float] = None
    samples: Optional[List[float]] = None


class FeasibilityResult(BaseModel):
    """Result of feasibility check."""
    is_feasible: bool
    violations: List[str] = Field(default_factory=list)
    violation_magnitudes: Dict[str, float] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)


class CostEstimate(BaseModel):
    """Estimated cost for a simulation at a given fidelity."""
    fidelity: Fidelity
    estimated_time_ms: float
    estimated_memory_mb: float = 0.0
    estimated_compute_cost: float = 0.0


class ObjectiveMetric(BaseModel):
    """A single objective metric specification."""
    name: str
    direction: str = Field(default="maximize", pattern="^(minimize|maximize)$")
    weight: float = Field(default=1.0, ge=0.0)
    target: Optional[float] = None
    threshold: Optional[float] = None


class Constraint(BaseModel):
    """A constraint specification."""
    name: str
    constraint_type: str = Field(default="max", pattern="^(min|max|eq|range)$")
    value: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    penalty_weight: float = Field(default=1.0, ge=0.0)
    is_hard: bool = False


class ObjectiveSpec(BaseModel):
    """Structured objective specification derived from user question."""
    description: str
    metrics: List[ObjectiveMetric] = Field(default_factory=list)
    primary_direction: str = Field(default="maximize", pattern="^(minimize|maximize)$")
    constraints: List[Constraint] = Field(default_factory=list)
    horizon: Optional[str] = None  # e.g., "1 year", "100 steps"
    context_tags: List[str] = Field(default_factory=list)
    success_criteria: List[str] = Field(default_factory=list)
    required_outputs: List[str] = Field(default_factory=list)
    budget: Optional[Dict[str, float]] = None
    risk_tolerance: Optional[str] = None  # "low", "medium", "high"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self.model_dump()
