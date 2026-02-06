# GSIP Judge Service

Deterministic rubric scoring engine with context-based benchmarks.

## Overview

The Judge Service provides:
- **Deterministic Scoring**: Pure mathematical computation, no LLM involvement
- **Threshold Scoring**: acceptable/good/very_good/excellent levels
- **Context-based Benchmark Selection**: Domain and tag-based filtering
- **Credibility & Recency Weighting**: Trust older sources less
- **Confidence Penalties**: Uncertainty width + robustness failures
- **Rubric Aggregation**: weighted_sum, geometric_mean, or min
- **Optional LLM Explainer**: Describes math decisions (cannot change scores)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DeterministicScorer                       │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    Scoring Pipeline                      ││
│  │  1. Threshold Score    →  per-metric level assignment   ││
│  │  2. Weight Application →  rubric weights                ││
│  │  3. Aggregation        →  weighted_sum/geo_mean/min     ││
│  │  4. Penalty Application →  constraints, confidence      ││
│  │  5. Benchmark Comparison →  context-selected            ││
│  └─────────────────────────────────────────────────────────┘│
│              │                                               │
│  ┌───────────┼───────────┬───────────┬───────────┐          │
│  ▼           ▼           ▼           ▼           ▼          │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐│
│ │Threshold│ │Context  │ │Confidence│ │Recency │ │LLM      ││
│ │Scorer   │ │Selector │ │Calculator│ │Weighter│ │Explainer││
│ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘│
└─────────────────────────────────────────────────────────────┘
```

## Scoring Formula

```
final_score = raw_aggregate
            × feasibility_multiplier
            × (1 - total_penalty)
            - constraint_penalty

where:
  raw_aggregate = aggregation(weighted_threshold_scores)
  total_penalty = confidence_penalty + uncertainty_penalty + robustness_penalty
```

## Threshold Levels

| Level | Score | Description |
|-------|-------|-------------|
| UNACCEPTABLE | 0.0 | Below minimum acceptable |
| ACCEPTABLE | 0.5 | Meets minimum requirements |
| GOOD | 0.7 | Better than acceptable |
| VERY_GOOD | 0.85 | Strong performance |
| EXCELLENT | 1.0 | Outstanding performance |

## Usage

### Basic Scoring

```python
from services.judge import (
    DeterministicScorer,
    RubricSpec,
    MetricValue,
    ThresholdSpec,
)

scorer = DeterministicScorer()

# Load rubric
rubric = RubricSpec(
    id="impact-rubric",
    name="Impact Assessment Rubric",
    metric_weights={
        "impact": 0.4,
        "cost": 0.3,
        "feasibility": 0.2,
        "confidence": 0.1,
    },
    thresholds=[
        ThresholdSpec(
            metric_name="impact",
            acceptable=0.3,
            good=0.5,
            very_good=0.7,
            excellent=0.9,
        ),
        ThresholdSpec(
            metric_name="cost",
            acceptable=100000,
            good=50000,
            very_good=25000,
            excellent=10000,
            direction="lower_is_better",
        ),
    ],
    aggregation_method="weighted_sum",
)
scorer.load_rubric(rubric)

# Score a scenario
result = scorer.score(
    scenario_id="s-001",
    run_id="r-001",
    metrics=[
        MetricValue(name="impact", value=0.75, uncertainty=0.05),
        MetricValue(name="cost", value=30000),
        MetricValue(name="feasibility", value=0.9),
        MetricValue(name="confidence", value=0.85),
    ],
    rubric_id="impact-rubric",
    feasibility=0.95,
    confidence=0.8,
)

print(f"Score: {result.score:.4f}")
print(f"Level: {result.threshold_level.value}")
```

### Context-Based Benchmark Selection

```python
from services.judge import BenchmarkSpec

# Load benchmarks with context
scorer.load_benchmark(BenchmarkSpec(
    id="finance-roi-min",
    name="Minimum ROI",
    metric_name="roi",
    threshold_value=0.05,
    threshold_type="min",
    credibility_weight=0.9,
    domain="finance",
    context_tags=["investment", "quarterly"],
))

scorer.load_benchmark(BenchmarkSpec(
    id="spatial-coverage",
    name="Coverage Threshold",
    metric_name="coverage",
    threshold_value=0.8,
    threshold_type="min",
    domain="spatial",
    context_tags=["urban", "planning"],
))

# Select benchmarks by context
benchmarks = scorer.select_benchmarks(
    domain="finance",
    context_tags=["investment"],
)
```

### Confidence Penalties

```python
# Metrics with uncertainty
metrics = [
    MetricValue(name="impact", value=0.8, uncertainty=0.15),  # High uncertainty
    MetricValue(name="cost", value=50000, uncertainty=5000),
]

# With robustness failures
result = scorer.score(
    scenario_id="s-002",
    run_id="r-001",
    metrics=metrics,
    rubric_id="impact-rubric",
    robustness_total=10,
    robustness_failures=3,  # 30% failure rate
)

# Penalties are applied automatically
print(f"Uncertainty Penalty: {result.breakdown.uncertainty_penalty}")
print(f"Robustness Penalty: {result.breakdown.robustness_penalty}")
```

### LLM Explanation (Optional)

```python
# Generate explanation (does NOT change score)
explanation = await scorer.generate_explanation(result)
print(explanation)

# With LLM prose (optional)
explanation = await scorer.generate_explanation(result, use_llm=True)
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/score/compute` | POST | Compute score for a scenario |
| `/score/compute-with-llm` | POST | Compute with LLM explanation |
| `/score/batch` | POST | Score multiple scenarios |
| `/score/rubrics` | GET/POST | List/load rubrics |
| `/benchmarks` | GET/POST | List/load benchmarks |
| `/benchmarks/select` | POST | Select by context |
| `/benchmarks/compare` | POST | Compare metrics |

## JudgeResult Structure

```python
JudgeResult(
    scenario_id="s-001",
    run_id="r-001",
    rubric_id="impact-rubric",
    rubric_version="1.0",
    score=0.7234,
    threshold_level=ThresholdLevel.GOOD,
    breakdown=ScoreBreakdown(
        metric_breakdowns=[
            MetricBreakdown(
                name="impact",
                raw_value=0.75,
                threshold_level=ThresholdLevel.VERY_GOOD,
                threshold_score=0.85,
                weight=0.4,
                weighted_score=0.34,
                uncertainty=0.05,
                uncertainty_penalty=0.003,
            ),
            # ...more metrics
        ],
        raw_aggregate=0.78,
        constraint_penalties={},
        feasibility_multiplier=0.95,
        confidence_penalty=0.02,
        uncertainty_penalty=0.01,
        robustness_penalty=0.03,
        total_penalty=0.06,
        final_score=0.7234,
    ),
    benchmark_comparisons=[
        BenchmarkComparison(
            benchmark_id="finance-roi-min",
            passed=True,
            credibility_weight=0.9,
            recency_weight=0.85,
            weighted_pass=0.765,
        ),
    ],
    benchmarks_passed=1,
    benchmarks_total=1,
    benchmark_weighted_score=0.765,
)
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `confidence_penalty_rate` | 0.1 | Penalty per unit low confidence |
| `uncertainty_penalty_rate` | 0.05 | Penalty per unit uncertainty |
| `robustness_penalty_rate` | 0.1 | Penalty per robustness failure |
| `feasibility_weight` | 1.0 | Weight for feasibility multiplier |
| `aggregation_method` | weighted_sum | How to combine metrics |

## Key Principles

1. **Deterministic**: Same inputs always produce same scores
2. **Transparent**: Full breakdown of how score was computed
3. **LLM-free Scoring**: LLM only explains, never scores
4. **Weighted Benchmarks**: Credibility and recency matter
5. **Penalty Composition**: Multiple penalty sources combine additively
