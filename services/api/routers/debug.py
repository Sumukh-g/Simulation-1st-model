"""Debug endpoints for MoE."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..auth import UserContext, get_current_user
from ..moe import MoECommittee, MoETask, TaskStage

router = APIRouter()


class SimulationResult(BaseModel):
    scenario_id: str
    score: float


class MoEDebugRequest(BaseModel):
    task: str
    stage: TaskStage = TaskStage.PLANNING
    stakes: float = 0.5
    context: Dict[str, Any] = Field(default_factory=dict)
    evidence_refs: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    simulation_results: List[SimulationResult] = Field(default_factory=list)


@router.post("/moe")
async def debug_moe(
    request: MoEDebugRequest,
    user: UserContext = Depends(get_current_user),
):
    committee = MoECommittee()
    task = MoETask(
        task=request.task,
        stage=request.stage,
        stakes=request.stakes,
        context=request.context,
        evidence_refs=request.evidence_refs,
        constraints=request.constraints,
        simulation_results=[result.model_dump() for result in request.simulation_results],
    )
    report = await committee.run(task)
    return {
        "routing": report.routing.model_dump(),
        "experts": [output.model_dump() for output in report.expert_outputs],
        "arbitration": report.arbitration.model_dump(),
        "escalation": report.escalation,
    }
