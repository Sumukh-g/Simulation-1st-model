"""Benchmark endpoints."""
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..scorer import scorer, BenchmarkSpec

router = APIRouter()


class BenchmarkCompareRequest(BaseModel):
    """Request to compare against benchmarks."""

    metrics: dict  # {metric_name: value}
    benchmark_ids: List[str] = Field(default_factory=list)  # Empty = use context
    domain: Optional[str] = None
    context_tags: List[str] = Field(default_factory=list)


class BenchmarkSelectRequest(BaseModel):
    """Request to select benchmarks by context."""

    domain: Optional[str] = None
    context_tags: List[str] = Field(default_factory=list)
    metric_names: List[str] = Field(default_factory=list)


@router.post("")
async def load_benchmark(benchmark: BenchmarkSpec):
    """Load a benchmark into the scorer."""
    scorer.load_benchmark(benchmark)
    return {"status": "loaded", "benchmark_id": benchmark.id}


@router.get("")
async def list_benchmarks():
    """List all loaded benchmarks."""
    return {
        "benchmarks": [
            {
                "id": b.id,
                "name": b.name,
                "metric": b.metric_name,
                "threshold": b.threshold_value,
                "type": b.threshold_type,
                "credibility_weight": b.credibility_weight,
                "domain": b.domain,
                "context_tags": b.context_tags,
            }
            for b in scorer._benchmarks.values()
        ]
    }


@router.get("/{benchmark_id}")
async def get_benchmark(benchmark_id: str):
    """Get a specific benchmark."""
    bench = scorer._benchmarks.get(benchmark_id)
    if not bench:
        return {"error": f"Benchmark {benchmark_id} not found"}
    return bench


@router.post("/select")
async def select_benchmarks(request: BenchmarkSelectRequest):
    """Select benchmarks based on context."""
    selected = scorer.select_benchmarks(
        domain=request.domain,
        context_tags=request.context_tags,
        metric_names=request.metric_names if request.metric_names else None,
    )

    return {
        "count": len(selected),
        "benchmarks": [
            {
                "id": b.id,
                "name": b.name,
                "metric": b.metric_name,
                "threshold": b.threshold_value,
                "type": b.threshold_type,
                "domain": b.domain,
                "context_tags": b.context_tags,
            }
            for b in selected
        ],
    }


@router.post("/compare")
async def compare_benchmarks(request: BenchmarkCompareRequest):
    """Compare metrics against benchmarks."""
    from ..scorer import MetricValue

    # Convert dict to MetricValue list
    metrics = [
        MetricValue(name=name, value=value)
        for name, value in request.metrics.items()
    ]

    # Get comparisons
    comparisons = scorer._compare_benchmarks(
        metrics=metrics,
        domain=request.domain,
        context_tags=request.context_tags,
        benchmark_ids=request.benchmark_ids if request.benchmark_ids else None,
    )

    passed = sum(1 for c in comparisons if c.passed)
    total = len(comparisons)

    # Compute weighted score
    weighted_sum = sum(c.weighted_pass for c in comparisons)
    total_weight = sum(c.credibility_weight * c.recency_weight for c in comparisons)
    weighted_score = weighted_sum / total_weight if total_weight > 0 else 0.0

    return {
        "passed": passed,
        "total": total,
        "pass_rate": passed / total if total > 0 else 0,
        "weighted_score": weighted_score,
        "comparisons": [
            {
                "benchmark_id": c.benchmark_id,
                "name": c.benchmark_name,
                "metric": c.metric_name,
                "value": c.metric_value,
                "threshold": c.threshold_value,
                "threshold_type": c.threshold_type,
                "passed": c.passed,
                "margin": c.margin,
                "credibility_weight": c.credibility_weight,
                "recency_weight": c.recency_weight,
                "weighted_pass": c.weighted_pass,
            }
            for c in comparisons
        ],
    }
