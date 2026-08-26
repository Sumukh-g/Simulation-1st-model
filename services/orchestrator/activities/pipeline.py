"""Pipeline activities for run orchestration."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
from typing import Any, Dict, List

from temporalio import activity

from services.api.moe import MoECommittee, MoETask, TaskStage
from .formalizer import formalize_objective

logger = logging.getLogger(__name__)


def _coerce_action_value(bounds: Dict[str, Any], value: float) -> Any:
    """Keep integer action parameters as ints when bounds declare type=int or both ends are ints with type hint."""
    lo, hi = bounds["min"], bounds["max"]
    as_int = bounds.get("type") == "int" or bounds.get("dtype") == "int"
    value = max(lo, min(hi, value))
    return int(round(value)) if as_int else float(value)


@activity.defn
async def formalize_objectives(run_spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse user question and formalize into structured ObjectiveSpec.
    
    This is the critical wiring that makes the user's question DRIVE
    the entire simulation pipeline.
    """
    # Extract the user's question from run_spec
    objective_spec = run_spec.get("objective_spec", {})
    user_question = objective_spec.get("description", "")
    domain_pack = run_spec.get("domain_pack", "")
    
    if not user_question:
        logger.warning("No user question found in run_spec, using default objectives")
        return {
            "objectives": {"type": "maximize", "metrics": []},
            "constraints": [],
            "context": {},
            "action_ranges": run_spec.get("action_ranges") or {},
            "initial_state": run_spec.get("initial_state") or {},
        }

    # Ephemeral packs ship pre-built ranges/state from pack_creation.materialize_for_execution
    if run_spec.get("ephemeral") and run_spec.get("action_ranges"):
        objectives_list = run_spec.get("objective_spec", {}).get("objectives") or []
        metrics = [
            {
                "name": o.get("name"),
                "direction": o.get("direction", "maximize"),
                "weight": float(o.get("weight", 1.0)),
            }
            for o in objectives_list
            if isinstance(o, dict) and o.get("name")
        ]
        if not metrics:
            draft = run_spec.get("ephemeral_pack_spec") or {}
            metrics = [
                {
                    "name": m.get("name"),
                    "direction": m.get("direction", "maximize"),
                    "weight": 1.0,
                }
                for m in (draft.get("metrics") or [])
                if isinstance(m, dict) and m.get("name")
            ]
        direction = "minimize" if any(m.get("direction") == "minimize" for m in metrics) else "maximize"
        return {
            "objectives": {
                "type": direction,
                "metrics": metrics,
                "description": user_question,
            },
            "constraints": run_spec.get("objective_spec", {}).get("constraints") or [],
            "context": {"ephemeral": True, "simulation_mode": run_spec.get("simulation_mode")},
            "action_ranges": run_spec.get("action_ranges") or {},
            "initial_state": run_spec.get("initial_state") or {},
        }
    
    # Get available metrics from domain pack if possible
    available_metrics = None
    if run_spec.get("ephemeral"):
        draft = run_spec.get("ephemeral_pack_spec") or run_spec.get("draft_pack") or {}
        available_metrics = [
            m.get("name") for m in (draft.get("metrics") or []) if isinstance(m, dict) and m.get("name")
        ]
    if not available_metrics:
        try:
            from compute.domain_packs.sdk import DomainPackRegistry
            pack = DomainPackRegistry.create_instance(domain_pack)
            if pack:
                available_metrics = pack.get_metrics_list()
        except Exception as e:
            logger.debug(f"Could not load domain pack metrics: {e}")
    
    # Formalize the objective using heuristics and/or LLM. The LLM path makes a
    # blocking network call, so run it in a worker thread to keep the Temporal
    # activity's event loop responsive.
    formalized = await asyncio.to_thread(
        formalize_objective,
        question=user_question,
        domain_pack=domain_pack,
        available_metrics=available_metrics,
        use_llm=True,  # Will fall back to heuristics if LLM unavailable
    )
    
    logger.info(f"Formalized objective: direction={formalized.primary_direction}, "
                f"metrics={[m.name for m in formalized.metrics]}, "
                f"constraints={[c.name for c in formalized.constraints]}")
    
    # Convert to objectives dict format expected by rest of pipeline
    objectives = {
        "type": formalized.primary_direction,
        "metrics": [m.model_dump() for m in formalized.metrics],
        "description": formalized.description,
    }
    
    constraints = [c.model_dump() for c in formalized.constraints]
    
    context = {
        "horizon": formalized.horizon,
        "context_tags": formalized.context_tags,
        "success_criteria": formalized.success_criteria,
        "required_outputs": formalized.required_outputs,
        "domain_hints": formalized.domain_hints,
    }
    
    return {
        "objectives": objectives,
        "constraints": constraints,
        "context": context,
        "action_ranges": formalized.action_ranges,
        "initial_state": formalized.initial_state,
    }


@activity.defn
async def build_evidence_pack(run_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build EvidencePack stub from provided references."""
    return {
        "name": run_spec.get("evidence_pack_name", f"EvidencePack-{run_spec['run_id']}"),
        "description": run_spec.get("evidence_pack_description", "Auto-generated evidence pack"),
        "items": run_spec.get("evidence_items", []),
    }


@activity.defn
async def model_causes(run_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Run causal/levers modeling via MoE (structured, LLM-backed when available)."""
    committee = MoECommittee()
    # MoETask.constraints is List[str]; the formalizer emits constraint dicts,
    # so reduce them to their names before handing them to the committee.
    raw_constraints = run_spec.get("constraints", []) or []
    constraint_names = [
        (c.get("name") or c.get("constraint_type") or "constraint")
        if isinstance(c, dict)
        else str(c)
        for c in raw_constraints
    ]

    objectives = run_spec.get("objectives", {}) or {}
    question = (
        objectives.get("description")
        or run_spec.get("objective_spec", {}).get("description")
        or "the objective"
    )
    metric_names = [m.get("name") for m in objectives.get("metrics", []) if isinstance(m, dict)]

    # Provide the actual goal + metrics + domain so the LLM reasons about THIS run.
    context = {
        **(run_spec.get("context", {}) or {}),
        "domain_pack": run_spec.get("domain_pack", ""),
        "objective_direction": objectives.get("type", "optimize"),
        "objective_metrics": metric_names,
        "action_ranges": list((run_spec.get("action_ranges") or {}).keys()),
    }

    task = MoETask(
        task=f"Identify the key decision levers and causal drivers for: {question}",
        stage=TaskStage.CAUSE_MODELING,
        stakes=float(run_spec.get("stakes", 0.5) or 0.5),
        context=context,
        evidence_refs=run_spec.get("evidence_refs", []),
        constraints=constraint_names,
    )
    report = await committee.run(task)
    result = report.arbitration.model_dump()
    # Attach the structured expert outputs so the report/UI can show the reasoning.
    result["expert_outputs"] = [eo.model_dump() for eo in report.expert_outputs]
    result["escalation"] = report.escalation
    return result


@activity.defn
async def generate_structured_scenarios(run_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Generate structured scenarios driven by the formalized ObjectiveSpec.
    
    Ensures:
    - At least 50 scenarios are generated
    - Scenarios are diverse (grid + Latin hypercube + random)
    - Scenarios respect domain pack action schemas
    - Each scenario has a deterministic hash for reproducibility
    """
    run_id = run_spec["run_id"]
    
    # Minimum 50 scenarios as per requirements
    budget = max(50, run_spec.get("scenario_budget", run_spec.get("budget", 100)))
    
    seed_policy = run_spec.get("seed_policy", {})
    base_seed = seed_policy.get("base_seed", 42)
    rng = random.Random(base_seed)

    initial_state = run_spec.get("initial_state", {})
    action_ranges = run_spec.get("action_ranges", {})
    fidelity = run_spec.get("default_fidelity", "cheap")
    
    # Get objectives to inform scenario generation
    objectives = run_spec.get("objectives", {})
    
    # If no action_ranges provided, try to get from domain pack
    if not action_ranges:
        domain_pack = run_spec.get("domain_pack", "")
        try:
            from compute.domain_packs.sdk import DomainPackRegistry
            pack = DomainPackRegistry.create_instance(domain_pack)
            if pack:
                action_ranges = pack.get_action_ranges()
                if not initial_state:
                    initial_state = pack.get_default_state()
                logger.info(f"Using action ranges from {domain_pack}: {list(action_ranges.keys())}")
        except Exception as e:
            logger.warning(f"Could not get action ranges from domain pack: {e}")
    
    if not action_ranges:
        logger.error("No action_ranges available - cannot generate meaningful scenarios!")
        # Return minimal scenarios that will fail loudly
        raise ValueError("Cannot generate scenarios: no action_ranges defined and domain pack not found")
    
    scenarios = []
    
    # Strategy 1: Grid sampling for exploration (20% of budget)
    grid_count = max(10, budget // 5)
    grid_scenarios = _generate_grid_scenarios(
        run_id, initial_state, action_ranges, fidelity, rng, grid_count
    )
    scenarios.extend(grid_scenarios)
    
    # Strategy 2: Latin Hypercube for space-filling (30% of budget)
    lhs_count = max(15, budget // 3)
    lhs_scenarios = _generate_lhs_scenarios(
        run_id, initial_state, action_ranges, fidelity, rng, lhs_count
    )
    scenarios.extend(lhs_scenarios)
    
    # Strategy 3: Random sampling for diversity (remaining budget)
    random_count = budget - len(scenarios)
    random_scenarios = _generate_random_scenarios(
        run_id, initial_state, action_ranges, fidelity, rng, random_count
    )
    scenarios.extend(random_scenarios)
    
    # Add objective-aware scenarios if we have metric direction info
    if objectives.get("type") == "maximize" or objectives.get("type") == "minimize":
        # Add boundary/extreme scenarios for objective-aware exploration
        boundary_scenarios = _generate_boundary_scenarios(
            run_id, initial_state, action_ranges, fidelity, rng, 
            objectives.get("type", "maximize"), min(10, budget // 10)
        )
        # Replace some random scenarios with boundary ones
        if boundary_scenarios:
            scenarios = scenarios[:-len(boundary_scenarios)] + boundary_scenarios
    
    logger.info(f"Generated {len(scenarios)} scenarios: "
                f"{grid_count} grid, {lhs_count} LHS, {random_count} random")
    
    return scenarios


def _generate_grid_scenarios(
    run_id: str,
    initial_state: Dict[str, Any],
    action_ranges: Dict[str, Any],
    fidelity: str,
    rng: random.Random,
    count: int,
) -> List[Dict[str, Any]]:
    """Generate grid-based scenarios for systematic exploration."""
    scenarios = []
    
    # Get numeric parameters with ranges
    params = [(k, v) for k, v in action_ranges.items() 
              if isinstance(v, dict) and "min" in v and "max" in v]
    
    if not params:
        return []
    
    # Calculate grid points per dimension
    n_dims = len(params)
    points_per_dim = max(2, int(count ** (1.0 / n_dims)))
    
    # Generate grid points
    from itertools import product
    
    grid_values = {}
    for param, bounds in params:
        min_val, max_val = bounds["min"], bounds["max"]
        grid_values[param] = [
            min_val + i * (max_val - min_val) / (points_per_dim - 1)
            for i in range(points_per_dim)
        ]
    
    # Generate all combinations (up to count)
    all_combos = list(product(*[grid_values[p[0]] for p in params]))
    selected_combos = all_combos[:count]
    
    for combo in selected_combos:
        actions = {params[i][0]: _coerce_action_value(params[i][1], combo[i]) for i in range(len(params))}
        
        # Add non-range parameters
        for k, v in action_ranges.items():
            if k not in actions:
                actions[k] = v if not isinstance(v, list) else rng.choice(v)
        
        seed = rng.randint(0, 2**31)
        hash_data = {
            "run_id": run_id,
            "state": initial_state,
            "actions": actions,
            "seed": seed,
            "fidelity": fidelity,
            "strategy": "grid",
        }
        scenario_hash = hashlib.sha256(json.dumps(hash_data, sort_keys=True).encode()).hexdigest()
        
        scenarios.append({
            "run_id": run_id,
            "state": initial_state,
            "actions": actions,
            "fidelity": fidelity,
            "seed": seed,
            "scenario_hash": scenario_hash,
            "generation_strategy": "grid",
        })
    
    return scenarios


def _generate_lhs_scenarios(
    run_id: str,
    initial_state: Dict[str, Any],
    action_ranges: Dict[str, Any],
    fidelity: str,
    rng: random.Random,
    count: int,
) -> List[Dict[str, Any]]:
    """Generate Latin Hypercube sampled scenarios for space-filling."""
    scenarios = []
    
    # Get numeric parameters
    params = [(k, v) for k, v in action_ranges.items() 
              if isinstance(v, dict) and "min" in v and "max" in v]
    
    if not params:
        return []
    
    n_dims = len(params)
    
    # Simple LHS implementation
    samples = []
    for dim in range(n_dims):
        # Create stratified samples
        perm = list(range(count))
        rng.shuffle(perm)
        samples.append([
            (perm[i] + rng.random()) / count
            for i in range(count)
        ])
    
    # Create scenarios
    for i in range(count):
        actions = {}
        for j, (param, bounds) in enumerate(params):
            min_val, max_val = bounds["min"], bounds["max"]
            actions[param] = _coerce_action_value(
                bounds, min_val + samples[j][i] * (max_val - min_val)
            )
        
        # Add non-range parameters
        for k, v in action_ranges.items():
            if k not in actions:
                actions[k] = v if not isinstance(v, list) else rng.choice(v)
        
        seed = rng.randint(0, 2**31)
        hash_data = {
            "run_id": run_id,
            "state": initial_state,
            "actions": actions,
            "seed": seed,
            "fidelity": fidelity,
            "strategy": "lhs",
        }
        scenario_hash = hashlib.sha256(json.dumps(hash_data, sort_keys=True).encode()).hexdigest()
        
        scenarios.append({
            "run_id": run_id,
            "state": initial_state,
            "actions": actions,
            "fidelity": fidelity,
            "seed": seed,
            "scenario_hash": scenario_hash,
            "generation_strategy": "lhs",
        })
    
    return scenarios


def _generate_random_scenarios(
    run_id: str,
    initial_state: Dict[str, Any],
    action_ranges: Dict[str, Any],
    fidelity: str,
    rng: random.Random,
    count: int,
) -> List[Dict[str, Any]]:
    """Generate random scenarios for exploration."""
    scenarios = []
    
    for i in range(count):
        actions = {}
        for param, bounds in action_ranges.items():
            if isinstance(bounds, dict) and "min" in bounds and "max" in bounds:
                lo, hi = bounds["min"], bounds["max"]
                as_int = bounds.get("type") == "int" or bounds.get("dtype") == "int"
                raw = rng.randint(int(lo), int(hi)) if as_int else rng.uniform(float(lo), float(hi))
                actions[param] = _coerce_action_value(bounds, raw)
            elif isinstance(bounds, list):
                actions[param] = rng.choice(bounds)
            else:
                actions[param] = bounds

        seed = rng.randint(0, 2**31)
        hash_data = {
            "run_id": run_id,
            "state": initial_state,
            "actions": actions,
            "seed": seed,
            "fidelity": fidelity,
            "strategy": "random",
        }
        scenario_hash = hashlib.sha256(json.dumps(hash_data, sort_keys=True).encode()).hexdigest()
        
        scenarios.append({
            "run_id": run_id,
            "state": initial_state,
            "actions": actions,
            "fidelity": fidelity,
            "seed": seed,
            "scenario_hash": scenario_hash,
            "generation_strategy": "random",
        })
    
    return scenarios


def _generate_boundary_scenarios(
    run_id: str,
    initial_state: Dict[str, Any],
    action_ranges: Dict[str, Any],
    fidelity: str,
    rng: random.Random,
    direction: str,
    count: int,
) -> List[Dict[str, Any]]:
    """Generate boundary/extreme scenarios for objective-aware exploration."""
    scenarios = []
    
    params = [(k, v) for k, v in action_ranges.items() 
              if isinstance(v, dict) and "min" in v and "max" in v]
    
    if not params:
        return []
    
    for i in range(count):
        actions = {}
        for param, bounds in params:
            min_val, max_val = bounds["min"], bounds["max"]
            
            # Alternate between min, max, and mid values
            choice = i % 3
            if choice == 0:
                actions[param] = _coerce_action_value(bounds, min_val)
            elif choice == 1:
                actions[param] = _coerce_action_value(bounds, max_val)
            else:
                actions[param] = _coerce_action_value(bounds, (min_val + max_val) / 2)
        
        # Add non-range parameters
        for k, v in action_ranges.items():
            if k not in actions:
                actions[k] = v if not isinstance(v, list) else rng.choice(v)
        
        seed = rng.randint(0, 2**31)
        hash_data = {
            "run_id": run_id,
            "state": initial_state,
            "actions": actions,
            "seed": seed,
            "fidelity": fidelity,
            "strategy": "boundary",
        }
        scenario_hash = hashlib.sha256(json.dumps(hash_data, sort_keys=True).encode()).hexdigest()
        
        scenarios.append({
            "run_id": run_id,
            "state": initial_state,
            "actions": actions,
            "fidelity": fidelity,
            "seed": seed,
            "scenario_hash": scenario_hash,
            "generation_strategy": "boundary",
        })
    
    return scenarios


@activity.defn
async def promote_finalists(
    finalists: List[Dict[str, Any]],
    fidelity: str,
    replicates: int,
) -> List[Dict[str, Any]]:
    """Promote finalists to higher fidelity with replicates."""
    promoted = []
    for finalist in finalists:
        for r in range(replicates):
            seed = finalist.get("seed", 0) + r + 1
            hash_data = {
                "run_id": finalist["run_id"],
                "state": finalist.get("state", {}),
                "actions": finalist.get("actions", {}),
                "seed": seed,
                "fidelity": fidelity,
            }
            scenario_hash = hashlib.sha256(
                json.dumps(hash_data, sort_keys=True).encode()
            ).hexdigest()
            promoted.append(
                {
                    "run_id": finalist["run_id"],
                    "state": finalist.get("state", {}),
                    "actions": finalist.get("actions", {}),
                    "fidelity": fidelity,
                    "seed": seed,
                    "scenario_hash": scenario_hash,
                }
            )
    return promoted


@activity.defn
async def generate_robustness_scenarios(
    base_scenarios: List[Dict[str, Any]],
    action_ranges: Dict[str, Any],
    stress_factor: float = 0.1,
) -> List[Dict[str, Any]]:
    """Generate sensitivity, stress, and worst-case scenarios."""
    robustness = []
    for scenario in base_scenarios:
        actions = scenario.get("actions", {})
        for mode in ["sensitivity", "stress", "worst_case"]:
            adjusted = {}
            for param, value in actions.items():
                bounds = action_ranges.get(param)
                if isinstance(value, (int, float)) and isinstance(bounds, dict):
                    delta = (bounds["max"] - bounds["min"]) * stress_factor
                    if mode == "worst_case":
                        adjusted[param] = bounds["max"]
                    else:
                        adjusted[param] = min(bounds["max"], max(bounds["min"], value + delta))
                else:
                    adjusted[param] = value

            seed = scenario.get("seed", 0) + hash(mode) % 997
            hash_data = {
                "run_id": scenario["run_id"],
                "state": scenario.get("state", {}),
                "actions": adjusted,
                "seed": seed,
                "fidelity": scenario.get("fidelity", "mid"),
                "mode": mode,
            }
            scenario_hash = hashlib.sha256(
                json.dumps(hash_data, sort_keys=True).encode()
            ).hexdigest()
            robustness.append(
                {
                    "run_id": scenario["run_id"],
                    "state": scenario.get("state", {}),
                    "actions": adjusted,
                    "fidelity": scenario.get("fidelity", "mid"),
                    "seed": seed,
                    "scenario_hash": scenario_hash,
                    "robustness_mode": mode,
                }
            )
    return robustness
