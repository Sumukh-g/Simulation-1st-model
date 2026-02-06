"""Scoring endpoints."""
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..scorer import (
    scorer,
    MetricValue,
    RubricSpec,
    JudgeResult,
    ThresholdSpec,
)

router = APIRouter()


class ScoreRequest(BaseModel):
    """Score computation request."""

    scenario_id: str
    run_id: str
    metrics: List[MetricValue]
    rubric_id: str
    feasibility: float = 1.0
    confidence: float = 1.0
    constraint_violations: Dict[str, float] = Field(default_factory=dict)
    robustness_total: int = 0
    robustness_failures: int = 0
    domain: Optional[str] = None
    context_tags: List[str] = Field(default_factory=list)
    benchmark_ids: Optional[List[str]] = None


class ScoreResponse(BaseModel):
    """Score response."""

    result: JudgeResult
    explanation: Optional[str] = None


@router.post("/compute", response_model=ScoreResponse)
async def compute_score(request: ScoreRequest):
    """
    Compute deterministic score for a scenario.

    The score is computed using pure mathematical operations
    based on the rubric specification. No LLM involvement in scoring.
    """
    try:
        result = scorer.score(
            scenario_id=request.scenario_id,
            run_id=request.run_id,
            metrics=request.metrics,
            rubric_id=request.rubric_id,
            feasibility=request.feasibility,
            confidence=request.confidence,
            constraint_violations=request.constraint_violations,
            robustness_total=request.robustness_total,
            robustness_failures=request.robustness_failures,
            domain=request.domain,
            context_tags=request.context_tags,
            benchmark_ids=request.benchmark_ids,
        )

        explanation = await scorer.generate_explanation(result)

        return ScoreResponse(result=result, explanation=explanation)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/compute-with-llm", response_model=ScoreResponse)
async def compute_score_with_llm_explanation(request: ScoreRequest):
    """
    Compute score with LLM-generated explanation.

    The score is computed deterministically. The LLM only
    describes the math decisions - it cannot change scores.
    """
    try:
        result = scorer.score(
            scenario_id=request.scenario_id,
            run_id=request.run_id,
            metrics=request.metrics,
            rubric_id=request.rubric_id,
            feasibility=request.feasibility,
            confidence=request.confidence,
            constraint_violations=request.constraint_violations,
            robustness_total=request.robustness_total,
            robustness_failures=request.robustness_failures,
            domain=request.domain,
            context_tags=request.context_tags,
            benchmark_ids=request.benchmark_ids,
        )

        explanation = await scorer.generate_explanation(result, use_llm=True)

        return ScoreResponse(result=result, explanation=explanation)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/rubrics")
async def load_rubric(rubric: RubricSpec):
    """Load a rubric into the scorer."""
    scorer.load_rubric(rubric)
    return {"status": "loaded", "rubric_id": rubric.id}


@router.get("/rubrics")
async def list_rubrics():
    """List loaded rubrics."""
    return {
        "rubrics": [
            {
                "id": r.id,
                "name": r.name,
                "version": r.version,
                "metric_weights": r.metric_weights,
                "aggregation_method": r.aggregation_method,
            }
            for r in scorer._rubrics.values()
        ]
    }


@router.get("/rubrics/{rubric_id}")
async def get_rubric(rubric_id: str):
    """Get a specific rubric."""
    rubric = scorer._rubrics.get(rubric_id)
    if not rubric:
        raise HTTPException(status_code=404, detail=f"Rubric {rubric_id} not found")
    return rubric


@router.post("/batch")
async def score_batch(requests: List[ScoreRequest]):
    """Score multiple scenarios in batch."""
    results = []

    for req in requests:
        try:
            result = scorer.score(
                scenario_id=req.scenario_id,
                run_id=req.run_id,
                metrics=req.metrics,
                rubric_id=req.rubric_id,
                feasibility=req.feasibility,
                confidence=req.confidence,
                constraint_violations=req.constraint_violations,
                robustness_total=req.robustness_total,
                robustness_failures=req.robustness_failures,
                domain=req.domain,
                context_tags=req.context_tags,
                benchmark_ids=req.benchmark_ids,
            )
            results.append({"status": "success", "result": result})
        except Exception as e:
            results.append({"status": "error", "error": str(e)})

    return {"results": results}
