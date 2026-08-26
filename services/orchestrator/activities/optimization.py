"""Optimization-related activities."""
import hashlib
import json
import random
import uuid
from typing import Any, Dict, List

from temporalio import activity


def _sample_bound(bounds: Dict[str, Any], rng: random.Random, value: float | None = None) -> Any:
    """Sample or coerce a value into the correct int/float type for a bound."""
    lo, hi = bounds["min"], bounds["max"]
    as_int = bounds.get("type") == "int" or bounds.get("dtype") == "int"
    if value is None:
        value = rng.randint(int(lo), int(hi)) if as_int else rng.uniform(float(lo), float(hi))
    else:
        value = max(lo, min(hi, value))
    return int(round(value)) if as_int else float(value)


@activity.defn
async def initialize_optimizer(run_spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Initialize optimizer state.
    
    Creates the initial state for Bayesian/evolutionary optimization.
    """
    optimizer_type = run_spec.get("optimizer_type", "bayesian")
    objectives = run_spec.get("objectives", {"type": "maximize", "metrics": []})
    
    # Get parameter bounds
    action_ranges = run_spec.get("action_ranges", {})
    
    return {
        "optimizer_type": optimizer_type,
        "objectives": objectives,
        "action_ranges": action_ranges,
        "initial_state": run_spec.get("initial_state", {}),
        "iteration": 0,
        "best_score": None,
        "best_params": None,
        "history": [],
        "surrogate_model": None,  # Would be actual model state
        "acquisition_function": "expected_improvement",
    }


@activity.defn
async def propose_next_batch(
    optimizer_state: Dict[str, Any],
    batch_size: int,
    run_id: str,
) -> List[Dict[str, Any]]:
    """
    Propose next batch of scenarios to evaluate.
    
    Uses the optimizer to suggest promising parameter combinations.
    """
    action_ranges = optimizer_state.get("action_ranges", {})
    history = optimizer_state.get("history", [])
    
    rng = random.Random(optimizer_state.get("iteration", 0))
    
    scenarios = []
    for i in range(batch_size):
        # Simple random proposal (would use Bayesian optimization in production)
        # In practice, this would:
        # 1. Fit a surrogate model to history
        # 2. Optimize acquisition function
        # 3. Return points that maximize expected improvement
        
        actions = {}
        for param, bounds in action_ranges.items():
            if isinstance(bounds, dict) and "min" in bounds and "max" in bounds:
                if history and rng.random() > 0.3:
                    best = optimizer_state.get("best_params", {})
                    if param in best:
                        span = (bounds["max"] - bounds["min"]) * 0.1
                        noise = rng.gauss(0, span if span else 1)
                        actions[param] = _sample_bound(bounds, rng, best[param] + noise)
                    else:
                        actions[param] = _sample_bound(bounds, rng)
                else:
                    actions[param] = _sample_bound(bounds, rng)
            else:
                actions[param] = bounds
        
        scenario_seed = rng.randint(0, 2**31)
        sequence = optimizer_state.get("iteration", 0) * batch_size + i
        
        hash_data = {"run_id": run_id, "sequence": sequence, "actions": actions}
        scenario_hash = hashlib.sha256(
            json.dumps(hash_data, sort_keys=True).encode()
        ).hexdigest()
        
        scenarios.append({
            "scenario_id": str(uuid.uuid4()),
            "run_id": run_id,
            "sequence_number": sequence,
            "state": optimizer_state.get("initial_state", {}),
            "actions": actions,
            "fidelity": "mid",
            "seed": scenario_seed,
            "scenario_hash": scenario_hash,
        })
    
    return scenarios


@activity.defn
async def update_optimizer(
    optimizer_state: Dict[str, Any],
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Update optimizer with new results.
    
    Adds results to history and updates surrogate model.
    """
    new_state = optimizer_state.copy()
    new_state["iteration"] = optimizer_state.get("iteration", 0) + 1
    
    # Add to history
    history = list(optimizer_state.get("history", []))
    for result in results:
        if result.get("score") is not None:
            history.append({
                "scenario_id": result.get("scenario_id"),
                "params": result.get("actions") or result.get("outcome", {}).get("actions", {}),
                "score": result["score"],
            })
    new_state["history"] = history
    
    # Update best
    for result in results:
        score = result.get("score")
        if score is not None:
            if new_state.get("best_score") is None or score > new_state["best_score"]:
                new_state["best_score"] = score
                new_state["best_params"] = result.get("actions") or result.get("outcome", {}).get("actions", {})
    
    # Would update surrogate model here
    
    return new_state


@activity.defn
async def check_convergence(
    optimizer_state: Dict[str, Any],
    all_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Check if optimization has converged.
    
    Convergence criteria:
    - Improvement below threshold for N iterations
    - Score variance below threshold
    - Maximum iterations reached
    """
    history = optimizer_state.get("history", [])
    
    if len(history) < 20:
        return {"converged": False, "reason": "insufficient_data"}
    
    # Check recent improvement
    recent_scores = [h["score"] for h in history[-20:]]
    score_range = max(recent_scores) - min(recent_scores)
    
    # Converged if score range is very small
    if score_range < 0.001:
        return {"converged": True, "reason": "score_plateau"}
    
    # Check improvement trend
    first_half = sum(recent_scores[:10]) / 10
    second_half = sum(recent_scores[10:]) / 10
    
    improvement = (second_half - first_half) / abs(first_half) if first_half != 0 else 0
    
    if abs(improvement) < 0.01:
        return {"converged": True, "reason": "no_improvement"}
    
    return {"converged": False, "reason": "improving"}


@activity.defn
async def get_pareto_frontier(
    results: List[Dict[str, Any]],
    objectives: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Compute Pareto frontier for multi-objective optimization.
    
    Returns non-dominated solutions.
    """
    metrics = objectives.get("metrics", [])
    if len(metrics) < 2:
        return []
    
    # Extract metric values for each result
    points = []
    for result in results:
        if result.get("score") is None:
            continue
        
        outcome = result.get("outcome", {})
        metric_values = {}
        
        if "metrics" in outcome and isinstance(outcome["metrics"], list):
            for m in outcome["metrics"]:
                if m.get("name") in metrics:
                    metric_values[m["name"]] = m.get("value", 0)
        
        if len(metric_values) == len(metrics):
            points.append({
                "scenario_id": result.get("scenario_id"),
                "metrics": metric_values,
                "score": result.get("score"),
            })
    
    # Find non-dominated points
    pareto = []
    for i, point in enumerate(points):
        is_dominated = False
        for j, other in enumerate(points):
            if i == j:
                continue
            
            # Check if other dominates point
            dominates = True
            strictly_better = False
            for m in metrics:
                if other["metrics"][m] < point["metrics"][m]:
                    dominates = False
                    break
                if other["metrics"][m] > point["metrics"][m]:
                    strictly_better = True
            
            if dominates and strictly_better:
                is_dominated = True
                break
        
        if not is_dominated:
            pareto.append(point)
    
    return pareto
