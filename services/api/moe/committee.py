"""MoE Committee orchestrator."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .arbitrator import ArbitrationEngine, ArbitrationResult
from .experts import ExpertContract, ExpertInput, EXPERT_REGISTRY
from .router import EscalationPolicy, MoERouter, RoutingDecision, TaskStage


class MoETask(BaseModel):
    """Task specification for MoE execution."""

    task: str
    stage: TaskStage = TaskStage.PLANNING
    stakes: float = 0.5
    context: Dict[str, Any] = Field(default_factory=dict)
    evidence_refs: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    simulation_results: List[Dict[str, Any]] = Field(default_factory=list)


class MoERunReport(BaseModel):
    routing: RoutingDecision
    expert_outputs: List[ExpertContract]
    arbitration: ArbitrationResult
    escalation: Dict[str, Any]


class MoECommittee:
    """Coordinates expert routing, execution, arbitration, and escalation."""

    def __init__(
        self,
        router: Optional[MoERouter] = None,
        arbitration_engine: Optional[ArbitrationEngine] = None,
        escalation_policy: Optional[EscalationPolicy] = None,
    ):
        self.router = router or MoERouter()
        self.arbitration_engine = arbitration_engine or ArbitrationEngine()
        self.escalation_policy = escalation_policy or self.router.escalation_policy

    async def run(self, task: MoETask) -> MoERunReport:
        routing = self.router.route(
            task_description=task.task,
            stage=task.stage,
            stakes=task.stakes,
            context=task.context,
        )
        expert_input = ExpertInput(
            task=task.task,
            # Surface routing decisions so experts can choose single-model vs
            # multi-model ensemble reasoning and the appropriate tier.
            context={
                **task.context,
                "use_ensemble": routing.use_ensemble,
                "stakes": task.stakes,
                "model_tier": routing.model_tier.value,
            },
            evidence_refs=task.evidence_refs,
            constraints=task.constraints,
            simulation_results={"results": task.simulation_results}
            if task.simulation_results
            else None,
        )

        outputs = await self._run_experts(routing, expert_input)
        arbitration = self.arbitration_engine.arbitrate(
            outputs,
            k_candidates=routing.k_candidates,
            simulation_results=task.simulation_results,
        )

        average_confidence = (
            sum(output.confidence for output in outputs) / len(outputs) if outputs else 1.0
        )
        top_gap = self.arbitration_engine.compute_top_gap(task.simulation_results)
        expert_escalations = any(output.requires_escalation for output in outputs)

        escalation = self.escalation_policy.decide(
            disagreement=arbitration.disagreement_score,
            uncertainty=1.0 - arbitration.agreement_score,
            stakes=task.stakes,
            average_confidence=average_confidence,
            top_candidate_gap=top_gap,
            expert_escalations=expert_escalations,
        )

        return MoERunReport(
            routing=routing,
            expert_outputs=outputs,
            arbitration=arbitration,
            escalation=escalation.model_dump(),
        )

    async def _run_experts(
        self,
        routing: RoutingDecision,
        expert_input: ExpertInput,
    ) -> List[ExpertContract]:
        outputs: List[ExpertContract] = []
        groups = routing.parallel_groups or [routing.experts]

        for group in groups:
            tasks = []
            for expert_id in group:
                expert_cls = EXPERT_REGISTRY.get(expert_id)
                if not expert_cls:
                    continue
                expert = expert_cls()
                tasks.append(expert.execute(expert_input))
            if tasks:
                results = await asyncio.gather(*tasks)
                outputs.extend(results)

        return outputs
