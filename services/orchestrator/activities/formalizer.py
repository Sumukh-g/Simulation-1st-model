"""Objective Formalizer - Converts user questions into structured ObjectiveSpecs."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ObjectiveMetric(BaseModel):
    """A single objective metric."""
    name: str
    direction: str = "maximize"  # "minimize" or "maximize"
    weight: float = 1.0


class Constraint(BaseModel):
    """A constraint on the optimization."""
    name: str
    constraint_type: str = "max"  # "min", "max", "eq", "range"
    value: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    is_hard: bool = False


class FormalizedObjective(BaseModel):
    """Fully formalized objective from user question."""
    description: str
    metrics: List[ObjectiveMetric] = Field(default_factory=list)
    primary_direction: str = "maximize"
    constraints: List[Constraint] = Field(default_factory=list)
    horizon: Optional[str] = None
    context_tags: List[str] = Field(default_factory=list)
    success_criteria: List[str] = Field(default_factory=list)
    required_outputs: List[str] = Field(default_factory=list)
    domain_hints: List[str] = Field(default_factory=list)
    action_ranges: Dict[str, Any] = Field(default_factory=dict)
    initial_state: Dict[str, Any] = Field(default_factory=dict)


# Domain keyword mappings
DOMAIN_KEYWORDS = {
    "finance-pack": [
        "portfolio", "stock", "invest", "return", "sharpe", "volatility",
        "risk", "asset", "allocation", "backtest", "trading", "price",
        "capital", "profit", "loss", "drawdown", "yield", "bond", "equity",
    ],
    "spatial-pack": [
        "pollution", "diffusion", "spread", "grid", "heatmap", "spatial",
        "air quality", "contamination", "emission", "coverage", "concentration",
        "zone", "area", "location", "region", "map", "environment",
    ],
    "toy-pack": [
        "test", "demo", "toy", "simple", "walk", "position", "distance",
        "target", "move", "step", "path",
    ],
}

# Objective direction keywords
MINIMIZE_KEYWORDS = [
    "reduce", "minimize", "decrease", "lower", "less", "cut", "shrink",
    "limit", "drop", "decline", "diminish", "eliminate", "avoid",
]

MAXIMIZE_KEYWORDS = [
    "maximize", "increase", "improve", "boost", "enhance", "grow",
    "raise", "expand", "optimize", "best", "highest", "most", "gain",
]

# Constraint keywords
CONSTRAINT_KEYWORDS = {
    "budget": ["budget", "cost", "spend", "expense", "price"],
    "time": ["time", "duration", "period", "deadline", "within"],
    "risk": ["risk", "safe", "conservative", "cautious", "limit"],
    "feasibility": ["feasible", "possible", "realistic", "achievable"],
}

# Domain-specific metric mappings
DOMAIN_METRICS = {
    "finance-pack": {
        "default": [
            ObjectiveMetric(name="sharpe_ratio", direction="maximize", weight=1.0),
            ObjectiveMetric(name="total_return", direction="maximize", weight=0.8),
            ObjectiveMetric(name="max_drawdown", direction="minimize", weight=0.6),
        ],
        "return": [ObjectiveMetric(name="total_return", direction="maximize")],
        "risk": [ObjectiveMetric(name="max_drawdown", direction="minimize")],
        "sharpe": [ObjectiveMetric(name="sharpe_ratio", direction="maximize")],
    },
    "spatial-pack": {
        "default": [
            ObjectiveMetric(name="safe_area_ratio", direction="maximize", weight=1.0),
            ObjectiveMetric(name="mean_concentration", direction="minimize", weight=0.8),
            ObjectiveMetric(name="threshold_violations", direction="minimize", weight=0.6),
        ],
        "pollution": [ObjectiveMetric(name="mean_concentration", direction="minimize")],
        "coverage": [ObjectiveMetric(name="coverage_ratio", direction="maximize")],
        "safety": [ObjectiveMetric(name="safe_area_ratio", direction="maximize")],
    },
    "toy-pack": {
        "default": [
            ObjectiveMetric(name="score", direction="maximize", weight=1.0),
            ObjectiveMetric(name="distance", direction="minimize", weight=0.8),
            ObjectiveMetric(name="efficiency", direction="maximize", weight=0.5),
        ],
        "distance": [ObjectiveMetric(name="distance", direction="minimize")],
        "efficiency": [ObjectiveMetric(name="efficiency", direction="maximize")],
    },
}

# Default action ranges by domain
DOMAIN_ACTION_RANGES = {
    "finance-pack": {
        "weight_spy": {"min": 0.0, "max": 1.0},
        "weight_bnd": {"min": 0.0, "max": 1.0},
        "weight_gld": {"min": 0.0, "max": 1.0},
        "weight_cash": {"min": 0.0, "max": 1.0},
    },
    "spatial-pack": {
        "source_x": {"min": 0, "max": 100},
        "source_y": {"min": 0, "max": 100},
        "source_intensity": {"min": 0.1, "max": 5.0},
        "source_radius": {"min": 1.0, "max": 10.0},
    },
    "toy-pack": {
        "dx": {"min": -10.0, "max": 10.0},
        "dy": {"min": -10.0, "max": 10.0},
        "steps": {"min": 5, "max": 50, "type": "int"},
    },
}


def _pack_defaults(domain: str, action_ranges: Dict[str, Any]) -> Dict[str, Any]:
    """Fill initial_state / action_ranges from the registered domain pack when possible."""
    initial_state: Dict[str, Any] = {}
    ranges = dict(action_ranges or {})
    try:
        import compute.domain_packs  # noqa: F401
        from compute.domain_packs.sdk import DomainPackRegistry

        pack = DomainPackRegistry.create_instance(domain)
        if pack is not None:
            initial_state = pack.get_default_state() or {}
            if not ranges:
                ranges = pack.get_action_ranges() or {}
    except Exception as exc:
        logger.debug("Could not load pack defaults for %s: %s", domain, exc)
    return {"initial_state": initial_state, "action_ranges": ranges}


def detect_domain(question: str, domain_pack_hint: Optional[str] = None) -> str:
    """Detect which domain pack is most relevant for the question."""
    if domain_pack_hint:
        # Normalize the hint
        hint_lower = domain_pack_hint.lower().replace("_", "-").replace(" ", "-")
        for domain in DOMAIN_KEYWORDS.keys():
            if domain.lower() in hint_lower or hint_lower in domain.lower():
                return domain
        # Check if hint contains pack name variations
        if "spatial" in hint_lower:
            return "spatial-pack"
        if "finance" in hint_lower:
            return "finance-pack"
        if "toy" in hint_lower:
            return "toy-pack"
    
    question_lower = question.lower()
    
    # Score each domain by keyword matches
    scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in question_lower)
        scores[domain] = score
    
    # Return highest scoring domain
    best_domain = max(scores.items(), key=lambda x: x[1])
    if best_domain[1] > 0:
        return best_domain[0]
    
    # Default to toy-pack if no matches
    return "toy-pack"


def detect_direction(question: str) -> str:
    """Detect whether the objective is to minimize or maximize."""
    question_lower = question.lower()
    
    minimize_score = sum(1 for kw in MINIMIZE_KEYWORDS if kw in question_lower)
    maximize_score = sum(1 for kw in MAXIMIZE_KEYWORDS if kw in question_lower)
    
    if minimize_score > maximize_score:
        return "minimize"
    return "maximize"


def extract_constraints(question: str) -> List[Constraint]:
    """Extract constraints from the question."""
    constraints = []
    question_lower = question.lower()
    
    # Budget constraints
    if any(kw in question_lower for kw in CONSTRAINT_KEYWORDS["budget"]):
        # Try to extract budget amount
        budget_match = re.search(r'\$?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:budget|cost|spend)', question_lower)
        if budget_match:
            amount = float(budget_match.group(1).replace(",", ""))
            constraints.append(Constraint(
                name="budget",
                constraint_type="max",
                value=amount,
                is_hard=True,
            ))
        else:
            constraints.append(Constraint(
                name="budget",
                constraint_type="max",
                is_hard=False,
            ))
    
    # Time constraints
    if any(kw in question_lower for kw in CONSTRAINT_KEYWORDS["time"]):
        constraints.append(Constraint(
            name="time_horizon",
            constraint_type="max",
            is_hard=False,
        ))
    
    # Risk constraints
    if any(kw in question_lower for kw in CONSTRAINT_KEYWORDS["risk"]):
        constraints.append(Constraint(
            name="risk_level",
            constraint_type="max",
            is_hard=False,
        ))
    
    return constraints


def extract_horizon(question: str) -> Optional[str]:
    """Extract time horizon from the question."""
    question_lower = question.lower()
    
    # Look for explicit time mentions
    time_patterns = [
        (r'(\d+)\s*year', 'years'),
        (r'(\d+)\s*month', 'months'),
        (r'(\d+)\s*week', 'weeks'),
        (r'(\d+)\s*day', 'days'),
        (r'(\d+)\s*step', 'steps'),
    ]
    
    for pattern, unit in time_patterns:
        match = re.search(pattern, question_lower)
        if match:
            return f"{match.group(1)} {unit}"
    
    return None


def extract_context_tags(question: str, domain: str) -> List[str]:
    """Extract context tags from the question."""
    tags = [domain]
    question_lower = question.lower()
    
    # Add domain-specific tags
    for kw in DOMAIN_KEYWORDS.get(domain, []):
        if kw in question_lower:
            tags.append(kw)
    
    # Limit to 5 most relevant
    return list(set(tags))[:5]


def get_metrics_for_question(question: str, domain: str) -> List[ObjectiveMetric]:
    """Get relevant metrics based on the question and domain."""
    question_lower = question.lower()
    domain_metrics = DOMAIN_METRICS.get(domain, {})
    
    # Check for specific metric keywords
    for keyword, metrics in domain_metrics.items():
        if keyword != "default" and keyword in question_lower:
            return metrics
    
    # Return default metrics for domain
    return domain_metrics.get("default", [
        ObjectiveMetric(name="score", direction="maximize"),
    ])


def formalize_heuristic(
    question: str,
    domain_pack: Optional[str] = None,
) -> FormalizedObjective:
    """
    Formalize objectives using heuristic rules.
    
    This is the fallback when LLM is unavailable.
    """
    # Detect domain
    domain = detect_domain(question, domain_pack)
    
    # Detect objective direction
    direction = detect_direction(question)
    
    # Get metrics
    metrics = get_metrics_for_question(question, domain)
    
    # Adjust metric directions based on overall direction
    if direction == "minimize":
        # Flip the primary metric direction if user wants to minimize
        for metric in metrics:
            if metric.weight >= 1.0:
                if "return" in metric.name or "ratio" in metric.name or "score" in metric.name:
                    # These are naturally "higher is better", so flip
                    metric.direction = "minimize" if metric.direction == "maximize" else "maximize"
    
    # Extract constraints
    constraints = extract_constraints(question)
    
    # Extract horizon
    horizon = extract_horizon(question)
    
    # Extract context tags
    context_tags = extract_context_tags(question, domain)
    
    # Get action ranges for domain
    action_ranges = DOMAIN_ACTION_RANGES.get(domain, {})
    initial_state = _pack_defaults(domain, action_ranges)

    return FormalizedObjective(
        description=question,
        metrics=metrics,
        primary_direction=direction,
        constraints=constraints,
        horizon=horizon,
        context_tags=context_tags,
        success_criteria=[f"Achieve {direction}d objective metrics"],
        required_outputs=["ranked_scenarios", "metric_results", "uncertainty"],
        domain_hints=[domain],
        action_ranges=initial_state["action_ranges"],
        initial_state=initial_state["initial_state"],
    )


def _coerce_metric(raw: Dict[str, Any], allowed: Optional[List[str]]) -> Optional[ObjectiveMetric]:
    """Validate one LLM-proposed metric, grounding its name to the pack when possible."""
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name", "")).strip()
    if not name:
        return None
    # Ground to the pack's real metrics: drop hallucinated names the pack can't score.
    if allowed:
        if name not in allowed:
            match = next((m for m in allowed if m.lower() == name.lower()), None)
            if match is None:
                return None
            name = match
    direction = str(raw.get("direction", "maximize")).lower()
    if direction not in {"minimize", "maximize"}:
        direction = "maximize"
    try:
        weight = float(raw.get("weight", 1.0))
    except (TypeError, ValueError):
        weight = 1.0
    weight = max(0.0, min(weight, 1.0))
    return ObjectiveMetric(name=name, direction=direction, weight=weight)


def formalize_with_llm(
    question: str,
    domain_pack: Optional[str] = None,
    available_metrics: Optional[List[str]] = None,
) -> Optional[FormalizedObjective]:
    """
    Formalize objectives using an LLM (fast tier, multi-provider with fallback).

    Returns None if no LLM provider is available or the call fails, so the
    caller transparently falls back to deterministic heuristics.
    """
    from services.common import llm

    if not llm.is_enabled() or not llm.available_providers():
        logger.info("No LLM provider configured; using heuristic formalization")
        return None

    domain = detect_domain(question, domain_pack)

    system_prompt = (
        "You convert a user's optimization/simulation question into a structured "
        "objective specification. Respond with ONLY a JSON object of this shape:\n"
        "{\n"
        '  "metrics": [{"name": str, "direction": "maximize"|"minimize", "weight": 0.0-1.0}],\n'
        '  "primary_direction": "maximize"|"minimize",\n'
        '  "constraints": [{"name": str, "constraint_type": "min"|"max"|"eq"|"range", "value": number|null, "is_hard": bool}],\n'
        '  "horizon": str|null,\n'
        '  "context_tags": [str],\n'
        '  "success_criteria": [str]\n'
        "}\n"
        "Rules: choose 1-3 metrics that best capture the user's goal. "
        "Weights should sum to roughly 1.0. Do not invent metrics that are not "
        "measurable. If a list of available metrics is provided, you MUST only "
        "use names from that list."
    )

    user_prompt = f"Question: {question}\nDomain: {domain}"
    if available_metrics:
        user_prompt += f"\nAvailable metrics (use ONLY these names): {', '.join(available_metrics)}"

    try:
        result = llm.complete_json(
            system=system_prompt,
            user=user_prompt,
            tier=llm.LLMTier.FAST,
            temperature=0.1,
            max_tokens=1200,
        )
    except llm.LLMError as exc:
        logger.warning("LLM formalization unavailable (%s); using heuristics", type(exc).__name__)
        return None

    metrics: List[ObjectiveMetric] = []
    for raw in result.get("metrics", []) or []:
        metric = _coerce_metric(raw, available_metrics)
        if metric is not None:
            metrics.append(metric)

    # If grounding filtered everything out, the LLM output is not usable — fall back.
    if not metrics:
        logger.info("LLM produced no valid grounded metrics; using heuristics")
        return None

    constraints: List[Constraint] = []
    for raw in result.get("constraints", []) or []:
        if not isinstance(raw, dict) or not raw.get("name"):
            continue
        try:
            constraints.append(Constraint(**{k: raw[k] for k in raw if k in Constraint.model_fields}))
        except Exception:  # noqa: BLE001
            continue

    primary_direction = str(result.get("primary_direction", "maximize")).lower()
    if primary_direction not in {"minimize", "maximize"}:
        primary_direction = "maximize"

    defaults = _pack_defaults(domain, DOMAIN_ACTION_RANGES.get(domain, {}))

    return FormalizedObjective(
        description=question,
        metrics=metrics,
        primary_direction=primary_direction,
        constraints=constraints,
        horizon=result.get("horizon"),
        context_tags=[str(t) for t in (result.get("context_tags") or [])][:5] or [domain],
        success_criteria=[str(s) for s in (result.get("success_criteria") or [])] or
        [f"Achieve {primary_direction}d objective metrics"],
        required_outputs=["ranked_scenarios", "metric_results", "uncertainty"],
        domain_hints=[domain],
        action_ranges=defaults["action_ranges"],
        initial_state=defaults["initial_state"],
    )


def formalize_objective(
    question: str,
    domain_pack: Optional[str] = None,
    available_metrics: Optional[List[str]] = None,
    use_llm: bool = True,
) -> FormalizedObjective:
    """
    Main entry point for objective formalization.
    
    Tries LLM first, falls back to heuristics.
    """
    if use_llm:
        llm_result = formalize_with_llm(question, domain_pack, available_metrics)
        if llm_result is not None:
            return llm_result
    
    return formalize_heuristic(question, domain_pack)
