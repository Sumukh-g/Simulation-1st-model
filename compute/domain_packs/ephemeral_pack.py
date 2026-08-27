"""Ephemeral domain pack — deterministic simulate() from LLM-drafted schemas."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Type

import numpy as np
from pydantic import BaseModel, Field, create_model

from .sdk import (
    DomainPackBase,
    Fidelity,
    OutcomeBundle,
    MetricBundle,
    FeasibilityResult,
    CostEstimate,
    ObjectiveSpec,
)
from .sdk.types import MetricValue

EPHEMERAL_VERSION = "0.1.0-illustrative"

_NUMERIC_TYPES = {"number", "float", "int", "integer", "double", "decimal"}


def _is_numeric_field(field: Dict[str, Any]) -> bool:
    t = str(field.get("type", "number")).lower()
    return t in _NUMERIC_TYPES


def _pydantic_type(field_type: str) -> type:
    t = (field_type or "number").lower()
    if t in ("int", "integer"):
        return int
    if t in ("bool", "boolean"):
        return bool
    if t == "string":
        return str
    return float


def _build_model(name: str, fields: List[Dict[str, Any]], defaults: Dict[str, Any]) -> Type[BaseModel]:
    if not fields:
        fields = [{"name": "baseline", "type": "number", "description": "Baseline level"}]
    model_fields: Dict[str, Any] = {}
    for f in fields:
        if not isinstance(f, dict):
            continue
        fname = f.get("name")
        if not fname:
            continue
        py_type = _pydantic_type(str(f.get("type", "number")))
        default = defaults.get(fname)
        if default is not None:
            model_fields[fname] = (py_type, Field(default=default, description=f.get("description") or ""))
        elif py_type is float:
            model_fields[fname] = (float, Field(default=50.0, ge=0.0, le=100.0))
        elif py_type is int:
            model_fields[fname] = (int, Field(default=50, ge=0, le=100))
        elif py_type is str:
            model_fields[fname] = (str, Field(default=f.get("default") or "default", description=f.get("description") or ""))
        else:
            model_fields[fname] = (py_type, Field(default=False, description=f.get("description") or ""))
    return create_model(name, **model_fields)  # type: ignore[arg-type]


def sanitize_pack_schemas(pack: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only numeric levers for optimization; drop string IDs from action_schema."""
    pack = dict(pack)
    actions = list(pack.get("action_schema") or [])
    numeric_actions = [a for a in actions if isinstance(a, dict) and _is_numeric_field(a)]
    if not numeric_actions:
        numeric_actions = [
            {"name": "intervention_intensity", "type": "number", "description": "Overall intervention strength"},
            {"name": "policy_coverage", "type": "number", "description": "Coverage of target (0-100)"},
            {"name": "budget_fraction", "type": "number", "description": "Budget deployed (0-100)"},
        ]
    pack["action_schema"] = numeric_actions

    state = list(pack.get("state_schema") or [])
    if not state:
        pack["state_schema"] = [{"name": "baseline", "type": "number", "description": "Baseline level"}]

    metrics = list(pack.get("metrics") or [])
    if not metrics:
        pack["metrics"] = [
            {"name": "primary_outcome", "direction": "maximize"},
            {"name": "cost", "direction": "minimize"},
        ]
    return pack


def build_initial_state(pack: Dict[str, Any], objectives: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    """Build numeric initial state aligned with state_schema field names."""
    initial: Dict[str, Any] = {}
    for f in pack.get("state_schema") or []:
        if not isinstance(f, dict):
            continue
        name = f.get("name")
        if not name or not _is_numeric_field(f):
            continue
        lower = str(name).lower()
        if any(k in lower for k in ("pollution", "emission", "cost", "budget", "risk")):
            initial[name] = 100.0
        elif any(k in lower for k in ("year", "month", "time")):
            initial[name] = 0.0
        else:
            initial[name] = 1.0

    for m in objectives or []:
        if not isinstance(m, dict):
            continue
        mname = m.get("name")
        if not mname:
            continue
        key = f"{mname}_baseline"
        if key not in initial:
            initial[key] = 100.0 if m.get("direction") == "minimize" else 1.0

    if "baseline" not in initial and initial:
        first_key = next(iter(initial))
        initial.setdefault("baseline", initial[first_key])
    initial.setdefault("baseline", 100.0)
    return initial


class EphemeralDomainPack(DomainPackBase):
    """Runtime pack built from draft / ephemeral schemas in run_spec."""

    def __init__(self, spec: Dict[str, Any]) -> None:
        raw_pack = spec.get("ephemeral_pack_spec") or spec.get("draft_pack") or spec.get("ephemeral_pack") or {}
        pack = sanitize_pack_schemas(raw_pack)
        self.name = str(pack.get("name") or spec.get("domain_pack") or "ephemeral-pack")
        self.version = str(spec.get("domain_pack_version") or EPHEMERAL_VERSION)
        self.description = str(
            pack.get("display_name") or pack.get("description") or "LLM-drafted illustrative pack"
        )
        self._fidelity_label = str(pack.get("fidelity") or "ILLUSTRATIVE")
        self._metric_specs: List[Dict[str, Any]] = list(pack.get("metrics") or [])
        self.metrics = [str(m.get("name")) for m in self._metric_specs if m.get("name")]

        state_fields = list(pack.get("state_schema") or [])
        action_fields = list(pack.get("action_schema") or [])
        initial = dict(spec.get("initial_state") or build_initial_state(pack))

        self._StateModel = _build_model("EphemeralState", state_fields, initial)
        self._ActionModel = _build_model("EphemeralActions", action_fields, {})
        # Only numeric fields are optimized levers
        self._lever_names = [
            f["name"] for f in action_fields if isinstance(f, dict) and f.get("name") and _is_numeric_field(f)
        ]
        if not self._lever_names:
            self._lever_names = ["intervention_intensity", "policy_coverage"]

        self._baselines: Dict[str, float] = {}
        for m in self._metric_specs:
            mname = m.get("name")
            if not mname:
                continue
            key = f"{mname}_baseline"
            if key in initial:
                self._baselines[mname] = float(initial[key])
            elif "baseline" in initial:
                self._baselines[mname] = float(initial["baseline"])
            elif m.get("direction") == "minimize":
                self._baselines[mname] = 100.0
            else:
                self._baselines[mname] = 1.0

    def state_schema(self) -> Type[BaseModel]:
        return self._StateModel

    def action_schema(self) -> Type[BaseModel]:
        return self._ActionModel

    def simulate(
        self,
        state: BaseModel,
        actions: BaseModel,
        fidelity: Fidelity,
        seed: int,
        scenario_id: str,
        run_id: str,
    ) -> OutcomeBundle:
        start = time.perf_counter()
        rng = np.random.RandomState(seed)
        noise_scale = {Fidelity.CHEAP: 0.12, Fidelity.MID: 0.06, Fidelity.HIGH: 0.03}[fidelity]

        state_d = state.model_dump() if hasattr(state, "model_dump") else dict(state)
        action_d = actions.model_dump() if hasattr(actions, "model_dump") else dict(actions)

        n_levers = max(len(self._lever_names), 1)
        lever_effect = 0.0
        for aname in self._lever_names:
            raw = action_d.get(aname, 50.0)
            try:
                val = float(raw)
            except (TypeError, ValueError):
                val = 50.0
            normalized = max(0.0, min(1.0, val / 100.0 if val > 1.0 else val))
            lever_effect += normalized / n_levers

        computed: Dict[str, float] = {}
        for m in self._metric_specs:
            mname = str(m.get("name"))
            direction = str(m.get("direction", "maximize")).lower()
            baseline = self._baselines.get(mname, 50.0)
            noise = float(rng.normal(0.0, noise_scale))

            if direction == "minimize":
                value = baseline * max(0.05, 1.0 - 0.55 * lever_effect) * (1.0 + noise)
            else:
                value = baseline * (1.0 + 0.65 * lever_effect) * (1.0 + noise)
            computed[mname] = float(max(value, 1e-6))

        if "cost" in self.metrics and "cost" not in computed:
            computed["cost"] = float(10.0 + 90.0 * lever_effect * (1.0 + abs(noise) * 0.5))

        elapsed_ms = max((time.perf_counter() - start) * 1000, 0.001)
        return OutcomeBundle(
            scenario_id=scenario_id,
            run_id=run_id,
            final_state={**state_d, **computed, "lever_effect": lever_effect},
            trajectory=[{"step": 0, **computed}],
            fidelity=fidelity,
            seed=seed,
            execution_time_ms=elapsed_ms,
            domain_pack_name=self.name,
            domain_pack_version=self.version,
            artifacts={"fidelity_label": self._fidelity_label, "ephemeral": True},
            raw_output={"lever_effect": lever_effect, "actions": action_d},
        )

    def score(
        self,
        outcome: OutcomeBundle,
        objectives: Optional[ObjectiveSpec] = None,
    ) -> MetricBundle:
        final = outcome.final_state or {}
        metrics = []
        for m in self._metric_specs:
            name = str(m.get("name"))
            if name in final:
                metrics.append(MetricValue(name=name, value=float(final[name])))
        if not metrics:
            metrics.append(MetricValue(name="objective_score", value=float(final.get("objective_score", 0.0))))
        return MetricBundle(
            scenario_id=outcome.scenario_id,
            run_id=outcome.run_id,
            metrics=metrics,
            is_feasible=True,
        )

    def feasibility(self, state: BaseModel, actions: BaseModel) -> FeasibilityResult:
        return FeasibilityResult(is_feasible=True, violations=[])

    def cost_model(self, fidelity: Fidelity) -> CostEstimate:
        mult = {Fidelity.CHEAP: 1.0, Fidelity.MID: 3.0, Fidelity.HIGH: 10.0}[fidelity]
        return CostEstimate(estimated_time_ms=50.0 * mult, estimated_memory_mb=32.0 * mult)

    def get_action_ranges(self) -> Dict[str, Any]:
        return {
            fname: {"min": 0.0, "max": 100.0, "type": "float"}
            for fname in self._lever_names
        }

    def get_default_state(self) -> Dict[str, Any]:
        schema = self.state_schema()
        defaults: Dict[str, Any] = {}
        for field_name, field_info in schema.model_fields.items():
            if field_info.default is not None:
                defaults[field_name] = field_info.default
        return defaults

    @classmethod
    def from_run_spec(cls, run_spec: Dict[str, Any]) -> "EphemeralDomainPack":
        return cls(run_spec)


async def load_ephemeral_pack_for_run(run_id: str, pack_name: str) -> Optional[EphemeralDomainPack]:
    """Load ephemeral pack from persisted run_spec (works across worker processes)."""
    import uuid as uuid_mod
    from sqlalchemy import select
    from services.api.db import models
    from services.orchestrator.db import get_session

    try:
        run_uuid = uuid_mod.UUID(str(run_id))
    except ValueError:
        return None

    async with get_session() as session:
        result = await session.execute(select(models.Run).where(models.Run.id == run_uuid))
        run = result.scalar_one_or_none()
        if not run or not run.run_spec:
            return None
        spec = dict(run.run_spec)
        if not spec.get("ephemeral") and spec.get("simulation_mode") not in ("create_pack", "no_pack"):
            return None
        if spec.get("domain_pack") and spec.get("domain_pack") != pack_name:
            return None
        return EphemeralDomainPack.from_run_spec(spec)
