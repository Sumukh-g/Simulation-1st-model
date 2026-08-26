"""Expert definitions for MoE Committee."""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _resolve_tier(tier: Optional[str]):
    """Map a string/None tier to an LLMTier without importing at module load."""
    from services.common.llm import LLMTier

    if isinstance(tier, LLMTier):
        return tier
    if tier is None:
        return LLMTier.STANDARD
    try:
        return LLMTier(str(tier))
    except ValueError:
        return LLMTier.STANDARD


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

    # -- LLM helpers ------------------------------------------------------- #
    # Experts may call these to reason with real models. Every helper returns
    # None on any failure so callers fall back to deterministic behavior and
    # never fabricate simulation outputs.
    async def _llm_json(
        self, system: str, user: str, *, tier: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        try:
            from services.common import llm
        except Exception:  # pragma: no cover
            return None
        if not llm.is_enabled() or not llm.available_providers():
            return None
        chosen = _resolve_tier(tier)
        try:
            return await llm.acomplete_json(system=system, user=user, tier=chosen)
        except llm.LLMError as exc:
            logger.info("Expert '%s' LLM call failed (%s)", self.expert_id, type(exc).__name__)
            return None

    async def _llm_json_ensemble(self, system: str, user: str) -> List[Dict[str, Any]]:
        """Fan out to every configured provider and return all parsed JSON payloads.

        This realizes the "multiple models -> best output" committee: with several
        providers configured, each contributes a candidate that the caller merges;
        with one provider it is simply a single call.
        """
        try:
            from services.common import llm
        except Exception:  # pragma: no cover
            return []
        if not llm.is_enabled() or not llm.available_providers():
            return []
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            responses = await llm.ensemble(messages, json_mode=True)
        except Exception:  # noqa: BLE001
            return []
        payloads: List[Dict[str, Any]] = []
        for resp in responses:
            try:
                payloads.append(llm.extract_json(resp.text))
            except Exception:  # noqa: BLE001
                continue
        return payloads


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

    _SYSTEM = (
        "You are a causal-reasoning expert for decision optimization. Given a goal "
        "and constraints, identify the key decision levers and how they drive the "
        "outcome. Respond with ONLY JSON of shape:\n"
        '{"causal_graph": {"<driver>": ["<affected_metric_or_driver>", ...]}, '
        '"key_drivers": ["<driver>", ...], '
        '"uncertainties": {"<driver>": 0.0-1.0}}\n'
        "Keep it to 3-6 concrete drivers. Do not fabricate numeric simulation results."
    )

    def _prompt(self, input_data: ExpertInput) -> str:
        return json.dumps(
            {
                "goal": input_data.task,
                "constraints": input_data.constraints,
                "context": input_data.context,
            },
            default=str,
        )

    @staticmethod
    def _coerce(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return None
        graph_raw = payload.get("causal_graph", {})
        graph: Dict[str, List[str]] = {}
        if isinstance(graph_raw, dict):
            for node, children in graph_raw.items():
                if isinstance(children, list):
                    graph[str(node)] = [str(c) for c in children]
                elif children is not None:
                    graph[str(node)] = [str(children)]
        drivers = [str(d) for d in payload.get("key_drivers", []) if isinstance(payload.get("key_drivers"), list)]
        unc_raw = payload.get("uncertainties", {})
        unc: Dict[str, float] = {}
        if isinstance(unc_raw, dict):
            for k, v in unc_raw.items():
                try:
                    unc[str(k)] = max(0.0, min(1.0, float(v)))
                except (TypeError, ValueError):
                    continue
        if not graph and not drivers:
            return None
        return {"causal_graph": graph, "key_drivers": drivers, "uncertainties": unc}

    @classmethod
    def _merge(cls, payloads: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Consensus merge across provider candidates (union + averaged uncertainty)."""
        graph: Dict[str, List[str]] = {}
        drivers: List[str] = []
        unc_acc: Dict[str, List[float]] = {}
        for p in payloads:
            for node, children in p.get("causal_graph", {}).items():
                existing = graph.setdefault(node, [])
                for c in children:
                    if c not in existing:
                        existing.append(c)
            for d in p.get("key_drivers", []):
                if d not in drivers:
                    drivers.append(d)
            for k, v in p.get("uncertainties", {}).items():
                unc_acc.setdefault(k, []).append(v)
        uncertainties = {k: round(sum(vs) / len(vs), 3) for k, vs in unc_acc.items() if vs}
        return {"causal_graph": graph, "key_drivers": drivers, "uncertainties": uncertainties}

    async def execute(self, input_data: ExpertInput) -> ExpertContract:
        stakes = float(input_data.context.get("stakes", 0.5) or 0.5)
        use_ensemble = bool(input_data.context.get("use_ensemble"))
        user = self._prompt(input_data)

        candidates: List[Dict[str, Any]] = []
        if use_ensemble:
            for raw in await self._llm_json_ensemble(self._SYSTEM, user):
                coerced = self._coerce(raw)
                if coerced:
                    candidates.append(coerced)
        else:
            tier = "advanced" if stakes >= 0.8 else "standard"
            raw = await self._llm_json(self._SYSTEM, user, tier=tier)
            coerced = self._coerce(raw) if raw else None
            if coerced:
                candidates.append(coerced)

        if candidates:
            merged = self._merge(candidates)
            # More agreeing providers -> higher confidence, capped.
            confidence = min(0.95, 0.7 + 0.08 * (len(candidates) - 1))
            return self._build_contract(
                payload=merged,
                confidence=confidence,
                assumptions=[f"Causal model synthesized from {len(candidates)} model(s)"],
            )

        # Deterministic fallback: no fabricated drivers, low confidence, flag escalation.
        return self._build_contract(
            payload={"causal_graph": {}, "key_drivers": [], "uncertainties": {}},
            confidence=0.4,
            assumptions=["No LLM available; causal model not inferred"],
            requires_escalation=True,
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

    _SYSTEM = (
        "You are a critical reviewer of a decision-optimization plan. Identify concrete "
        "weaknesses and actionable fixes. Respond with ONLY JSON of shape:\n"
        '{"issues": [{"description": str, "severity": "low"|"medium"|"high"}], '
        '"recommendations": [str], "overall_quality": 0.0-1.0}\n'
        "Be specific; do not fabricate data."
    )

    async def execute(self, input_data: ExpertInput) -> ExpertContract:
        user = json.dumps(
            {"goal": input_data.task, "constraints": input_data.constraints, "context": input_data.context},
            default=str,
        )
        raw = await self._llm_json(self._SYSTEM, user, tier="standard")
        if isinstance(raw, dict):
            issues = [i for i in raw.get("issues", []) if isinstance(i, dict)]
            recs = [str(r) for r in raw.get("recommendations", []) if r]
            try:
                quality = max(0.0, min(1.0, float(raw.get("overall_quality", 0.8))))
            except (TypeError, ValueError):
                quality = 0.8
            return self._build_contract(
                payload={"issues": issues, "recommendations": recs, "overall_quality": quality},
                confidence=0.85,
                risks=[i.get("description", "") for i in issues if i.get("severity") == "high"][:3],
            )
        return self._build_contract(
            payload={"issues": [], "recommendations": [], "overall_quality": 0.8},
            confidence=0.6,
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

    _SYSTEM = (
        "You are a red-team analyst stress-testing a decision plan. Identify how it "
        "could fail or be gamed. Respond with ONLY JSON of shape:\n"
        '{"attack_vectors": [{"description": str}], '
        '"failure_modes": [{"description": str, "likelihood": "low"|"medium"|"high"}], '
        '"mitigations": [str]}\n'
        "Be specific and realistic; do not fabricate data."
    )

    async def execute(self, input_data: ExpertInput) -> ExpertContract:
        user = json.dumps(
            {"goal": input_data.task, "constraints": input_data.constraints, "context": input_data.context},
            default=str,
        )
        raw = await self._llm_json(self._SYSTEM, user, tier="standard")
        if isinstance(raw, dict):
            attacks = [a for a in raw.get("attack_vectors", []) if isinstance(a, dict)]
            failures = [f for f in raw.get("failure_modes", []) if isinstance(f, dict)]
            mitigations = [str(m) for m in raw.get("mitigations", []) if m]
            return self._build_contract(
                payload={"attack_vectors": attacks, "failure_modes": failures, "mitigations": mitigations},
                confidence=0.8,
                risks=[f.get("description", "") for f in failures][:3],
            )
        return self._build_contract(
            payload={"attack_vectors": [], "failure_modes": [], "mitigations": []},
            confidence=0.6,
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
