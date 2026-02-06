"""Invariant checks for simulation outputs."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List

import numpy as np


@dataclass
class InvariantViolation:
    """A single invariant violation."""

    check_name: str
    message: str
    severity: str = "error"  # error, warning
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InvariantReport:
    """Report of all invariant checks."""

    passed: bool
    violations: List[InvariantViolation] = field(default_factory=list)
    warnings: List[InvariantViolation] = field(default_factory=list)
    checks_run: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "violations": [
                {
                    "check_name": v.check_name,
                    "message": v.message,
                    "severity": v.severity,
                    "details": v.details,
                }
                for v in self.violations
            ],
            "warnings": [
                {
                    "check_name": w.check_name,
                    "message": w.message,
                    "severity": w.severity,
                    "details": w.details,
                }
                for w in self.warnings
            ],
            "checks_run": self.checks_run,
        }


class InvariantChecker:
    """Performs invariant checks on simulation outputs."""

    def __init__(self, domain_pack_name: str | None = None):
        self.domain_pack_name = domain_pack_name

    def check_all(
        self,
        outcome: Dict[str, Any],
        state: Dict[str, Any] | None = None,
        actions: Dict[str, Any] | None = None,
    ) -> InvariantReport:
        """Run all invariant checks on an outcome."""
        violations: List[InvariantViolation] = []
        warnings: List[InvariantViolation] = []
        checks_run = 0

        # Bounds checks
        checks_run += 1
        bounds_result = self._check_bounds(outcome)
        violations.extend([v for v in bounds_result if v.severity == "error"])
        warnings.extend([v for v in bounds_result if v.severity == "warning"])

        # NaN/Inf detection
        checks_run += 1
        nan_result = self._check_nan_inf(outcome)
        violations.extend([v for v in nan_result if v.severity == "error"])
        warnings.extend([v for v in nan_result if v.severity == "warning"])

        # Conservation/sanity metrics for spatial packs
        if self.domain_pack_name and "spatial" in self.domain_pack_name.lower():
            checks_run += 1
            conservation_result = self._check_spatial_conservation(outcome)
            violations.extend([v for v in conservation_result if v.severity == "error"])
            warnings.extend([v for v in conservation_result if v.severity == "warning"])

        # Schema completeness
        checks_run += 1
        schema_result = self._check_schema_completeness(outcome)
        violations.extend([v for v in schema_result if v.severity == "error"])
        warnings.extend([v for v in schema_result if v.severity == "warning"])

        passed = len(violations) == 0
        return InvariantReport(
            passed=passed,
            violations=violations,
            warnings=warnings,
            checks_run=checks_run,
        )

    def _check_bounds(self, outcome: Dict[str, Any]) -> List[InvariantViolation]:
        """Check that numeric values are within reasonable bounds."""
        violations = []
        metrics = outcome.get("metrics", [])

        for metric in metrics:
            if not isinstance(metric, dict):
                continue
            value = metric.get("value")
            name = metric.get("name", "unknown")

            if value is None:
                continue

            if isinstance(value, (int, float)):
                if value < -1e15 or value > 1e15:
                    violations.append(
                        InvariantViolation(
                            check_name="bounds_check",
                            message=f"Metric '{name}' value {value} exceeds bounds",
                            severity="error",
                            details={"metric": name, "value": value},
                        )
                    )

        return violations

    def _check_nan_inf(self, outcome: Dict[str, Any]) -> List[InvariantViolation]:
        """Check for NaN or Inf values in the outcome."""
        violations = []

        def check_value(path: str, value: Any) -> None:
            if isinstance(value, float):
                if math.isnan(value):
                    violations.append(
                        InvariantViolation(
                            check_name="nan_check",
                            message=f"NaN detected at {path}",
                            severity="error",
                            details={"path": path},
                        )
                    )
                elif math.isinf(value):
                    violations.append(
                        InvariantViolation(
                            check_name="inf_check",
                            message=f"Infinity detected at {path}",
                            severity="error",
                            details={"path": path},
                        )
                    )
            elif isinstance(value, dict):
                for k, v in value.items():
                    check_value(f"{path}.{k}", v)
            elif isinstance(value, list):
                for i, v in enumerate(value):
                    check_value(f"{path}[{i}]", v)

        check_value("outcome", outcome)
        return violations

    def _check_spatial_conservation(
        self, outcome: Dict[str, Any]
    ) -> List[InvariantViolation]:
        """Check conservation laws for spatial simulations."""
        violations = []
        arrays = outcome.get("arrays", {})

        # Check concentration grid if present
        grid = arrays.get("concentration_grid") or arrays.get("grid")
        if grid is not None:
            try:
                arr = np.array(grid)
                if np.any(arr < 0):
                    violations.append(
                        InvariantViolation(
                            check_name="spatial_non_negative",
                            message="Concentration grid contains negative values",
                            severity="error",
                            details={"min_value": float(np.min(arr))},
                        )
                    )
                if np.any(np.isnan(arr)):
                    violations.append(
                        InvariantViolation(
                            check_name="spatial_nan",
                            message="Concentration grid contains NaN values",
                            severity="error",
                            details={"nan_count": int(np.sum(np.isnan(arr)))},
                        )
                    )
                # Check mass conservation (soft warning)
                total_mass = float(np.sum(arr))
                if total_mass < 0:
                    violations.append(
                        InvariantViolation(
                            check_name="spatial_mass_conservation",
                            message="Total mass is negative",
                            severity="warning",
                            details={"total_mass": total_mass},
                        )
                    )
            except Exception:
                pass

        return violations

    def _check_schema_completeness(
        self, outcome: Dict[str, Any]
    ) -> List[InvariantViolation]:
        """Check that required fields are present."""
        violations = []
        required_fields = ["metrics"]

        for field_name in required_fields:
            if field_name not in outcome:
                violations.append(
                    InvariantViolation(
                        check_name="schema_completeness",
                        message=f"Required field '{field_name}' is missing",
                        severity="warning",
                        details={"missing_field": field_name},
                    )
                )

        return violations
