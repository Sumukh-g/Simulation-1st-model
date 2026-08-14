"""
Tests for the optimiser's own validation harness.

Two things are being checked here, and they are different:

  1. The measuring instruments are correct — the problems evaluate to their
     published definitions, and hypervolume/IGD compute what they claim. If
     these are wrong, every convergence claim downstream is meaningless.
  2. The engine actually converges on a problem with a known answer, and does
     so reproducibly.
"""

import math

import numpy as np
import pytest

from services.optimizer import create_backend, list_backends
from services.optimizer.benchmarks import (
    BenchmarkConfig,
    generational_distance,
    get_problem,
    hypervolume,
    inverted_generational_distance,
    list_problems,
    non_dominated,
    run_benchmark,
)

# Small enough to run in seconds, large enough that the search has to work.
SMOKE_VARIABLES = 5
SMOKE_BUDGET = 200
SMOKE_BATCH = 20


class TestProblemSuite:
    """The benchmark problems match their published definitions."""

    def test_all_problems_are_constructible(self):
        names = list_problems()
        assert {"zdt1", "zdt2", "zdt3", "zdt4", "zdt6"} <= set(names)
        assert {"dtlz1", "dtlz2", "dtlz3", "dtlz4"} <= set(names)

        for name in names:
            problem = get_problem(name)
            assert problem.n_variables >= problem.n_objectives
            assert len(problem.bounds) == problem.n_variables
            assert len(problem.variable_names) == problem.n_variables
            assert len(problem.reference_point) == problem.n_objectives

    def test_zdt5_is_excluded(self):
        # ZDT5 is binary-encoded; every backend here searches a continuous box.
        assert "zdt5" not in list_problems()
        with pytest.raises(KeyError):
            get_problem("zdt5")

    def test_zdt1_known_values(self):
        problem = get_problem("zdt1", n_variables=3)

        # x = 0 everywhere: f1 = 0, g = 1, so f2 = 1.
        assert problem.evaluate({"x1": 0.0, "x2": 0.0, "x3": 0.0}) == pytest.approx(
            {"f1": 0.0, "f2": 1.0}
        )

        # Any x1 with a zero tail sits exactly on the front: f2 = 1 - sqrt(f1).
        outcome = problem.evaluate({"x1": 0.25, "x2": 0.0, "x3": 0.0})
        assert outcome["f1"] == pytest.approx(0.25)
        assert outcome["f2"] == pytest.approx(0.5)

    def test_zdt2_known_values(self):
        problem = get_problem("zdt2", n_variables=3)
        outcome = problem.evaluate({"x1": 0.5, "x2": 0.0, "x3": 0.0})
        assert outcome["f1"] == pytest.approx(0.5)
        assert outcome["f2"] == pytest.approx(1.0 - 0.25)

    def test_dtlz1_front_lies_on_the_half_hyperplane(self):
        problem = get_problem("dtlz1", n_objectives=3)
        # Tail variables at 0.5 zero out g, putting the point on the true front,
        # where the objectives sum to 0.5.
        params = {name: 0.5 for name in problem.variable_names}
        values = problem.evaluate(params)
        assert sum(values.values()) == pytest.approx(0.5)

    def test_dtlz2_front_lies_on_the_unit_sphere(self):
        problem = get_problem("dtlz2", n_objectives=3)
        params = {name: 0.5 for name in problem.variable_names}
        values = np.array(list(problem.evaluate(params).values()))
        assert np.linalg.norm(values) == pytest.approx(1.0)

    def test_problems_are_resizable(self):
        small = get_problem("zdt1", n_variables=4)
        assert small.n_variables == 4

        many_objectives = get_problem("dtlz2", n_objectives=5)
        assert many_objectives.n_objectives == 5
        assert many_objectives.n_variables >= 5

        with pytest.raises(ValueError):
            get_problem("zdt1", n_objectives=3)  # ZDT is bi-objective by definition
        with pytest.raises(ValueError):
            get_problem("dtlz2", n_variables=1, n_objectives=3)

    def test_evaluation_is_deterministic(self):
        problem = get_problem("zdt3", n_variables=6)
        params = {name: 0.3 for name in problem.variable_names}
        assert problem.evaluate(params) == problem.evaluate(params)

    def test_analytic_fronts_are_non_dominated(self):
        for name in ("zdt1", "zdt2", "zdt6", "dtlz2"):
            front = get_problem(name).pareto_front(40)
            # Every sampled point should survive the domination filter.
            assert non_dominated(front).shape[0] == front.shape[0], name

    def test_clip_respects_bounds(self):
        problem = get_problem("zdt4", n_variables=3)
        clipped = problem.clip({"x1": 5.0, "x2": -99.0, "x3": 99.0})
        assert clipped["x1"] == 1.0
        assert clipped["x2"] == -5.0
        assert clipped["x3"] == 5.0


class TestMetrics:
    """Hypervolume and IGD compute what they claim."""

    def test_non_dominated_filters_dominated_points(self):
        points = [[1.0, 1.0], [2.0, 2.0], [0.5, 3.0]]
        front = non_dominated(points)
        assert sorted(front.tolist()) == [[0.5, 3.0], [1.0, 1.0]]

    def test_non_dominated_keeps_duplicates_once_only_when_distinct(self):
        # Identical points do not dominate each other, so both are kept.
        front = non_dominated([[1.0, 1.0], [1.0, 1.0]])
        assert front.shape == (2, 2)

    def test_non_dominated_handles_empty_input(self):
        assert non_dominated([]).shape[0] == 0

    def test_hypervolume_single_point_is_a_rectangle(self):
        volume, method = hypervolume([[1.0, 1.0]], reference_point=(2.0, 3.0))
        assert method == "exact_2d"
        assert volume == pytest.approx(1.0 * 2.0)

    def test_hypervolume_two_points_by_hand(self):
        # Reference (3, 3). Sweeping f1: (1,2) contributes (3-1)*(3-2) = 2,
        # then (2,1) contributes (3-2)*(2-1) = 1.
        volume, _ = hypervolume([[1.0, 2.0], [2.0, 1.0]], reference_point=(3.0, 3.0))
        assert volume == pytest.approx(3.0)

    def test_hypervolume_ignores_points_outside_the_reference_box(self):
        volume, method = hypervolume([[5.0, 5.0]], reference_point=(1.0, 1.0))
        assert method == "empty"
        assert volume == 0.0

    def test_hypervolume_rewards_a_better_front(self):
        reference = (1.1, 1.1)
        worse, _ = hypervolume([[0.8, 0.8]], reference)
        better, _ = hypervolume([[0.2, 0.2]], reference)
        assert better > worse

    def test_hypervolume_uses_monte_carlo_beyond_two_objectives(self):
        volume, method = hypervolume([[0.5, 0.5, 0.5]], reference_point=(1.0, 1.0, 1.0))
        assert method == "monte_carlo"
        # The exact answer is 0.5**3; the estimate should be close.
        assert volume == pytest.approx(0.125, abs=0.01)

    def test_monte_carlo_hypervolume_is_reproducible(self):
        points = [[0.4, 0.6, 0.5], [0.7, 0.2, 0.4]]
        first, _ = hypervolume(points, (1.0, 1.0, 1.0), seed=7)
        second, _ = hypervolume(points, (1.0, 1.0, 1.0), seed=7)
        assert first == second

    def test_igd_is_zero_on_the_true_front(self):
        front = get_problem("zdt1").pareto_front(50)
        assert inverted_generational_distance(front, front) == pytest.approx(0.0)

    def test_igd_punishes_partial_coverage(self):
        truth = get_problem("zdt1").pareto_front(50)
        one_corner = truth[:1]
        assert inverted_generational_distance(one_corner, truth) > 0.1

    def test_igd_and_gd_differ_on_coverage(self):
        truth = get_problem("zdt1").pareto_front(50)
        one_corner = truth[:1]
        # A single point sitting exactly on the front is accurate (GD ~ 0) but
        # covers almost none of it (IGD large). That asymmetry is the reason
        # both metrics are reported.
        assert generational_distance(one_corner, truth) == pytest.approx(0.0)
        assert inverted_generational_distance(one_corner, truth) > 0.1

    def test_igd_of_nothing_is_infinite(self):
        truth = get_problem("zdt1").pareto_front(10)
        assert math.isinf(inverted_generational_distance([], truth))


class TestBackendInterface:
    """Every backend satisfies one interface, so callers never name one."""

    def test_default_backends_are_registered(self):
        assert set(list_backends()) >= {"hybrid", "evolutionary", "bayesian"}

    def test_unknown_backend_is_rejected(self):
        with pytest.raises(KeyError):
            create_backend("no_such_backend", bounds={"x": (0.0, 1.0)}, objective_names=["f1"])

    def test_direction_list_must_match_objectives(self):
        with pytest.raises(ValueError):
            create_backend(
                "evolutionary",
                bounds={"x": (0.0, 1.0)},
                objective_names=["f1", "f2"],
                minimise=[True],
            )

    @pytest.mark.parametrize("name", ["evolutionary", "bayesian", "hybrid"])
    def test_backends_propose_within_bounds_and_accept_observations(self, name):
        problem = get_problem("zdt1", n_variables=3)
        backend = create_backend(
            name,
            bounds=problem.bounds,
            objective_names=problem.objective_names,
            minimise=[True, True],
            seed=1,
            batch_size=4,
            n_restarts=1,
            bayesian_n_restarts=1,
        )

        proposals = backend.propose(4)
        assert len(proposals) == 4
        for params in proposals:
            assert set(params) == set(problem.variable_names)
            for variable, value in params.items():
                low, high = problem.bounds[variable]
                assert low <= value <= high

        backend.observe([(params, problem.evaluate(params)) for params in proposals])
        assert backend.state()["backend"] == name


class TestConvergence:
    """The engine measurably converges on a problem with a known answer."""

    def test_evolutionary_backend_converges_on_zdt1(self):
        result = run_benchmark(
            BenchmarkConfig(
                problem="zdt1",
                backend="evolutionary",
                budget=SMOKE_BUDGET,
                batch_size=SMOKE_BATCH,
                seed=42,
                n_variables=SMOKE_VARIABLES,
            )
        )

        assert result.n_evaluations == SMOKE_BUDGET
        assert result.hypervolume_method == "exact_2d"
        # It found part of the front, and got closer to it over the run.
        assert result.hypervolume > result.initial_hypervolume
        assert result.igd < result.initial_igd
        assert len(result.front) > 1

    def test_hypervolume_never_decreases(self):
        # Hypervolume is computed over a cumulative archive, so a drop would
        # mean the archive or the metric is wrong, not that the search regressed.
        result = run_benchmark(
            BenchmarkConfig(
                problem="zdt1",
                backend="evolutionary",
                budget=SMOKE_BUDGET,
                batch_size=SMOKE_BATCH,
                seed=3,
                n_variables=SMOKE_VARIABLES,
            )
        )
        volumes = [record.hypervolume for record in result.history]
        assert volumes == sorted(volumes)

    def test_runs_are_reproducible_from_seed(self):
        config = BenchmarkConfig(
            problem="zdt1",
            backend="evolutionary",
            budget=60,
            batch_size=20,
            seed=123,
            n_variables=SMOKE_VARIABLES,
        )
        first = run_benchmark(config)
        second = run_benchmark(config)

        assert first.hypervolume == second.hypervolume
        assert first.igd == second.igd
        assert first.front == second.front

    def test_different_seeds_explore_differently(self):
        def front_for(seed: int):
            return run_benchmark(
                BenchmarkConfig(
                    problem="zdt1",
                    backend="evolutionary",
                    budget=60,
                    batch_size=20,
                    seed=seed,
                    n_variables=SMOKE_VARIABLES,
                )
            ).front

        assert front_for(1) != front_for(2)

    def test_bayesian_backend_converges_on_zdt1(self):
        result = run_benchmark(
            BenchmarkConfig(
                problem="zdt1",
                backend="bayesian",
                budget=60,
                batch_size=20,
                seed=42,
                n_variables=SMOKE_VARIABLES,
                backend_options={"n_restarts": 1},
            )
        )
        assert result.n_evaluations == 60
        assert result.igd <= result.initial_igd

    def test_hybrid_backend_runs_end_to_end(self):
        # The hybrid is the v1 engine. This asserts only that it runs and makes
        # progress: on multi-objective problems its Bayesian half optimises the
        # first objective alone, so at small budgets it does not beat either of
        # its own parts. See the note in services/optimizer/backends.py.
        result = run_benchmark(
            BenchmarkConfig(
                problem="zdt1",
                backend="hybrid",
                budget=60,
                batch_size=20,
                seed=42,
                n_variables=SMOKE_VARIABLES,
                backend_options={"bayesian_n_restarts": 1},
            )
        )
        assert result.n_evaluations == 60
        assert len(result.front) >= 1
        assert result.igd < result.initial_igd
        assert result.backend_state["backend"] == "hybrid"

    def test_three_objective_problem_runs(self):
        result = run_benchmark(
            BenchmarkConfig(
                problem="dtlz2",
                backend="evolutionary",
                budget=60,
                batch_size=20,
                seed=5,
                n_objectives=3,
            )
        )
        assert result.n_objectives == 3
        assert result.hypervolume_method in {"monte_carlo", "empty"}
        assert len(result.front) >= 1

    def test_result_serialises_for_the_ledger(self):
        result = run_benchmark(
            BenchmarkConfig(
                problem="zdt1",
                backend="evolutionary",
                budget=40,
                batch_size=20,
                seed=9,
                n_variables=SMOKE_VARIABLES,
            )
        )
        payload = result.to_dict()
        assert payload["problem"] == "zdt1"
        assert len(payload["history"]) == 2
        assert set(payload["history"][0]) == {
            "iteration",
            "evaluations",
            "hypervolume",
            "igd",
            "front_size",
        }


class TestConfigValidation:
    def test_budget_must_be_positive(self):
        with pytest.raises(ValueError):
            BenchmarkConfig(problem="zdt1", budget=0)

    def test_batch_size_must_be_positive(self):
        with pytest.raises(ValueError):
            BenchmarkConfig(problem="zdt1", batch_size=0)

    def test_budget_smaller_than_batch_is_respected(self):
        result = run_benchmark(
            BenchmarkConfig(
                problem="zdt1",
                backend="evolutionary",
                budget=7,
                batch_size=20,
                seed=1,
                n_variables=SMOKE_VARIABLES,
            )
        )
        assert result.n_evaluations == 7
