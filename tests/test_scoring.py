"""Tests for Judge Service scoring."""
from datetime import datetime, timedelta, timezone

import pytest

from services.judge import (
    DeterministicScorer,
    MetricValue,
    RubricSpec,
    BenchmarkSpec,
    ThresholdSpec,
    ThresholdLevel,
    ContextSelector,
    ThresholdScorer,
    ConfidencePenaltyCalculator,
    THRESHOLD_SCORES,
)


class TestThresholdScorer:
    """Tests for threshold-based scoring."""

    def test_score_value_higher_is_better(self):
        """Test threshold scoring when higher values are better."""
        threshold = ThresholdSpec(
            metric_name="impact",
            acceptable=0.3,
            good=0.5,
            very_good=0.7,
            excellent=0.9,
            direction="higher_is_better",
        )

        # Test each level
        level, score = ThresholdScorer.score_value(0.1, threshold)
        assert level == ThresholdLevel.UNACCEPTABLE
        assert score == 0.0

        level, score = ThresholdScorer.score_value(0.35, threshold)
        assert level == ThresholdLevel.ACCEPTABLE
        assert score == 0.5

        level, score = ThresholdScorer.score_value(0.55, threshold)
        assert level == ThresholdLevel.GOOD
        assert score == 0.7

        level, score = ThresholdScorer.score_value(0.75, threshold)
        assert level == ThresholdLevel.VERY_GOOD
        assert score == 0.85

        level, score = ThresholdScorer.score_value(0.95, threshold)
        assert level == ThresholdLevel.EXCELLENT
        assert score == 1.0

    def test_score_value_lower_is_better(self):
        """Test threshold scoring when lower values are better."""
        threshold = ThresholdSpec(
            metric_name="cost",
            acceptable=100000,
            good=50000,
            very_good=25000,
            excellent=10000,
            direction="lower_is_better",
        )

        # Test each level
        level, score = ThresholdScorer.score_value(150000, threshold)
        assert level == ThresholdLevel.UNACCEPTABLE

        level, score = ThresholdScorer.score_value(75000, threshold)
        assert level == ThresholdLevel.ACCEPTABLE

        level, score = ThresholdScorer.score_value(35000, threshold)
        assert level == ThresholdLevel.GOOD

        level, score = ThresholdScorer.score_value(15000, threshold)
        assert level == ThresholdLevel.VERY_GOOD

        level, score = ThresholdScorer.score_value(5000, threshold)
        assert level == ThresholdLevel.EXCELLENT

    def test_interpolate_score(self):
        """Test score interpolation between thresholds."""
        threshold = ThresholdSpec(
            metric_name="impact",
            acceptable=0.0,
            good=0.5,
            very_good=0.75,
            excellent=1.0,
        )

        # Below acceptable should be near 0
        score = ThresholdScorer.interpolate_score(-0.5, threshold)
        assert score < 0.5

        # At acceptable
        score = ThresholdScorer.interpolate_score(0.0, threshold)
        assert abs(score - 0.5) < 0.1

        # Between good and very_good
        score = ThresholdScorer.interpolate_score(0.625, threshold)
        assert 0.7 < score < 0.85

        # At excellent
        score = ThresholdScorer.interpolate_score(1.0, threshold)
        assert score == 1.0


class TestContextSelector:
    """Tests for context-based benchmark selection."""

    def setup_method(self):
        """Set up test benchmarks."""
        self.selector = ContextSelector()

        self.selector.register(
            BenchmarkSpec(
                id="finance-roi",
                name="Finance ROI",
                metric_name="roi",
                threshold_value=0.05,
                domain="finance",
                context_tags=["investment", "quarterly"],
            )
        )
        self.selector.register(
            BenchmarkSpec(
                id="finance-risk",
                name="Finance Risk",
                metric_name="risk",
                threshold_value=0.3,
                threshold_type="max",
                domain="finance",
                context_tags=["investment", "risk"],
            )
        )
        self.selector.register(
            BenchmarkSpec(
                id="spatial-coverage",
                name="Spatial Coverage",
                metric_name="coverage",
                threshold_value=0.8,
                domain="spatial",
                context_tags=["urban", "planning"],
            )
        )

    def test_select_by_domain(self):
        """Test selection by domain."""
        selected = self.selector.select(domain="finance")
        assert len(selected) == 2

        selected = self.selector.select(domain="spatial")
        assert len(selected) == 1
        assert selected[0].id == "spatial-coverage"

    def test_select_by_context_tags(self):
        """Test selection by context tags."""
        selected = self.selector.select(context_tags=["investment"])
        assert len(selected) == 2

        selected = self.selector.select(context_tags=["urban"])
        assert len(selected) == 1

        selected = self.selector.select(context_tags=["nonexistent"])
        assert len(selected) == 0

    def test_select_by_metric_names(self):
        """Test selection by metric names."""
        selected = self.selector.select(metric_names=["roi"])
        assert len(selected) == 1
        assert selected[0].id == "finance-roi"

        selected = self.selector.select(metric_names=["roi", "risk"])
        assert len(selected) == 2

    def test_combined_selection(self):
        """Test combined domain + tags selection."""
        selected = self.selector.select(domain="finance", context_tags=["risk"])
        assert len(selected) == 1
        assert selected[0].id == "finance-risk"

    def test_recency_weight(self):
        """Test recency weighting."""
        # Recent benchmark
        recent = BenchmarkSpec(
            id="recent",
            name="Recent",
            metric_name="x",
            threshold_value=0.5,
            recency_date=datetime.now(timezone.utc),
        )
        weight = self.selector.compute_recency_weight(recent)
        assert weight > 0.9

        # Old benchmark
        old = BenchmarkSpec(
            id="old",
            name="Old",
            metric_name="x",
            threshold_value=0.5,
            recency_date=datetime.now(timezone.utc) - timedelta(days=730),  # 2 years
        )
        weight = self.selector.compute_recency_weight(old)
        assert weight < 0.5

        # No recency date
        no_date = BenchmarkSpec(
            id="nodate",
            name="No Date",
            metric_name="x",
            threshold_value=0.5,
        )
        weight = self.selector.compute_recency_weight(no_date)
        assert weight == 1.0


class TestConfidencePenaltyCalculator:
    """Tests for confidence penalty calculations."""

    def test_uncertainty_penalty(self):
        """Test penalty from uncertainty width."""
        metrics = [
            MetricValue(name="a", value=100, uncertainty=10),  # 10% uncertainty
            MetricValue(name="b", value=50, uncertainty=5),  # 10% uncertainty
        ]

        penalty = ConfidencePenaltyCalculator.from_uncertainty(metrics, penalty_rate=0.1)
        assert penalty > 0
        assert penalty < 0.05  # Should be roughly 0.1 * 0.1 = 0.01

    def test_no_uncertainty(self):
        """Test no penalty when no uncertainty."""
        metrics = [
            MetricValue(name="a", value=100),
            MetricValue(name="b", value=50),
        ]

        penalty = ConfidencePenaltyCalculator.from_uncertainty(metrics, penalty_rate=0.1)
        assert penalty == 0.0

    def test_robustness_penalty(self):
        """Test penalty from robustness failures."""
        # 30% failure rate
        penalty = ConfidencePenaltyCalculator.from_robustness_failures(
            total_tests=10, failures=3, penalty_rate=0.1
        )
        assert abs(penalty - 0.03) < 0.001

        # No failures
        penalty = ConfidencePenaltyCalculator.from_robustness_failures(
            total_tests=10, failures=0, penalty_rate=0.1
        )
        assert penalty == 0.0

        # No tests
        penalty = ConfidencePenaltyCalculator.from_robustness_failures(
            total_tests=0, failures=0, penalty_rate=0.1
        )
        assert penalty == 0.0


class TestDeterministicScorer:
    """Tests for the main scoring engine."""

    def setup_method(self):
        """Set up scorer with rubric and benchmarks."""
        self.scorer = DeterministicScorer()

        # Load rubric
        self.scorer.load_rubric(
            RubricSpec(
                id="test-rubric",
                name="Test Rubric",
                metric_weights={
                    "impact": 0.4,
                    "cost": 0.3,
                    "feasibility": 0.3,
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
                    ThresholdSpec(
                        metric_name="feasibility",
                        acceptable=0.5,
                        good=0.7,
                        very_good=0.85,
                        excellent=0.95,
                    ),
                ],
                constraint_penalties={"budget_exceeded": 0.1},
                confidence_penalty_rate=0.1,
                uncertainty_penalty_rate=0.05,
                robustness_penalty_rate=0.1,
            )
        )

        # Load benchmarks
        self.scorer.load_benchmark(
            BenchmarkSpec(
                id="min-impact",
                name="Minimum Impact",
                metric_name="impact",
                threshold_value=0.5,
                threshold_type="min",
                credibility_weight=0.9,
            )
        )

    def test_basic_scoring(self):
        """Test basic score computation."""
        result = self.scorer.score(
            scenario_id="s-001",
            run_id="r-001",
            metrics=[
                MetricValue(name="impact", value=0.75),
                MetricValue(name="cost", value=30000),
                MetricValue(name="feasibility", value=0.9),
            ],
            rubric_id="test-rubric",
        )

        assert result.scenario_id == "s-001"
        assert result.rubric_id == "test-rubric"
        assert 0 <= result.score <= 1
        assert result.threshold_level in ThresholdLevel

    def test_threshold_level_assignment(self):
        """Test correct threshold level assignment."""
        # High scores should get EXCELLENT or VERY_GOOD
        result = self.scorer.score(
            scenario_id="s-001",
            run_id="r-001",
            metrics=[
                MetricValue(name="impact", value=0.95),
                MetricValue(name="cost", value=8000),
                MetricValue(name="feasibility", value=0.98),
            ],
            rubric_id="test-rubric",
        )

        assert result.score > 0.85
        assert result.threshold_level in [ThresholdLevel.EXCELLENT, ThresholdLevel.VERY_GOOD]

    def test_constraint_penalties(self):
        """Test constraint penalty application."""
        result_no_violation = self.scorer.score(
            scenario_id="s-001",
            run_id="r-001",
            metrics=[MetricValue(name="impact", value=0.8)],
            rubric_id="test-rubric",
        )

        result_with_violation = self.scorer.score(
            scenario_id="s-002",
            run_id="r-001",
            metrics=[MetricValue(name="impact", value=0.8)],
            rubric_id="test-rubric",
            constraint_violations={"budget_exceeded": 1.0},
        )

        assert result_with_violation.score < result_no_violation.score
        assert result_with_violation.breakdown.total_constraint_penalty > 0

    def test_confidence_penalty(self):
        """Test confidence penalty application."""
        result_high_conf = self.scorer.score(
            scenario_id="s-001",
            run_id="r-001",
            metrics=[MetricValue(name="impact", value=0.8)],
            rubric_id="test-rubric",
            confidence=1.0,
        )

        result_low_conf = self.scorer.score(
            scenario_id="s-002",
            run_id="r-001",
            metrics=[MetricValue(name="impact", value=0.8)],
            rubric_id="test-rubric",
            confidence=0.5,
        )

        assert result_low_conf.score < result_high_conf.score
        assert result_low_conf.breakdown.confidence_penalty > result_high_conf.breakdown.confidence_penalty

    def test_uncertainty_penalty(self):
        """Test uncertainty penalty application."""
        result_certain = self.scorer.score(
            scenario_id="s-001",
            run_id="r-001",
            metrics=[MetricValue(name="impact", value=0.8)],
            rubric_id="test-rubric",
        )

        result_uncertain = self.scorer.score(
            scenario_id="s-002",
            run_id="r-001",
            metrics=[MetricValue(name="impact", value=0.8, uncertainty=0.2)],
            rubric_id="test-rubric",
        )

        assert result_uncertain.score < result_certain.score
        assert result_uncertain.breakdown.uncertainty_penalty > 0

    def test_robustness_penalty(self):
        """Test robustness penalty application."""
        result_robust = self.scorer.score(
            scenario_id="s-001",
            run_id="r-001",
            metrics=[MetricValue(name="impact", value=0.8)],
            rubric_id="test-rubric",
            robustness_total=10,
            robustness_failures=0,
        )

        result_fragile = self.scorer.score(
            scenario_id="s-002",
            run_id="r-001",
            metrics=[MetricValue(name="impact", value=0.8)],
            rubric_id="test-rubric",
            robustness_total=10,
            robustness_failures=5,
        )

        assert result_fragile.score < result_robust.score
        assert result_fragile.breakdown.robustness_penalty > result_robust.breakdown.robustness_penalty

    def test_feasibility_multiplier(self):
        """Test feasibility multiplier effect."""
        result_feasible = self.scorer.score(
            scenario_id="s-001",
            run_id="r-001",
            metrics=[MetricValue(name="impact", value=0.8)],
            rubric_id="test-rubric",
            feasibility=1.0,
        )

        result_infeasible = self.scorer.score(
            scenario_id="s-002",
            run_id="r-001",
            metrics=[MetricValue(name="impact", value=0.8)],
            rubric_id="test-rubric",
            feasibility=0.5,
        )

        assert result_infeasible.score < result_feasible.score
        assert result_infeasible.breakdown.feasibility_multiplier < result_feasible.breakdown.feasibility_multiplier

    def test_benchmark_comparison(self):
        """Test benchmark comparison."""
        result_pass = self.scorer.score(
            scenario_id="s-001",
            run_id="r-001",
            metrics=[MetricValue(name="impact", value=0.7)],
            rubric_id="test-rubric",
        )

        assert result_pass.benchmarks_total == 1
        assert result_pass.benchmarks_passed == 1

        result_fail = self.scorer.score(
            scenario_id="s-002",
            run_id="r-001",
            metrics=[MetricValue(name="impact", value=0.3)],
            rubric_id="test-rubric",
        )

        assert result_fail.benchmarks_passed == 0

    def test_metric_breakdown(self):
        """Test per-metric breakdown in result."""
        result = self.scorer.score(
            scenario_id="s-001",
            run_id="r-001",
            metrics=[
                MetricValue(name="impact", value=0.75),
                MetricValue(name="cost", value=30000),
            ],
            rubric_id="test-rubric",
        )

        assert len(result.breakdown.metric_breakdowns) == 2

        impact_breakdown = next(
            m for m in result.breakdown.metric_breakdowns if m.name == "impact"
        )
        assert impact_breakdown.raw_value == 0.75
        assert impact_breakdown.threshold_level == ThresholdLevel.VERY_GOOD


class TestAggregationMethods:
    """Tests for different aggregation methods."""

    def test_weighted_sum(self):
        """Test weighted_sum aggregation."""
        scorer = DeterministicScorer()
        scorer.load_rubric(
            RubricSpec(
                id="weighted",
                name="Weighted",
                metric_weights={"a": 0.5, "b": 0.5},
                aggregation_method="weighted_sum",
            )
        )

        result = scorer.score(
            scenario_id="s-001",
            run_id="r-001",
            metrics=[
                MetricValue(name="a", value=0.8),
                MetricValue(name="b", value=0.6),
            ],
            rubric_id="weighted",
        )

        # Raw aggregate should be close to (0.8*0.5 + 0.6*0.5) / 1.0 = 0.7
        assert 0.6 < result.breakdown.raw_aggregate < 0.8

    def test_geometric_mean(self):
        """Test geometric_mean aggregation."""
        scorer = DeterministicScorer()
        scorer.load_rubric(
            RubricSpec(
                id="geometric",
                name="Geometric",
                metric_weights={"a": 1.0, "b": 1.0},
                aggregation_method="geometric_mean",
            )
        )

        result = scorer.score(
            scenario_id="s-001",
            run_id="r-001",
            metrics=[
                MetricValue(name="a", value=0.64),
                MetricValue(name="b", value=1.0),
            ],
            rubric_id="geometric",
        )

        # Geometric mean of 0.64 and 1.0 = 0.8
        assert 0.7 < result.breakdown.raw_aggregate < 0.9

    def test_min_aggregation(self):
        """Test min aggregation."""
        scorer = DeterministicScorer()
        scorer.load_rubric(
            RubricSpec(
                id="min-agg",
                name="Min",
                metric_weights={"a": 1.0, "b": 1.0},
                aggregation_method="min",
            )
        )

        result = scorer.score(
            scenario_id="s-001",
            run_id="r-001",
            metrics=[
                MetricValue(name="a", value=0.9),
                MetricValue(name="b", value=0.5),
            ],
            rubric_id="min-agg",
        )

        # Min should be threshold score of b (0.5)
        assert result.breakdown.raw_aggregate < 0.6


class TestExplanation:
    """Tests for explanation generation."""

    @pytest.mark.asyncio
    async def test_generate_explanation(self):
        """Test explanation generation."""
        scorer = DeterministicScorer()
        scorer.load_rubric(
            RubricSpec(
                id="test",
                name="Test",
                metric_weights={"impact": 1.0},
            )
        )

        result = scorer.score(
            scenario_id="s-001",
            run_id="r-001",
            metrics=[MetricValue(name="impact", value=0.8)],
            rubric_id="test",
        )

        explanation = await scorer.generate_explanation(result)

        assert "Score:" in explanation
        assert "impact" in explanation
        assert "0.8" in explanation

    @pytest.mark.asyncio
    async def test_explanation_includes_benchmarks(self):
        """Test that explanation includes benchmark info."""
        scorer = DeterministicScorer()
        scorer.load_rubric(
            RubricSpec(
                id="test",
                name="Test",
                metric_weights={"impact": 1.0},
            )
        )
        scorer.load_benchmark(
            BenchmarkSpec(
                id="bench",
                name="Min Impact",
                metric_name="impact",
                threshold_value=0.5,
            )
        )

        result = scorer.score(
            scenario_id="s-001",
            run_id="r-001",
            metrics=[MetricValue(name="impact", value=0.8)],
            rubric_id="test",
        )

        explanation = await scorer.generate_explanation(result)

        assert "Benchmarks" in explanation
        assert "PASS" in explanation
