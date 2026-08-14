"""Tests for optimization algorithms."""
import numpy as np
from services.optimizer import (
    BayesianOptimizer,
    EvolutionaryOptimizer,
    MultiFidelityBandit,
    FidelityLevel,
    UnifiedOptimizer,
    OptimizerConfig,
    OptimizerStrategy,
    Objective,
    Constraint,
    ConstraintType,
    ConstraintHandler,
    StoppingConfig,
    StoppingRules,
    StopReason,
    bounds_constraint,
    metric_threshold_constraint,
)


class TestBayesianOptimizer:
    """Tests for Bayesian optimization."""

    def test_initialization(self):
        """Test optimizer initialization."""
        opt = BayesianOptimizer(
            bounds={"x": (0, 10), "y": (-5, 5)},
            maximize=True,
        )
        assert opt.n_params == 2

    def test_random_proposals_initially(self):
        """Test that proposals are random initially."""
        opt = BayesianOptimizer(
            bounds={"x": (0, 10), "y": (-5, 5)},
            random_state=42,
        )

        proposals = opt.propose(3)
        assert len(proposals) == 3

        for p in proposals:
            assert 0 <= p["x"] <= 10
            assert -5 <= p["y"] <= 5

    def test_observation(self):
        """Test recording observations."""
        opt = BayesianOptimizer(
            bounds={"x": (0, 10)},
            maximize=True,
        )

        opt.observe({"x": 5}, 0.5)
        opt.observe({"x": 7}, 0.8)

        assert len(opt.X_observed) == 2
        assert opt.best_score == 0.8
        assert opt.best_params == {"x": 7}

    def test_propose_after_observations(self):
        """Test proposals improve after observations."""
        opt = BayesianOptimizer(
            bounds={"x": (0, 10)},
            maximize=True,
            random_state=42,
        )

        # Add some observations
        for x in [1, 3, 5, 7, 9]:
            score = -(x - 6) ** 2 + 10  # Peak at x=6
            opt.observe({"x": x}, score)

        # Proposal should be near peak
        proposals = opt.propose(1)
        assert len(proposals) == 1
        # Should be somewhat close to 6
        assert 4 <= proposals[0]["x"] <= 8

    def test_finds_optimum_1d(self):
        """Test that Bayesian finds optimum in simple 1D case."""
        opt = BayesianOptimizer(
            bounds={"x": (0, 10)},
            maximize=True,
            random_state=42,
        )

        # Objective: peak at x=7
        def objective(x):
            return -((x - 7) ** 2) + 10

        # Run optimization
        for i in range(20):
            proposals = opt.propose(1)
            for p in proposals:
                score = objective(p["x"])
                opt.observe(p, score)

        # Best should be close to 7
        assert opt.best_params is not None
        assert abs(opt.best_params["x"] - 7) < 1.5


class TestEvolutionaryOptimizer:
    """Tests for evolutionary optimization."""

    def test_initialization(self):
        """Test optimizer initialization."""
        opt = EvolutionaryOptimizer(
            bounds={"x": (0, 10), "y": (-5, 5)},
            objectives=["obj1", "obj2"],
            population_size=20,
        )
        assert opt.n_params == 2
        assert opt.n_objectives == 2

    def test_population_initialization(self):
        """Test initial population generation."""
        opt = EvolutionaryOptimizer(
            bounds={"x": (0, 10)},
            objectives=["obj"],
            population_size=10,
        )

        pop = opt.initialize_population()
        assert len(pop) == 10

        for ind in pop:
            assert 0 <= ind["x"] <= 10

    def test_pareto_frontier(self):
        """Test Pareto frontier computation."""
        opt = EvolutionaryOptimizer(
            bounds={"x": (0, 10)},
            objectives=["obj1", "obj2"],
            population_size=10,
        )

        # Add some dominated and non-dominated points
        opt.observe({"x": 1}, {"obj1": 0.5, "obj2": 0.5})  # Dominated
        opt.observe({"x": 2}, {"obj1": 0.9, "obj2": 0.3})  # Pareto
        opt.observe({"x": 3}, {"obj1": 0.3, "obj2": 0.9})  # Pareto
        opt.observe({"x": 4}, {"obj1": 0.8, "obj2": 0.8})  # Pareto

        pareto = opt.get_pareto_frontier()
        assert len(pareto) == 3  # Three non-dominated points

    def test_evolution(self):
        """Test that evolution produces offspring."""
        opt = EvolutionaryOptimizer(
            bounds={"x": (0, 10), "y": (0, 10)},
            objectives=["obj"],
            population_size=10,
            random_state=42,
        )

        # Initialize and evaluate
        pop = opt.initialize_population()
        for ind in pop:
            opt.observe(ind, {"obj": ind["x"] + ind["y"]})

        # Evolve
        offspring = opt.evolve()
        assert len(offspring) > 0

        for ind in offspring:
            assert 0 <= ind["x"] <= 10
            assert 0 <= ind["y"] <= 10


class TestMultiFidelityBandit:
    """Tests for multi-fidelity bandit."""

    def test_initialization(self):
        """Test bandit initialization."""
        bandit = MultiFidelityBandit(budget=1000)
        assert bandit.remaining_budget == 1000

    def test_fidelity_selection(self):
        """Test fidelity selection."""
        bandit = MultiFidelityBandit(budget=1000, random_state=42)

        fidelity = bandit.select_fidelity(100)
        assert fidelity in [FidelityLevel.CHEAP, FidelityLevel.MID, FidelityLevel.HIGH]

    def test_force_high_fidelity(self):
        """Test forcing high fidelity."""
        bandit = MultiFidelityBandit(budget=1000)

        fidelity = bandit.select_fidelity(100, force_high=True)
        assert fidelity == FidelityLevel.HIGH

    def test_budget_update(self):
        """Test budget is updated on observation."""
        bandit = MultiFidelityBandit(budget=1000)

        bandit.update(FidelityLevel.CHEAP, 0.5)
        assert bandit.remaining_budget == 999  # Cost of CHEAP is 1

        bandit.update(FidelityLevel.HIGH, 0.8)
        assert bandit.remaining_budget == 974  # Cost of HIGH is 25

    def test_promotion_decision(self):
        """Test promotion decision."""
        bandit = MultiFidelityBandit(budget=1000)

        # Without data, should promote
        assert bandit.should_promote(FidelityLevel.CHEAP, 0.9)

        # High fidelity should never promote
        assert not bandit.should_promote(FidelityLevel.HIGH, 0.9)


class TestConstraintHandler:
    """Tests for constraint handling."""

    def test_hard_constraint_filter(self):
        """Test hard constraints filter candidates."""
        handler = ConstraintHandler(
            [
                Constraint(
                    name="x_positive",
                    type=ConstraintType.HARD,
                    check_fn=lambda p, o: p.get("x", 0) > 0,
                )
            ]
        )

        candidates = [{"x": 5}, {"x": -1}, {"x": 0}, {"x": 10}]
        feasible = handler.filter_feasible(candidates)

        assert len(feasible) == 2
        assert {"x": 5} in feasible
        assert {"x": 10} in feasible

    def test_soft_constraint_penalty(self):
        """Test soft constraints add penalties."""
        handler = ConstraintHandler(
            [
                Constraint(
                    name="prefer_low_x",
                    type=ConstraintType.SOFT,
                    check_fn=lambda p, o: p.get("x", 0) < 5,
                    penalty_fn=lambda p, o: p.get("x", 0) - 5,
                    penalty_weight=0.1,
                )
            ]
        )

        params = {"x": 8}
        objectives = {"score": 10.0}

        penalized = handler.apply_penalties(params, objectives)
        assert penalized["score"] < 10.0  # Penalty applied

    def test_bounds_constraint(self):
        """Test bounds constraint helper."""
        constraint = bounds_constraint("x", lower=0, upper=10)

        # Satisfied
        satisfied, penalty = constraint.evaluate({"x": 5}, {})
        assert penalty == 0

        # Violated
        satisfied, penalty = constraint.evaluate({"x": 15}, {})
        assert not satisfied
        assert penalty > 0

    def test_metric_threshold_constraint(self):
        """Test metric threshold constraint."""
        constraint = metric_threshold_constraint("accuracy", min_value=0.8, hard=True)

        # Satisfied
        satisfied, _ = constraint.evaluate({}, {"metrics": {"accuracy": 0.9}})
        assert satisfied

        # Violated
        satisfied, _ = constraint.evaluate({}, {"metrics": {"accuracy": 0.5}})
        assert not satisfied


class TestStoppingRules:
    """Tests for stopping rules."""

    def test_plateau_detection(self):
        """Test plateau stopping."""
        rules = StoppingRules(
            StoppingConfig(
                plateau_window=5,
                plateau_threshold=0.01,
                min_iterations=1,
            )
        )

        # Add flat scores
        for _ in range(10):
            rules.update(best_score=0.5, evaluations_this_step=1)

        should_stop, reason = rules.check()
        assert should_stop
        assert reason == StopReason.PLATEAU

    def test_budget_exhaustion(self):
        """Test budget stopping."""
        rules = StoppingRules(
            StoppingConfig(
                max_budget=100,
                min_iterations=1,
            )
        )

        rules.update(budget_spent_this_step=150)
        should_stop, reason = rules.check()
        assert should_stop
        assert reason == StopReason.BUDGET_EXHAUSTED

    def test_max_iterations(self):
        """Test max iterations stopping."""
        rules = StoppingRules(
            StoppingConfig(
                max_iterations=5,
                min_iterations=1,
            )
        )

        for _ in range(6):
            rules.update()

        should_stop, reason = rules.check()
        assert should_stop
        assert reason == StopReason.MAX_ITERATIONS

    def test_confidence_threshold(self):
        """Test confidence threshold stopping."""
        rules = StoppingRules(
            StoppingConfig(
                confidence_threshold=0.9,
                min_iterations=1,
            )
        )

        rules.update(confidence=0.95)
        should_stop, reason = rules.check()
        assert should_stop
        assert reason == StopReason.CONFIDENCE_MET


class TestUnifiedOptimizer:
    """Tests for unified optimizer."""

    def test_initialization(self):
        """Test optimizer initialization."""
        config = OptimizerConfig(
            bounds={"x": (0, 10), "y": (-5, 5)},
            objectives=[Objective(name="score", maximize=True)],
        )
        opt = UnifiedOptimizer(config)
        assert opt.iteration == 0

    def test_propose_batch(self):
        """Test batch proposal."""
        config = OptimizerConfig(
            bounds={"x": (0, 10)},
            batch_size=5,
            random_state=42,
        )
        opt = UnifiedOptimizer(config)

        candidates = opt.propose_batch()
        assert len(candidates) == 5

        for c in candidates:
            assert 0 <= c.params["x"] <= 10

    def test_update(self):
        """Test update with results."""
        config = OptimizerConfig(
            bounds={"x": (0, 10)},
            objectives=[Objective(name="score", maximize=True)],
            random_state=42,
        )
        opt = UnifiedOptimizer(config)

        candidates = opt.propose_batch(3)
        results = [
            {
                "params": c.params,
                "outcome": {"metrics": {"score": c.params["x"]}},
                "fidelity": "cheap",
            }
            for c in candidates
        ]

        should_stop, _ = opt.update(results)
        assert opt.iteration == 1
        assert len(opt.candidates) == 3

    def test_get_best(self):
        """Test getting best candidate."""
        config = OptimizerConfig(
            bounds={"x": (0, 10)},
            objectives=[Objective(name="score", maximize=True)],
        )
        opt = UnifiedOptimizer(config)

        # Add some results
        results = [
            {"params": {"x": 3}, "outcome": {"metrics": {"score": 3}}},
            {"params": {"x": 7}, "outcome": {"metrics": {"score": 7}}},
            {"params": {"x": 5}, "outcome": {"metrics": {"score": 5}}},
        ]
        opt.update(results)

        best = opt.get_best()
        assert best is not None
        assert best.objectives["score"] == 7

    def test_explain_choice(self):
        """Test choice explanation."""
        config = OptimizerConfig(
            bounds={"x": (0, 10)},
            strategy=OptimizerStrategy.BAYESIAN,
            random_state=42,
        )
        opt = UnifiedOptimizer(config)

        candidates = opt.propose_batch(1)
        explanation = opt.explain_choice(candidates[0].id)

        assert "source" in explanation
        assert "reasoning" in explanation

    def test_constraint_respect(self):
        """Test that optimizer respects constraints."""
        config = OptimizerConfig(
            bounds={"x": (0, 10)},
            random_state=42,
        )

        constraints = [
            Constraint(
                name="x_above_5",
                type=ConstraintType.HARD,
                check_fn=lambda p, o: p.get("x", 0) > 5,
            )
        ]

        opt = UnifiedOptimizer(config, constraints)

        # All proposals should satisfy constraint
        for _ in range(5):
            candidates = opt.propose_batch(10)
            for c in candidates:
                assert c.params["x"] > 5


class TestToyPackOptimization:
    """Tests proving optimizer finds ToyPack optimum reliably."""

    def _toy_objective(self, x: float, y: float) -> float:
        """ToyPack-like objective: peak at (7, 3)."""
        return -((x - 7) ** 2) - ((y - 3) ** 2) + 50

    def test_finds_toypack_optimum_bayesian(self):
        """Test Bayesian finds ToyPack optimum."""
        config = OptimizerConfig(
            bounds={"x": (0, 10), "y": (0, 10)},
            objectives=[Objective(name="score", maximize=True)],
            strategy=OptimizerStrategy.BAYESIAN,
            batch_size=5,
            random_state=42,
        )

        stopping = StoppingConfig(
            max_iterations=20,
            min_iterations=5,
        )

        opt = UnifiedOptimizer(config, stopping_config=stopping)

        # Run optimization
        for _ in range(20):
            candidates = opt.propose_batch()
            results = []
            for c in candidates:
                score = self._toy_objective(c.params["x"], c.params["y"])
                results.append({
                    "params": c.params,
                    "outcome": {"metrics": {"score": score}},
                })
            should_stop, _ = opt.update(results)
            if should_stop:
                break

        best = opt.get_best()
        assert best is not None
        # Should be close to (7, 3)
        assert abs(best.params["x"] - 7) < 2.0
        assert abs(best.params["y"] - 3) < 2.0
        # Score should be high
        assert best.objectives["score"] > 40

    def test_finds_toypack_optimum_evolutionary(self):
        """Test evolutionary finds ToyPack optimum."""
        config = OptimizerConfig(
            bounds={"x": (0, 10), "y": (0, 10)},
            objectives=[Objective(name="score", maximize=True)],
            strategy=OptimizerStrategy.EVOLUTIONARY,
            population_size=20,
            batch_size=10,
            random_state=42,
        )

        stopping = StoppingConfig(
            max_iterations=30,
            min_iterations=5,
        )

        opt = UnifiedOptimizer(config, stopping_config=stopping)

        for _ in range(30):
            candidates = opt.propose_batch()
            results = []
            for c in candidates:
                score = self._toy_objective(c.params["x"], c.params["y"])
                results.append({
                    "params": c.params,
                    "outcome": {"metrics": {"score": score}},
                })
            should_stop, _ = opt.update(results)
            if should_stop:
                break

        best = opt.get_best()
        assert best is not None
        assert best.objectives["score"] > 35

    def test_finds_toypack_optimum_hybrid(self):
        """Test hybrid finds ToyPack optimum."""
        config = OptimizerConfig(
            bounds={"x": (0, 10), "y": (0, 10)},
            objectives=[Objective(name="score", maximize=True)],
            strategy=OptimizerStrategy.HYBRID,
            batch_size=10,
            random_state=42,
        )

        stopping = StoppingConfig(
            max_iterations=25,
            min_iterations=5,
        )

        opt = UnifiedOptimizer(config, stopping_config=stopping)

        for _ in range(25):
            candidates = opt.propose_batch()
            results = []
            for c in candidates:
                score = self._toy_objective(c.params["x"], c.params["y"])
                results.append({
                    "params": c.params,
                    "outcome": {"metrics": {"score": score}},
                })
            should_stop, _ = opt.update(results)
            if should_stop:
                break

        best = opt.get_best()
        assert best is not None
        assert best.objectives["score"] > 40

    def test_respects_constraints_while_optimizing(self):
        """Test optimizer respects constraints while finding optimum."""
        config = OptimizerConfig(
            bounds={"x": (0, 10), "y": (0, 10)},
            objectives=[Objective(name="score", maximize=True)],
            strategy=OptimizerStrategy.HYBRID,
            batch_size=10,
            random_state=42,
        )

        # Constraint: x must be > 5 (restricts optimum from (7,3) to valid region)
        constraints = [
            Constraint(
                name="x_min",
                type=ConstraintType.HARD,
                check_fn=lambda p, o: p.get("x", 0) >= 5,
            )
        ]

        stopping = StoppingConfig(max_iterations=20, min_iterations=5)
        opt = UnifiedOptimizer(config, constraints, stopping)

        all_candidates = []
        for _ in range(20):
            candidates = opt.propose_batch()
            all_candidates.extend(candidates)

            results = []
            for c in candidates:
                score = self._toy_objective(c.params["x"], c.params["y"])
                results.append({
                    "params": c.params,
                    "outcome": {"metrics": {"score": score}},
                })
            should_stop, _ = opt.update(results)
            if should_stop:
                break

        # All proposed candidates should satisfy constraint
        for c in all_candidates:
            assert c.params["x"] >= 5, f"Constraint violated: x={c.params['x']}"

        best = opt.get_best()
        assert best is not None
        # Best should be close to (7, 3) and satisfy constraint
        assert best.params["x"] >= 5
        assert best.objectives["score"] > 40


class TestMultiObjectiveOptimization:
    """Tests for multi-objective optimization."""

    def test_pareto_frontier_tracking(self):
        """Test Pareto frontier is tracked correctly."""
        config = OptimizerConfig(
            bounds={"x": (0, 10)},
            objectives=[
                Objective(name="impact", maximize=True),
                Objective(name="cost", maximize=False),
            ],
            strategy=OptimizerStrategy.EVOLUTIONARY,
            population_size=20,
            random_state=42,
        )

        opt = UnifiedOptimizer(config)

        # Simulate results with tradeoff
        results = []
        for x in np.linspace(0, 10, 20):
            results.append({
                "params": {"x": float(x)},
                "outcome": {
                    "metrics": {
                        "impact": x,  # Higher x = higher impact
                        "cost": x * 0.5,  # Higher x = higher cost
                    }
                },
            })

        opt.update(results)

        frontier = opt.get_frontier()
        assert len(frontier) > 0

        # Frontier should contain tradeoff points
        for point in frontier:
            assert point.candidate.objectives is not None
