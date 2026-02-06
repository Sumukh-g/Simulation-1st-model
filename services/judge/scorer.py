"""Deterministic Scoring Engine with full feature set."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field


class ThresholdLevel(str, Enum):
    """Threshold scoring levels."""

    UNACCEPTABLE = "unacceptable"
    ACCEPTABLE = "acceptable"
    GOOD = "good"
    VERY_GOOD = "very_good"
    EXCELLENT = "excellent"


# Numeric scores for threshold levels
THRESHOLD_SCORES = {
    ThresholdLevel.UNACCEPTABLE: 0.0,
    ThresholdLevel.ACCEPTABLE: 0.5,
    ThresholdLevel.GOOD: 0.7,
    ThresholdLevel.VERY_GOOD: 0.85,
    ThresholdLevel.EXCELLENT: 1.0,
}


class MetricValue(BaseModel):
    """A metric value with metadata."""

    name: str
    value: float
    unit: Optional[str] = None
    uncertainty: Optional[float] = None  # Uncertainty width (std dev or CI width)


class ThresholdSpec(BaseModel):
    """Thresholds for a metric."""

    metric_name: str
    acceptable: float  # Minimum for acceptable
    good: float  # Minimum for good
    very_good: float  # Minimum for very_good
    excellent: float  # Minimum for excellent
    direction: str = "higher_is_better"  # or "lower_is_better"


class RubricSpec(BaseModel):
    """Rubric specification for scoring."""

    id: str
    name: str
    metric_weights: Dict[str, float]
    thresholds: List[ThresholdSpec] = Field(default_factory=list)
    constraint_penalties: Dict[str, float] = Field(default_factory=dict)
    feasibility_weight: float = 1.0
    confidence_penalty_rate: float = 0.1
    uncertainty_penalty_rate: float = 0.05  # Penalty per unit uncertainty
    robustness_penalty_rate: float = 0.1  # Penalty per robustness failure
    aggregation_method: str = "weighted_sum"  # weighted_sum, geometric_mean, min
    version: str = "1.0"


class BenchmarkSpec(BaseModel):
    """Benchmark specification for comparison."""

    id: str
    name: str
    metric_name: str
    threshold_value: float
    threshold_type: str = "min"  # 'min', 'max', 'target'
    credibility_weight: float = 1.0  # Source credibility
    recency_date: Optional[datetime] = None  # For recency weighting
    domain: Optional[str] = None  # Domain context
    context_tags: List[str] = Field(default_factory=list)  # Context matching
    source_id: Optional[str] = None


class MetricBreakdown(BaseModel):
    """Breakdown for a single metric."""

    name: str
    raw_value: float
    threshold_level: ThresholdLevel
    threshold_score: float
    weight: float
    weighted_score: float
    uncertainty: float = 0.0
    uncertainty_penalty: float = 0.0


class BenchmarkComparison(BaseModel):
    """Result of comparing against a benchmark."""

    benchmark_id: str
    benchmark_name: str
    metric_name: str
    metric_value: float
    threshold_value: float
    threshold_type: str
    passed: bool
    margin: float
    credibility_weight: float
    recency_weight: float
    weighted_pass: float  # 1.0 * credibility * recency if passed, else 0


class ScoreBreakdown(BaseModel):
    """Detailed score breakdown."""

    metric_breakdowns: List[MetricBreakdown] = Field(default_factory=list)
    raw_aggregate: float = 0.0
    constraint_penalties: Dict[str, float] = Field(default_factory=dict)
    total_constraint_penalty: float = 0.0
    feasibility_multiplier: float = 1.0
    confidence_penalty: float = 0.0
    uncertainty_penalty: float = 0.0
    robustness_penalty: float = 0.0
    total_penalty: float = 0.0
    final_score: float = 0.0

    # Legacy compatibility
    metric_scores: Dict[str, float] = Field(default_factory=dict)
    metric_weights: Dict[str, float] = Field(default_factory=dict)
    weighted_scores: Dict[str, float] = Field(default_factory=dict)


class JudgeResult(BaseModel):
    """Complete judging result."""

    scenario_id: str
    run_id: str
    rubric_id: str
    rubric_version: str
    breakdown: ScoreBreakdown
    score: float
    threshold_level: ThresholdLevel
    benchmark_comparisons: List[BenchmarkComparison] = Field(default_factory=list)
    benchmarks_passed: int = 0
    benchmarks_total: int = 0
    benchmark_weighted_score: float = 0.0
    explanation: Optional[str] = None
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ContextSelector:
    """Context-based benchmark selection."""

    def __init__(self):
        self._benchmarks: Dict[str, BenchmarkSpec] = {}

    def register(self, benchmark: BenchmarkSpec) -> None:
        """Register a benchmark."""
        self._benchmarks[benchmark.id] = benchmark

    def select(
        self,
        domain: Optional[str] = None,
        context_tags: Optional[List[str]] = None,
        metric_names: Optional[List[str]] = None,
    ) -> List[BenchmarkSpec]:
        """Select benchmarks based on context."""
        context_tags = context_tags or []
        selected = []

        for bench in self._benchmarks.values():
            # Domain filter
            if domain and bench.domain and bench.domain != domain:
                continue

            # Metric filter
            if metric_names and bench.metric_name not in metric_names:
                continue

            # Context tag matching (any match is sufficient)
            if context_tags and bench.context_tags:
                if not any(tag in bench.context_tags for tag in context_tags):
                    continue

            selected.append(bench)

        return selected

    def compute_recency_weight(
        self,
        benchmark: BenchmarkSpec,
        reference_date: Optional[datetime] = None,
        half_life_days: float = 365.0,
    ) -> float:
        """Compute recency weight with exponential decay."""
        if not benchmark.recency_date:
            return 1.0

        reference = reference_date or datetime.now(timezone.utc)
        age_days = (reference - benchmark.recency_date).days

        if age_days <= 0:
            return 1.0

        # Exponential decay
        decay = math.exp(-0.693 * age_days / half_life_days)
        return max(0.1, decay)  # Minimum weight of 0.1


class ThresholdScorer:
    """Threshold-based scoring."""

    @staticmethod
    def score_value(
        value: float,
        threshold: ThresholdSpec,
    ) -> tuple[ThresholdLevel, float]:
        """Score a value against thresholds."""
        if threshold.direction == "lower_is_better":
            # Invert comparison
            if value <= threshold.excellent:
                return ThresholdLevel.EXCELLENT, THRESHOLD_SCORES[ThresholdLevel.EXCELLENT]
            elif value <= threshold.very_good:
                return ThresholdLevel.VERY_GOOD, THRESHOLD_SCORES[ThresholdLevel.VERY_GOOD]
            elif value <= threshold.good:
                return ThresholdLevel.GOOD, THRESHOLD_SCORES[ThresholdLevel.GOOD]
            elif value <= threshold.acceptable:
                return ThresholdLevel.ACCEPTABLE, THRESHOLD_SCORES[ThresholdLevel.ACCEPTABLE]
            else:
                return ThresholdLevel.UNACCEPTABLE, THRESHOLD_SCORES[ThresholdLevel.UNACCEPTABLE]
        else:
            # Higher is better (default)
            if value >= threshold.excellent:
                return ThresholdLevel.EXCELLENT, THRESHOLD_SCORES[ThresholdLevel.EXCELLENT]
            elif value >= threshold.very_good:
                return ThresholdLevel.VERY_GOOD, THRESHOLD_SCORES[ThresholdLevel.VERY_GOOD]
            elif value >= threshold.good:
                return ThresholdLevel.GOOD, THRESHOLD_SCORES[ThresholdLevel.GOOD]
            elif value >= threshold.acceptable:
                return ThresholdLevel.ACCEPTABLE, THRESHOLD_SCORES[ThresholdLevel.ACCEPTABLE]
            else:
                return ThresholdLevel.UNACCEPTABLE, THRESHOLD_SCORES[ThresholdLevel.UNACCEPTABLE]

    @staticmethod
    def interpolate_score(
        value: float,
        threshold: ThresholdSpec,
    ) -> float:
        """Interpolate score between thresholds for smoother gradients."""
        if threshold.direction == "lower_is_better":
            # Invert thresholds
            thresholds = [
                (float("inf"), 0.0),
                (threshold.acceptable, 0.5),
                (threshold.good, 0.7),
                (threshold.very_good, 0.85),
                (threshold.excellent, 1.0),
            ]
            # Sort descending for lower_is_better
            thresholds = sorted(thresholds, key=lambda x: x[0], reverse=True)
        else:
            thresholds = [
                (float("-inf"), 0.0),
                (threshold.acceptable, 0.5),
                (threshold.good, 0.7),
                (threshold.very_good, 0.85),
                (threshold.excellent, 1.0),
            ]

        # Find the two surrounding thresholds
        for i in range(len(thresholds) - 1):
            t1_val, t1_score = thresholds[i]
            t2_val, t2_score = thresholds[i + 1]

            if threshold.direction == "lower_is_better":
                if t1_val >= value >= t2_val:
                    # Interpolate
                    if t1_val == float("inf"):
                        return t1_score
                    ratio = (t1_val - value) / (t1_val - t2_val) if t1_val != t2_val else 0
                    return t1_score + ratio * (t2_score - t1_score)
            else:
                if t1_val <= value <= t2_val:
                    # Interpolate
                    if t1_val == float("-inf"):
                        return t1_score
                    ratio = (value - t1_val) / (t2_val - t1_val) if t2_val != t1_val else 0
                    return t1_score + ratio * (t2_score - t1_score)

        # If above excellent
        return 1.0


class ConfidencePenaltyCalculator:
    """Calculates confidence penalties from uncertainty and robustness."""

    @staticmethod
    def from_uncertainty(
        metrics: List[MetricValue],
        penalty_rate: float,
    ) -> float:
        """Calculate penalty from uncertainty widths."""
        total_uncertainty = 0.0
        count = 0

        for m in metrics:
            if m.uncertainty is not None and m.uncertainty > 0:
                # Normalize uncertainty by value magnitude
                if abs(m.value) > 1e-10:
                    relative_uncertainty = m.uncertainty / abs(m.value)
                else:
                    relative_uncertainty = m.uncertainty
                total_uncertainty += relative_uncertainty
                count += 1

        if count == 0:
            return 0.0

        avg_uncertainty = total_uncertainty / count
        return avg_uncertainty * penalty_rate

    @staticmethod
    def from_robustness_failures(
        total_tests: int,
        failures: int,
        penalty_rate: float,
    ) -> float:
        """Calculate penalty from robustness test failures."""
        if total_tests == 0:
            return 0.0

        failure_rate = failures / total_tests
        return failure_rate * penalty_rate


class DeterministicScorer:
    """
    Deterministic scoring engine.

    All scoring is pure mathematical computation.
    LLM is only used for generating explanations AFTER scoring.
    """

    def __init__(self):
        self._rubrics: Dict[str, RubricSpec] = {}
        self._benchmarks: Dict[str, BenchmarkSpec] = {}
        self._context_selector = ContextSelector()
        self._threshold_scorer = ThresholdScorer()

    def load_rubric(self, rubric: RubricSpec) -> None:
        """Load a rubric for scoring."""
        self._rubrics[rubric.id] = rubric

    def load_benchmark(self, benchmark: BenchmarkSpec) -> None:
        """Load a benchmark for comparison."""
        self._benchmarks[benchmark.id] = benchmark
        self._context_selector.register(benchmark)

    def select_benchmarks(
        self,
        domain: Optional[str] = None,
        context_tags: Optional[List[str]] = None,
        metric_names: Optional[List[str]] = None,
    ) -> List[BenchmarkSpec]:
        """Select benchmarks based on context."""
        return self._context_selector.select(domain, context_tags, metric_names)

    def score(
        self,
        scenario_id: str,
        run_id: str,
        metrics: List[MetricValue],
        rubric_id: str,
        feasibility: float = 1.0,
        confidence: float = 1.0,
        constraint_violations: Optional[Dict[str, float]] = None,
        robustness_total: int = 0,
        robustness_failures: int = 0,
        domain: Optional[str] = None,
        context_tags: Optional[List[str]] = None,
        benchmark_ids: Optional[List[str]] = None,
    ) -> JudgeResult:
        """
        Compute deterministic score.

        This is pure math - no LLM involvement.

        Args:
            scenario_id: Scenario identifier
            run_id: Run identifier
            metrics: List of metric values
            rubric_id: Rubric to use for scoring
            feasibility: Feasibility factor (0-1)
            confidence: Confidence factor (0-1)
            constraint_violations: Constraint violations {name: magnitude}
            robustness_total: Total robustness tests run
            robustness_failures: Number of robustness failures
            domain: Domain for context-based benchmark selection
            context_tags: Tags for context-based benchmark selection
            benchmark_ids: Specific benchmark IDs (overrides context selection)

        Returns:
            JudgeResult with complete breakdown
        """
        rubric = self._rubrics.get(rubric_id)
        if rubric is None:
            raise ValueError(f"Rubric {rubric_id} not found")

        constraint_violations = constraint_violations or {}
        metric_map = {m.name: m for m in metrics}
        threshold_map = {t.metric_name: t for t in rubric.thresholds}

        # Step 1: Score each metric with thresholds
        breakdown = ScoreBreakdown()
        metric_breakdowns: List[MetricBreakdown] = []

        for metric_name, weight in rubric.metric_weights.items():
            if metric_name not in metric_map:
                continue

            metric = metric_map[metric_name]
            value = metric.value
            uncertainty = metric.uncertainty or 0.0

            # Threshold scoring
            if metric_name in threshold_map:
                threshold = threshold_map[metric_name]
                level, threshold_score = self._threshold_scorer.score_value(
                    value, threshold
                )
            else:
                # Default: normalize to 0-1 if no threshold
                threshold_score = min(1.0, max(0.0, value))
                level = ThresholdLevel.GOOD if threshold_score >= 0.7 else ThresholdLevel.ACCEPTABLE

            # Uncertainty penalty for this metric
            unc_penalty = 0.0
            if uncertainty > 0 and abs(value) > 1e-10:
                relative_unc = uncertainty / abs(value)
                unc_penalty = relative_unc * rubric.uncertainty_penalty_rate

            weighted_score = threshold_score * weight * (1 - unc_penalty)

            metric_breakdowns.append(
                MetricBreakdown(
                    name=metric_name,
                    raw_value=value,
                    threshold_level=level,
                    threshold_score=threshold_score,
                    weight=weight,
                    weighted_score=weighted_score,
                    uncertainty=uncertainty,
                    uncertainty_penalty=unc_penalty,
                )
            )

            # Legacy compatibility
            breakdown.metric_scores[metric_name] = value
            breakdown.metric_weights[metric_name] = weight
            breakdown.weighted_scores[metric_name] = weighted_score

        breakdown.metric_breakdowns = metric_breakdowns

        # Step 2: Aggregate based on method
        if not metric_breakdowns:
            breakdown.raw_aggregate = 0.0
        elif rubric.aggregation_method == "weighted_sum":
            total_weight = sum(m.weight for m in metric_breakdowns)
            if total_weight > 0:
                breakdown.raw_aggregate = (
                    sum(m.weighted_score for m in metric_breakdowns) / total_weight
                )
            else:
                breakdown.raw_aggregate = 0.0
        elif rubric.aggregation_method == "geometric_mean":
            scores = [m.threshold_score for m in metric_breakdowns]
            weights = [m.weight for m in metric_breakdowns]
            if scores and all(s > 0 for s in scores):
                log_sum = sum(w * math.log(s) for s, w in zip(scores, weights))
                total_weight = sum(weights)
                breakdown.raw_aggregate = math.exp(log_sum / total_weight)
            else:
                breakdown.raw_aggregate = 0.0
        elif rubric.aggregation_method == "min":
            if metric_breakdowns:
                breakdown.raw_aggregate = min(m.threshold_score for m in metric_breakdowns)
            else:
                breakdown.raw_aggregate = 0.0
        else:
            total_weight = sum(m.weight for m in metric_breakdowns)
            if total_weight > 0:
                breakdown.raw_aggregate = (
                    sum(m.weighted_score for m in metric_breakdowns) / total_weight
                )
            else:
                breakdown.raw_aggregate = 0.0

        # Step 3: Apply constraint penalties
        for constraint, magnitude in constraint_violations.items():
            if constraint in rubric.constraint_penalties:
                penalty = rubric.constraint_penalties[constraint] * magnitude
                breakdown.constraint_penalties[constraint] = penalty

        breakdown.total_constraint_penalty = sum(breakdown.constraint_penalties.values())

        # Step 4: Apply feasibility weight
        breakdown.feasibility_multiplier = feasibility * rubric.feasibility_weight

        # Step 5: Confidence penalty
        breakdown.confidence_penalty = (1 - confidence) * rubric.confidence_penalty_rate

        # Step 6: Uncertainty penalty (aggregate)
        breakdown.uncertainty_penalty = ConfidencePenaltyCalculator.from_uncertainty(
            metrics, rubric.uncertainty_penalty_rate
        )

        # Step 7: Robustness penalty
        breakdown.robustness_penalty = ConfidencePenaltyCalculator.from_robustness_failures(
            robustness_total, robustness_failures, rubric.robustness_penalty_rate
        )

        # Step 8: Total penalty
        breakdown.total_penalty = (
            breakdown.confidence_penalty
            + breakdown.uncertainty_penalty
            + breakdown.robustness_penalty
        )

        # Step 9: Compute final score
        score = breakdown.raw_aggregate
        score *= breakdown.feasibility_multiplier
        score *= (1 - breakdown.total_penalty)
        score -= breakdown.total_constraint_penalty

        breakdown.final_score = max(0.0, min(1.0, score))

        # Determine overall threshold level
        if breakdown.final_score >= THRESHOLD_SCORES[ThresholdLevel.EXCELLENT]:
            overall_level = ThresholdLevel.EXCELLENT
        elif breakdown.final_score >= THRESHOLD_SCORES[ThresholdLevel.VERY_GOOD]:
            overall_level = ThresholdLevel.VERY_GOOD
        elif breakdown.final_score >= THRESHOLD_SCORES[ThresholdLevel.GOOD]:
            overall_level = ThresholdLevel.GOOD
        elif breakdown.final_score >= THRESHOLD_SCORES[ThresholdLevel.ACCEPTABLE]:
            overall_level = ThresholdLevel.ACCEPTABLE
        else:
            overall_level = ThresholdLevel.UNACCEPTABLE

        # Step 10: Benchmark comparisons
        benchmark_comparisons = self._compare_benchmarks(
            metrics=metrics,
            domain=domain,
            context_tags=context_tags,
            benchmark_ids=benchmark_ids,
        )

        passed = sum(1 for c in benchmark_comparisons if c.passed)
        weighted_score = sum(c.weighted_pass for c in benchmark_comparisons)
        total_weight = sum(c.credibility_weight * c.recency_weight for c in benchmark_comparisons)

        return JudgeResult(
            scenario_id=scenario_id,
            run_id=run_id,
            rubric_id=rubric_id,
            rubric_version=rubric.version,
            breakdown=breakdown,
            score=breakdown.final_score,
            threshold_level=overall_level,
            benchmark_comparisons=benchmark_comparisons,
            benchmarks_passed=passed,
            benchmarks_total=len(benchmark_comparisons),
            benchmark_weighted_score=weighted_score / total_weight if total_weight > 0 else 0.0,
        )

    def _compare_benchmarks(
        self,
        metrics: List[MetricValue],
        domain: Optional[str] = None,
        context_tags: Optional[List[str]] = None,
        benchmark_ids: Optional[List[str]] = None,
    ) -> List[BenchmarkComparison]:
        """Compare metrics against benchmarks."""
        metric_map = {m.name: m for m in metrics}
        comparisons = []

        # Select benchmarks
        if benchmark_ids:
            benchmarks = [self._benchmarks[bid] for bid in benchmark_ids if bid in self._benchmarks]
        else:
            benchmarks = self.select_benchmarks(
                domain=domain,
                context_tags=context_tags,
                metric_names=list(metric_map.keys()),
            )

        for bench in benchmarks:
            if bench.metric_name not in metric_map:
                continue

            value = metric_map[bench.metric_name].value

            # Check threshold
            if bench.threshold_type == "min":
                passed = value >= bench.threshold_value
            elif bench.threshold_type == "max":
                passed = value <= bench.threshold_value
            else:  # target
                passed = abs(value - bench.threshold_value) < 0.1 * abs(bench.threshold_value)

            margin = value - bench.threshold_value
            if bench.threshold_type == "max":
                margin = -margin

            # Compute recency weight
            recency_weight = self._context_selector.compute_recency_weight(bench)

            # Weighted pass
            weighted_pass = (
                bench.credibility_weight * recency_weight if passed else 0.0
            )

            comparisons.append(
                BenchmarkComparison(
                    benchmark_id=bench.id,
                    benchmark_name=bench.name,
                    metric_name=bench.metric_name,
                    metric_value=value,
                    threshold_value=bench.threshold_value,
                    threshold_type=bench.threshold_type,
                    passed=passed,
                    margin=margin,
                    credibility_weight=bench.credibility_weight,
                    recency_weight=recency_weight,
                    weighted_pass=weighted_pass,
                )
            )

        return comparisons

    async def generate_explanation(
        self,
        result: JudgeResult,
        use_llm: bool = False,
    ) -> str:
        """
        Generate human-readable explanation.

        IMPORTANT: This does NOT affect the score.
        The score is already computed deterministically.
        This only explains the already-computed result.

        Args:
            result: The JudgeResult to explain
            use_llm: If True, use LLM to generate prose (optional)

        Returns:
            Explanation string
        """
        lines = [
            f"## Score: {result.score:.4f} ({result.threshold_level.value})",
            "",
            "### Metric Breakdown",
        ]

        for m in result.breakdown.metric_breakdowns:
            unc_str = ""
            if m.uncertainty_penalty > 0:
                unc_str = f", uncertainty penalty: -{m.uncertainty_penalty:.3f}"
            lines.append(
                f"- **{m.name}**: {m.raw_value:.4f} → "
                f"{m.threshold_level.value} ({m.threshold_score:.2f}) "
                f"× weight {m.weight:.2f} = {m.weighted_score:.4f}{unc_str}"
            )

        lines.append("")
        lines.append(f"**Raw Aggregate**: {result.breakdown.raw_aggregate:.4f}")

        if result.breakdown.constraint_penalties:
            lines.append("")
            lines.append("### Constraint Penalties")
            for constraint, penalty in result.breakdown.constraint_penalties.items():
                lines.append(f"- {constraint}: -{penalty:.4f}")
            lines.append(f"**Total Constraint Penalty**: -{result.breakdown.total_constraint_penalty:.4f}")

        lines.append("")
        lines.append("### Adjustments")
        lines.append(f"- Feasibility Multiplier: ×{result.breakdown.feasibility_multiplier:.2f}")
        lines.append(f"- Confidence Penalty: -{result.breakdown.confidence_penalty:.4f}")
        lines.append(f"- Uncertainty Penalty: -{result.breakdown.uncertainty_penalty:.4f}")
        lines.append(f"- Robustness Penalty: -{result.breakdown.robustness_penalty:.4f}")
        lines.append(f"- **Total Penalty**: -{result.breakdown.total_penalty:.4f}")

        if result.benchmark_comparisons:
            lines.append("")
            lines.append(f"### Benchmarks: {result.benchmarks_passed}/{result.benchmarks_total} passed")
            lines.append(f"Weighted Score: {result.benchmark_weighted_score:.4f}")
            lines.append("")

            for comp in result.benchmark_comparisons:
                status = "✓ PASS" if comp.passed else "✗ FAIL"
                weight_info = f"(cred: {comp.credibility_weight:.2f}, rec: {comp.recency_weight:.2f})"
                lines.append(
                    f"- {comp.benchmark_name}: {status} "
                    f"(value: {comp.metric_value:.4f} vs threshold: {comp.threshold_value:.4f}, "
                    f"margin: {comp.margin:+.4f}) {weight_info}"
                )

        lines.append("")
        lines.append("---")
        lines.append(
            f"*Computed at {result.computed_at.isoformat()} using rubric {result.rubric_id} v{result.rubric_version}*"
        )

        explanation = "\n".join(lines)

        if use_llm:
            # Optional: Use LLM to generate prose explanation
            # This ONLY describes the math decisions - cannot change scores
            explanation = await self._generate_llm_explanation(result, explanation)

        return explanation

    async def _generate_llm_explanation(
        self,
        result: JudgeResult,
        math_summary: str,
    ) -> str:
        """
        Use LLM to generate prose explanation of scoring.

        CRITICAL: The LLM can ONLY describe the math decisions.
        It CANNOT change any scores or make new judgments.
        """
        # Placeholder for actual LLM call
        # In production, this would call the LLM API

        prompt = f"""You are explaining a deterministic scoring result.
You may ONLY describe the mathematical decisions that were already made.
You CANNOT change any scores or make new judgments.

The scoring math is:
{math_summary}

Final score: {result.score:.4f}
Level: {result.threshold_level.value}

Write a 2-3 sentence natural language summary of why this score was assigned,
referencing the specific metrics and penalties that contributed most."""

        # For now, return the math summary with a header
        return f"**Explanation**\n\n{math_summary}"


# Global scorer instance
scorer = DeterministicScorer()
