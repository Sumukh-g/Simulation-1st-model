"""Constraint handling for optimization."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List


class ConstraintType(str, Enum):
    """Type of constraint."""

    HARD = "hard"  # Must be satisfied, filter out violations
    SOFT = "soft"  # Penalty added to objective


@dataclass
class Constraint:
    """A single constraint definition."""

    name: str
    type: ConstraintType
    check_fn: Callable[[Dict[str, Any], Dict[str, Any]], bool]
    # For soft constraints
    penalty_fn: Callable[[Dict[str, Any], Dict[str, Any]], float] | None = None
    penalty_weight: float = 1.0
    description: str = ""

    def evaluate(
        self,
        params: Dict[str, Any],
        outcome: Dict[str, Any] | None = None,
    ) -> tuple[bool, float]:
        """
        Evaluate constraint.

        Returns:
            (satisfied, penalty) - penalty is 0 if satisfied or hard constraint
        """
        outcome = outcome or {}
        satisfied = self.check_fn(params, outcome)

        if self.type == ConstraintType.HARD:
            return satisfied, 0.0

        if satisfied:
            return True, 0.0

        if self.penalty_fn:
            penalty = self.penalty_fn(params, outcome) * self.penalty_weight
        else:
            penalty = self.penalty_weight

        return False, penalty


@dataclass
class ConstraintReport:
    """Report of constraint evaluation."""

    all_satisfied: bool
    hard_violations: List[str] = field(default_factory=list)
    soft_violations: List[str] = field(default_factory=list)
    total_penalty: float = 0.0
    details: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "all_satisfied": self.all_satisfied,
            "hard_violations": self.hard_violations,
            "soft_violations": self.soft_violations,
            "total_penalty": self.total_penalty,
            "details": self.details,
        }


class ConstraintHandler:
    """Handles constraint evaluation and filtering."""

    def __init__(self, constraints: List[Constraint] | None = None):
        self.constraints = constraints or []
        self._hard_constraints = [c for c in self.constraints if c.type == ConstraintType.HARD]
        self._soft_constraints = [c for c in self.constraints if c.type == ConstraintType.SOFT]

    def add_constraint(self, constraint: Constraint) -> None:
        """Add a constraint."""
        self.constraints.append(constraint)
        if constraint.type == ConstraintType.HARD:
            self._hard_constraints.append(constraint)
        else:
            self._soft_constraints.append(constraint)

    def evaluate(
        self,
        params: Dict[str, Any],
        outcome: Dict[str, Any] | None = None,
    ) -> ConstraintReport:
        """Evaluate all constraints for a candidate."""
        hard_violations = []
        soft_violations = []
        total_penalty = 0.0
        details = {}

        for constraint in self.constraints:
            satisfied, penalty = constraint.evaluate(params, outcome)
            details[constraint.name] = {
                "satisfied": satisfied,
                "penalty": penalty,
                "type": constraint.type.value,
            }

            if not satisfied:
                if constraint.type == ConstraintType.HARD:
                    hard_violations.append(constraint.name)
                else:
                    soft_violations.append(constraint.name)
                    total_penalty += penalty

        return ConstraintReport(
            all_satisfied=len(hard_violations) == 0,
            hard_violations=hard_violations,
            soft_violations=soft_violations,
            total_penalty=total_penalty,
            details=details,
        )

    def filter_feasible(
        self,
        candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Filter candidates to only feasible ones (pass hard constraints)."""
        return [
            c for c in candidates
            if self.evaluate(c).all_satisfied
        ]

    def apply_penalties(
        self,
        params: Dict[str, Any],
        objectives: Dict[str, float],
        outcome: Dict[str, Any] | None = None,
    ) -> Dict[str, float]:
        """Apply soft constraint penalties to objectives."""
        report = self.evaluate(params, outcome)

        if report.total_penalty == 0:
            return objectives

        penalized = objectives.copy()
        # Apply penalty to all objectives (assuming minimizing penalty)
        for obj_name in penalized:
            penalized[obj_name] -= report.total_penalty

        return penalized


# Common constraint builders
def bounds_constraint(
    param_name: str,
    lower: float | None = None,
    upper: float | None = None,
) -> Constraint:
    """Create a bounds constraint for a parameter."""

    def check(params: Dict[str, Any], outcome: Dict[str, Any]) -> bool:
        value = params.get(param_name)
        if value is None:
            return True
        if lower is not None and value < lower:
            return False
        if upper is not None and value > upper:
            return False
        return True

    def penalty(params: Dict[str, Any], outcome: Dict[str, Any]) -> float:
        value = params.get(param_name, 0)
        violation = 0.0
        if lower is not None and value < lower:
            violation = lower - value
        if upper is not None and value > upper:
            violation = value - upper
        return violation

    return Constraint(
        name=f"bounds_{param_name}",
        type=ConstraintType.SOFT,
        check_fn=check,
        penalty_fn=penalty,
        description=f"Bounds for {param_name}: [{lower}, {upper}]",
    )


def metric_threshold_constraint(
    metric_name: str,
    min_value: float | None = None,
    max_value: float | None = None,
    hard: bool = True,
) -> Constraint:
    """Create a constraint on a metric value."""

    def check(params: Dict[str, Any], outcome: Dict[str, Any]) -> bool:
        metrics = outcome.get("metrics", {})
        if isinstance(metrics, list):
            # Handle list of metric dicts
            for m in metrics:
                if m.get("name") == metric_name:
                    value = m.get("value", 0)
                    break
            else:
                return True
        else:
            value = metrics.get(metric_name, 0)

        if min_value is not None and value < min_value:
            return False
        if max_value is not None and value > max_value:
            return False
        return True

    def penalty(params: Dict[str, Any], outcome: Dict[str, Any]) -> float:
        metrics = outcome.get("metrics", {})
        if isinstance(metrics, list):
            for m in metrics:
                if m.get("name") == metric_name:
                    value = m.get("value", 0)
                    break
            else:
                return 0.0
        else:
            value = metrics.get(metric_name, 0)

        violation = 0.0
        if min_value is not None and value < min_value:
            violation = min_value - value
        if max_value is not None and value > max_value:
            violation = value - max_value
        return violation

    return Constraint(
        name=f"metric_{metric_name}",
        type=ConstraintType.HARD if hard else ConstraintType.SOFT,
        check_fn=check,
        penalty_fn=penalty,
        description=f"Threshold for {metric_name}: [{min_value}, {max_value}]",
    )
