"""Objective Formalizer - Converts user questions into structured ObjectiveSpecs."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

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
        "steps": {"min": 5, "max": 50},
    },
}


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
        action_ranges=action_ranges,
        initial_state={},
    )


def formalize_with_llm(
    question: str,
    domain_pack: Optional[str] = None,
    available_metrics: Optional[List[str]] = None,
) -> Optional[FormalizedObjective]:
    """
    Formalize objectives using an LLM.
    
    Returns None if LLM is unavailable or fails.
    """
    # Check for LLM availability
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.info("No LLM API key found, using heuristic formalization")
        return None
    
    try:
        # Import LLM client
        import openai
        client = openai.OpenAI()
        
        # Build the prompt
        system_prompt = """You are an objective formalization expert. Given a user's question about optimization or simulation, extract:
1. The objective metrics to optimize (with direction: minimize or maximize)
2. Constraints (budget, time, risk, etc.)
3. Time horizon if mentioned
4. Context tags relevant to the domain
5. Success criteria

Output JSON matching this schema:
{
    "metrics": [{"name": "metric_name", "direction": "maximize|minimize", "weight": 0.0-1.0}],
    "primary_direction": "maximize|minimize",
    "constraints": [{"name": "constraint_name", "constraint_type": "min|max|eq", "value": null, "is_hard": false}],
    "horizon": "time period or null",
    "context_tags": ["tag1", "tag2"],
    "success_criteria": ["criterion1"],
    "domain_hints": ["likely_domain_pack"]
}"""

        user_prompt = f"Question: {question}"
        if domain_pack:
            user_prompt += f"\nDomain pack hint: {domain_pack}"
        if available_metrics:
            user_prompt += f"\nAvailable metrics: {', '.join(available_metrics)}"
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=1000,
            temperature=0.1,
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # Parse into FormalizedObjective
        metrics = [
            ObjectiveMetric(**m) for m in result.get("metrics", [])
        ]
        constraints = [
            Constraint(**c) for c in result.get("constraints", [])
        ]
        
        domain = detect_domain(question, domain_pack)
        action_ranges = DOMAIN_ACTION_RANGES.get(domain, {})
        
        return FormalizedObjective(
            description=question,
            metrics=metrics,
            primary_direction=result.get("primary_direction", "maximize"),
            constraints=constraints,
            horizon=result.get("horizon"),
            context_tags=result.get("context_tags", []),
            success_criteria=result.get("success_criteria", []),
            required_outputs=["ranked_scenarios", "metric_results"],
            domain_hints=result.get("domain_hints", [domain]),
            action_ranges=action_ranges,
            initial_state={},
        )
        
    except Exception as e:
        logger.warning(f"LLM formalization failed: {e}")
        return None


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
