"""Base class for Domain Packs."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel

from .types import (
    CostEstimate,
    Fidelity,
    FeasibilityResult,
    MetricBundle,
    ObjectiveSpec,
    OutcomeBundle,
)


class DomainPackBase(ABC):
    """
    Abstract base class for all domain packs.
    
    Every domain pack must implement:
    - state_schema(): Returns the Pydantic model for state validation
    - action_schema(): Returns the Pydantic model for action validation
    - simulate(): Runs the actual simulation
    - score(): Computes metrics from simulation outcome
    - feasibility(): Checks if a state/action pair is feasible
    - cost_model(): Estimates computational cost for a fidelity level
    """
    
    # Class attributes that subclasses should override
    name: str = "base-pack"
    version: str = "0.0.0"
    description: str = "Base domain pack"
    metrics: List[str] = []
    fidelity_modes: List[Fidelity] = [Fidelity.CHEAP, Fidelity.MID, Fidelity.HIGH]
    
    @abstractmethod
    def state_schema(self) -> Type[BaseModel]:
        """Return the Pydantic model for state validation."""
        raise NotImplementedError
    
    @abstractmethod
    def action_schema(self) -> Type[BaseModel]:
        """Return the Pydantic model for action validation."""
        raise NotImplementedError
    
    def validate_state(self, state: Dict[str, Any]) -> BaseModel:
        """Validate and parse state dictionary."""
        schema = self.state_schema()
        return schema.model_validate(state)
    
    def validate_actions(self, actions: Dict[str, Any]) -> BaseModel:
        """Validate and parse actions dictionary."""
        schema = self.action_schema()
        return schema.model_validate(actions)
    
    @abstractmethod
    def simulate(
        self,
        state: BaseModel,
        actions: BaseModel,
        fidelity: Fidelity,
        seed: int,
        scenario_id: str,
        run_id: str,
    ) -> OutcomeBundle:
        """
        Run the simulation.
        
        Args:
            state: Validated state object
            actions: Validated actions object
            fidelity: Simulation fidelity level
            seed: Random seed for reproducibility
            scenario_id: Unique identifier for this scenario
            run_id: Unique identifier for the run
            
        Returns:
            OutcomeBundle with simulation results
        """
        raise NotImplementedError
    
    @abstractmethod
    def score(
        self,
        outcome: OutcomeBundle,
        objectives: Optional[ObjectiveSpec] = None,
    ) -> MetricBundle:
        """
        Compute metrics from simulation outcome.
        
        Args:
            outcome: The simulation outcome
            objectives: Optional objective specification for weighted scoring
            
        Returns:
            MetricBundle with computed metrics
        """
        raise NotImplementedError
    
    @abstractmethod
    def feasibility(
        self,
        state: BaseModel,
        actions: BaseModel,
    ) -> FeasibilityResult:
        """
        Check if a state/action pair is feasible before simulation.
        
        Args:
            state: Validated state object
            actions: Validated actions object
            
        Returns:
            FeasibilityResult indicating if simulation can proceed
        """
        raise NotImplementedError
    
    @abstractmethod
    def cost_model(self, fidelity: Fidelity) -> CostEstimate:
        """
        Estimate computational cost for a fidelity level.
        
        Args:
            fidelity: The fidelity level
            
        Returns:
            CostEstimate with time and resource estimates
        """
        raise NotImplementedError
    
    def get_action_ranges(self) -> Dict[str, Any]:
        """
        Get the valid ranges for action parameters.
        
        Returns a dictionary mapping parameter names to their bounds.
        Used by scenario generation to create valid action combinations.
        """
        schema = self.action_schema()
        ranges = {}
        
        for field_name, field_info in schema.model_fields.items():
            # Check for numeric bounds
            if hasattr(field_info, 'annotation'):
                annotation = field_info.annotation
                # Handle numeric types
                if annotation in (int, float) or str(annotation).startswith(('int', 'float')):
                    # Try to get bounds from field metadata
                    ge = getattr(field_info, 'ge', None)
                    le = getattr(field_info, 'le', None)
                    gt = getattr(field_info, 'gt', None)
                    lt = getattr(field_info, 'lt', None)
                    
                    min_val = ge if ge is not None else (gt + 0.001 if gt is not None else None)
                    max_val = le if le is not None else (lt - 0.001 if lt is not None else None)
                    
                    if min_val is not None or max_val is not None:
                        ranges[field_name] = {
                            "min": min_val if min_val is not None else 0,
                            "max": max_val if max_val is not None else 100,
                        }
                    else:
                        # Default range
                        ranges[field_name] = {"min": 0, "max": 100}
            
            # Handle default values
            if field_info.default is not None and field_name not in ranges:
                ranges[field_name] = field_info.default
        
        return ranges
    
    def get_default_state(self) -> Dict[str, Any]:
        """Get default state for this domain pack."""
        schema = self.state_schema()
        defaults = {}
        for field_name, field_info in schema.model_fields.items():
            if field_info.default is not None:
                defaults[field_name] = field_info.default
            elif field_info.default_factory is not None:
                defaults[field_name] = field_info.default_factory()
        return defaults
    
    def get_metrics_list(self) -> List[str]:
        """Get list of metrics this pack can compute."""
        return self.metrics.copy()
