"""Expert definitions for MoE Committee."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Type

from pydantic import BaseModel, Field


class ExpertInput(BaseModel):
    """Standard input format for all experts."""

    task: str
    context: Dict[str, Any] = Field(default_factory=dict)
    evidence_refs: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    simulation_results: Dict[str, Any] | None = None


class ExpertContract(BaseModel):
    """Standard output contract for all experts."""

    expert_id: str
    output_type: str
    payload: Dict[str, Any]
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    assumptions: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    requires_escalation: bool = False


class ExpertBase(ABC):
    """
    Base class for all MoE experts.

    Experts must never fabricate simulation outputs.
    They may propose scenarios and reasoning only.
    """

    expert_id: str = "base"
    description: str = ""
    output_type: str = "generic"

    def input_schema(self) -> Type[BaseModel]:
        return ExpertInput

    @abstractmethod
    def output_schema(self) -> Type[BaseModel]:
        """Return the Pydantic model for payload validation."""
        raise NotImplementedError

    def _build_contract(
        self,
        payload: Dict[str, Any],
        confidence: float = 1.0,
        assumptions: List[str] | None = None,
        evidence_refs: List[str] | None = None,
        risks: List[str] | None = None,
        requires_escalation: bool = False,
    ) -> ExpertContract:
        schema = self.output_schema()
        validated = schema.model_validate(payload)
        return ExpertContract(
            expert_id=self.expert_id,
            output_type=self.output_type,
            payload=validated.model_dump(),
            confidence=confidence,
            assumptions=assumptions or [],
            evidence_refs=evidence_refs or [],
            risks=risks or [],
            requires_escalation=requires_escalation,
        )

    @abstractmethod
    async def execute(self, input_data: ExpertInput) -> ExpertContract:
        """Execute the expert's task."""
        raise NotImplementedError


class PlannerPayload(BaseModel):
    steps: List[Dict[str, Any]]
    dependencies: Dict[str, List[str]]
    estimated_complexity: str
    recommended_fidelity: str


class Planner(ExpertBase):
    expert_id = "planner"
    description = "Creates structured plans for simulation runs"
    output_type = "plan"

    def output_schema(self) -> Type[BaseModel]:
        return PlannerPayload

    async def execute(self, input_data: ExpertInput) -> ExpertContract:
        payload = {
            "steps": [
                {"id": "objectives", "action": "Define objectives"},
                {"id": "scenarios", "action": "Generate scenarios"},
                {"id": "simulate", "action": "Run simulations"},
                {"id": "analyze", "action": "Analyze results"},
            ],
            "dependencies": {"scenarios": ["objectives"], "simulate": ["scenarios"]},
            "estimated_complexity": "medium",
            "recommended_fidelity": "mid",
        }
        return self._build_contract(
            payload=payload,
            confidence=0.85,
            assumptions=["Objective metrics are well-defined"],
        )


class EvidenceCuratorPayload(BaseModel):
    evidence_refs: List[str]
    sources: List[str]
    credibility_scores: Dict[str, float]
    gaps: List[str]
    benchmark_candidates: List[Dict[str, Any]] = Field(default_factory=list)


class EvidenceCurator(ExpertBase):
    expert_id = "evidence_curator"
    description = "Retrieves and validates relevant evidence"
    output_type = "evidence"

    def output_schema(self) -> Type[BaseModel]:
        return EvidenceCuratorPayload

    async def execute(self, input_data: ExpertInput) -> ExpertContract:
        payload = {
            "evidence_refs": input_data.evidence_refs,
            "sources": [],
            "credibility_scores": {},
            "gaps": ["Need verified sources for benchmarks"],
            "benchmark_candidates": [],
        }
        return self._build_contract(
            payload=payload,
            confidence=0.8,
            evidence_refs=input_data.evidence_refs,
        )


class CauseModelerPayload(BaseModel):
    causal_graph: Dict[str, List[str]]
    key_drivers: List[str]
    uncertainties: Dict[str, float]


class CauseModeler(ExpertBase):
    expert_id = "cause_modeler"
    description = "Identifies causal relationships and key drivers"
    output_type = "causal_model"

    def output_schema(self) -> Type[BaseModel]:
        return CauseModelerPayload

    async def execute(self, input_data: ExpertInput) -> ExpertContract:
        payload = {
            "causal_graph": {},
            "key_drivers": [],
            "uncertainties": {},
        }
        return self._build_contract(
            payload=payload,
            confidence=0.75,
            assumptions=["Drivers are stable across scenarios"],
        )


class ScenarioIdea(BaseModel):
    scenario_id: str
    summary: str
    parameters: Dict[str, Any]
    priority: float = Field(ge=0.0, le=1.0, default=0.5)
    rationale: str | None = None


class ScenarioGeneratorPayload(BaseModel):
    scenario_ideas: List[ScenarioIdea]
    parameter_ranges: Dict[str, Dict[str, float]]
    coverage_notes: Dict[str, Any]


class ScenarioGenerator(ExpertBase):
    expert_id = "scenario_generator"
    description = "Generates diverse scenario variations"
    output_type = "scenario_ideas"

    def output_schema(self) -> Type[BaseModel]:
        return ScenarioGeneratorPayload

    async def execute(self, input_data: ExpertInput) -> ExpertContract:
        payload = {
            "scenario_ideas": [],
            "parameter_ranges": {},
            "coverage_notes": {},
        }
        return self._build_contract(
            payload=payload,
            confidence=0.9,
            assumptions=["Scenario space is sufficiently expressive"],
        )


class StatsPayload(BaseModel):
    calculations: Dict[str, Any]
    statistical_tests: List[Dict[str, Any]]
    validation_checks: Dict[str, bool]


class StatsExpert(ExpertBase):
    expert_id = "stats_expert"
    description = "Rigorous mathematical and statistical analysis"
    output_type = "analysis"

    def output_schema(self) -> Type[BaseModel]:
        return StatsPayload

    async def execute(self, input_data: ExpertInput) -> ExpertContract:
        payload = {
            "calculations": {},
            "statistical_tests": [],
            "validation_checks": {},
        }
        return self._build_contract(
            payload=payload,
            confidence=0.95,
        )


class CriticPayload(BaseModel):
    issues: List[Dict[str, Any]]
    recommendations: List[str]
    overall_quality: float = Field(ge=0.0, le=1.0, default=0.8)


class Critic(ExpertBase):
    expert_id = "critic"
    description = "Identifies issues and weaknesses"
    output_type = "critique"

    def output_schema(self) -> Type[BaseModel]:
        return CriticPayload

    async def execute(self, input_data: ExpertInput) -> ExpertContract:
        payload = {
            "issues": [],
            "recommendations": [],
            "overall_quality": 0.8,
        }
        return self._build_contract(
            payload=payload,
            confidence=0.85,
            risks=["Unverified assumptions may bias outcomes"],
        )


class RedTeamPayload(BaseModel):
    attack_vectors: List[Dict[str, Any]]
    failure_modes: List[Dict[str, Any]]
    mitigations: List[str]


class RedTeam(ExpertBase):
    expert_id = "red_team"
    description = "Identifies failure modes and risks"
    output_type = "red_team_report"

    def output_schema(self) -> Type[BaseModel]:
        return RedTeamPayload

    async def execute(self, input_data: ExpertInput) -> ExpertContract:
        payload = {
            "attack_vectors": [],
            "failure_modes": [],
            "mitigations": [],
        }
        return self._build_contract(
            payload=payload,
            confidence=0.8,
            risks=["Model leakage risk in data handling"],
        )


class JudgeExplainerPayload(BaseModel):
    score_explanations: List[str]
    factor_contributions: Dict[str, float]
    benchmark_refs: List[str]


class JudgeExplainer(ExpertBase):
    expert_id = "judge_explainer"
    description = "Explains deterministic scoring results"
    output_type = "judge_explanation"

    def output_schema(self) -> Type[BaseModel]:
        return JudgeExplainerPayload

    async def execute(self, input_data: ExpertInput) -> ExpertContract:
        payload = {
            "score_explanations": [],
            "factor_contributions": {},
            "benchmark_refs": [],
        }
        return self._build_contract(
            payload=payload,
            confidence=0.9,
        )


class ReportWriterPayload(BaseModel):
    sections: List[Dict[str, str]]
    executive_summary: str
    key_findings: List[str]
    visualizations: List[str]


class ReportWriter(ExpertBase):
    expert_id = "report_writer"
    description = "Generates structured reports"
    output_type = "report"

    def output_schema(self) -> Type[BaseModel]:
        return ReportWriterPayload

    async def execute(self, input_data: ExpertInput) -> ExpertContract:
        payload = {
            "sections": [],
            "executive_summary": "",
            "key_findings": [],
            "visualizations": [],
        }
        return self._build_contract(
            payload=payload,
            confidence=0.85,
        )


EXPERT_REGISTRY: Dict[str, Type[ExpertBase]] = {
    "planner": Planner,
    "evidence_curator": EvidenceCurator,
    "cause_modeler": CauseModeler,
    "scenario_generator": ScenarioGenerator,
    "stats_expert": StatsExpert,
    "critic": Critic,
    "red_team": RedTeam,
    "judge_explainer": JudgeExplainer,
    "report_writer": ReportWriter,
}


# Backwards-compatible aliases
PlannerExpert = Planner
EvidenceCuratorExpert = EvidenceCurator
CauseModelerExpert = CauseModeler
ScenarioGeneratorExpert = ScenarioGenerator
MathStatsExpert = StatsExpert
CriticExpert = Critic
RedTeamExpert = RedTeam
JudgeExplainerExpert = JudgeExplainer
ReportWriterExpert = ReportWriter
