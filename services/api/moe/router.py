"""MoE Router - Stage routing and escalation."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TaskStage(str, Enum):
    """Stages of MoE work."""

    PLANNING = "planning"
    EVIDENCE_RETRIEVAL = "evidence_retrieval"
    CAUSE_MODELING = "cause_modeling"
    SCENARIO_GENERATION = "scenario_generation"
    STATS_ANALYSIS = "stats_analysis"
    MATH_ANALYSIS = "math_analysis"
    CRITIQUE = "critique"
    RED_TEAM = "red_team"
    EXPLAIN_JUDGMENT = "explain_judgment"
    REPORT_WRITING = "report_writing"


class ModelTier(str, Enum):
    """LLM model tiers."""

    FAST = "fast"
    STANDARD = "standard"
    ADVANCED = "advanced"


class RoutingDecision(BaseModel):
    """Decision from the router."""

    stage: TaskStage
    experts: List[str] = Field(default_factory=list)
    parallel_groups: List[List[str]] = Field(default_factory=list)
    k_candidates: int = 5
    model_tier: ModelTier = ModelTier.STANDARD
    use_ensemble: bool = False
    learned_score: float | None = None
    reasoning: str = ""


class RouterPolicy(BaseModel):
    """Rule-based routing policy with optional learned scoring."""

    use_learned_scoring: bool = False
    high_stakes_threshold: float = 0.8
    scenario_k_default: int = 8

    def route(
        self,
        task: str,
        stage: TaskStage,
        stakes: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> RoutingDecision:
        context = context or {}
        experts = self._stage_experts(stage)
        use_ensemble = stakes >= self.high_stakes_threshold
        if use_ensemble:
            if "critic" not in experts:
                experts.append("critic")
            if "red_team" not in experts:
                experts.append("red_team")

        k_candidates = self._k_candidates(stage, context)
        model_tier = self._determine_model_tier(task, stakes, context)
        learned_score = self._learned_score(task, context) if self.use_learned_scoring else None

        parallel_groups = [experts]
        return RoutingDecision(
            stage=stage,
            experts=experts,
            parallel_groups=parallel_groups,
            k_candidates=k_candidates,
            model_tier=model_tier,
            use_ensemble=use_ensemble,
            learned_score=learned_score,
            reasoning=f"Stage {stage} routed to {experts}",
        )

    def _stage_experts(self, stage: TaskStage) -> List[str]:
        mapping = {
            TaskStage.PLANNING: ["planner"],
            TaskStage.EVIDENCE_RETRIEVAL: ["evidence_curator"],
            TaskStage.CAUSE_MODELING: ["cause_modeler"],
            TaskStage.SCENARIO_GENERATION: ["scenario_generator"],
            TaskStage.STATS_ANALYSIS: ["stats_expert"],
            TaskStage.MATH_ANALYSIS: ["stats_expert"],
            TaskStage.CRITIQUE: ["critic"],
            TaskStage.RED_TEAM: ["red_team"],
            TaskStage.EXPLAIN_JUDGMENT: ["judge_explainer"],
            TaskStage.REPORT_WRITING: ["report_writer"],
        }
        return list(mapping.get(stage, ["planner"]))

    def _k_candidates(self, stage: TaskStage, context: Dict[str, Any]) -> int:
        if stage == TaskStage.SCENARIO_GENERATION:
            return int(context.get("k_candidates", self.scenario_k_default))
        return int(context.get("k_candidates", 5))

    def _determine_model_tier(
        self,
        description: str,
        stakes: float,
        context: Dict[str, Any],
    ) -> ModelTier:
        if stakes >= 0.85:
            return ModelTier.ADVANCED
        if stakes >= 0.5 or len(description) > 500:
            return ModelTier.STANDARD
        return ModelTier.FAST

    def _learned_score(self, description: str, context: Dict[str, Any]) -> float:
        """Stub for learned routing score."""
        learned_score = context.get("learned_routing_score")
        if isinstance(learned_score, (int, float)):
            return float(learned_score)
        return 0.5


class EscalationDecision(BaseModel):
    """Decision for escalation actions."""

    escalate: bool
    actions: List[str]
    reason: str
    metrics: Dict[str, float]


class EscalationPolicy(BaseModel):
    """Policy for escalation decisions."""

    disagreement_threshold: float = 0.35
    uncertainty_threshold: float = 0.5
    top_gap_threshold: float = 0.05
    high_stakes_threshold: float = 0.8
    low_confidence_threshold: float = 0.55

    def decide(
        self,
        *,
        disagreement: float,
        uncertainty: float,
        stakes: float,
        average_confidence: float,
        top_candidate_gap: float | None,
        expert_escalations: bool,
    ) -> EscalationDecision:
        actions: List[str] = []
        reasons: List[str] = []

        if disagreement >= self.disagreement_threshold:
            actions.append("upgrade_llm_tier")
            reasons.append("high_disagreement")

        if uncertainty >= self.uncertainty_threshold:
            actions.append("upgrade_simulation_fidelity")
            reasons.append("high_uncertainty")

        if top_candidate_gap is not None and top_candidate_gap <= self.top_gap_threshold:
            actions.append("upgrade_simulation_fidelity")
            reasons.append("top_candidates_close")

        if stakes >= self.high_stakes_threshold and average_confidence <= self.low_confidence_threshold:
            actions.append("human_review")
            reasons.append("high_stakes_low_confidence")

        if expert_escalations:
            actions.append("human_review")
            reasons.append("expert_requested_escalation")

        escalate = bool(actions)
        return EscalationDecision(
            escalate=escalate,
            actions=sorted(set(actions)),
            reason="; ".join(sorted(set(reasons))) if reasons else "no_escalation",
            metrics={
                "disagreement": disagreement,
                "uncertainty": uncertainty,
                "stakes": stakes,
                "average_confidence": average_confidence,
                "top_candidate_gap": top_candidate_gap if top_candidate_gap is not None else 0.0,
            },
        )


class MoERouter:
    """Router wrapper providing stage inference and routing."""

    def __init__(
        self,
        router_policy: Optional[RouterPolicy] = None,
        escalation_policy: Optional[EscalationPolicy] = None,
    ):
        self.router_policy = router_policy or RouterPolicy()
        self.escalation_policy = escalation_policy or EscalationPolicy()

    def route(
        self,
        task_description: str,
        stage: Optional[TaskStage] = None,
        stakes: float = 0.5,
        context: Optional[Dict[str, Any]] = None,
    ) -> RoutingDecision:
        if stage is None:
            stage = self._infer_stage(task_description)
        return self.router_policy.route(task_description, stage, stakes, context)

    def _infer_stage(self, description: str) -> TaskStage:
        description_lower = description.lower()
        if any(kw in description_lower for kw in ["plan", "strategy", "approach"]):
            return TaskStage.PLANNING
        if any(kw in description_lower for kw in ["evidence", "document", "source"]):
            return TaskStage.EVIDENCE_RETRIEVAL
        if any(kw in description_lower for kw in ["cause", "driver", "why"]):
            return TaskStage.CAUSE_MODELING
        if any(kw in description_lower for kw in ["scenario", "what if", "generate"]):
            return TaskStage.SCENARIO_GENERATION
        if any(kw in description_lower for kw in ["stat", "math", "analysis"]):
            return TaskStage.STATS_ANALYSIS
        if any(kw in description_lower for kw in ["critique", "review"]):
            return TaskStage.CRITIQUE
        if any(kw in description_lower for kw in ["risk", "adversar", "attack"]):
            return TaskStage.RED_TEAM
        if any(kw in description_lower for kw in ["explain", "score", "judge"]):
            return TaskStage.EXPLAIN_JUDGMENT
        if any(kw in description_lower for kw in ["report", "summary", "write"]):
            return TaskStage.REPORT_WRITING
        return TaskStage.PLANNING
