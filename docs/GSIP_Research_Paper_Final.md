# GSIP: General Simulation Intelligence Platform

## A System for Question-Driven Simulation, Optimization, and Decision Support

---

# Abstract

Decision-making in complex domains requires simulation, optimization, and expert judgment—but traditional systems require users to manually define objective functions, constraints, and parameters. Meanwhile, modern AI chatbots can accept natural language but often fabricate numerical results.

We present GSIP (General Simulation Intelligence Platform), a system that bridges this gap. GSIP accepts a natural language question like "Maximize my portfolio returns while keeping risk low" and automatically:

1. Transforms the question into structured optimization objectives (metrics, direction, constraints)
2. Generates 50+ diverse scenarios covering the parameter space
3. Runs actual simulations using pluggable domain packs
4. Scores and ranks outcomes using deterministic rubrics
5. Optimizes iteratively using Bayesian optimization
6. Produces a final ranked report with full audit trail

The key innovation is the **Non-Negotiable Truth Architecture**: AI assists with problem formulation and explanation, but all numerical results come exclusively from simulation code and are immediately stored in an immutable ledger. This ensures that users can trust the numbers they see.

We demonstrate GSIP across three domains: portfolio optimization (FinancePack), spatial diffusion modeling (SpatialPack), and a testing harness (ToyPack). The system processes 50+ scenarios per run, achieves reproducibility through deterministic seeding, and maintains complete provenance for regulatory compliance.

---

# 1. Introduction

## 1.1 The Problem

Consider a financial analyst asking: *"What asset allocation maximizes risk-adjusted returns over 3 years?"*

To answer this question computationally, they currently need to:
- Define an objective function (e.g., maximize Sharpe ratio)
- Specify parameter ranges (e.g., stock weight 0-100%, bond weight 0-100%)
- Set up a backtest simulation
- Run multiple scenarios
- Analyze and compare results
- Document their methodology

This requires significant technical expertise and time.

Alternatively, they could ask a ChatGPT-style AI assistant. The AI would respond fluently, but might fabricate statistics like "Based on historical analysis, a 60/30/10 allocation achieves a 1.8 Sharpe ratio" without actually running any simulation. The numbers are plausible but invented.

**GSIP solves both problems**: it accepts natural language questions AND runs real simulations, ensuring that every number shown to the user was actually computed.

## 1.2 Our Solution

GSIP is an end-to-end platform that:

1. **Understands Intent**: Parses natural language questions to extract optimization objectives, constraints, and relevant metrics

2. **Generates Scenarios**: Creates diverse parameter combinations using grid sampling, Latin Hypercube, and random exploration

3. **Runs Real Simulations**: Executes actual computation using pluggable domain packs (not AI-generated fake numbers)

4. **Scores Deterministically**: Ranks results using versioned rubrics and benchmark comparisons

5. **Optimizes Iteratively**: Uses Bayesian optimization to find better solutions

6. **Maintains Full Audit Trail**: Every result is stored with its computation provenance

## 1.3 Key Contribution: The Non-Negotiable Truth Architecture

The central design principle of GSIP is:

> **LLMs and AI agents may propose objectives, scenarios, and explanations, but they must NEVER fabricate simulation results.**

This is enforced architecturally:
- Only domain pack `simulate()` methods produce numerical outcomes
- Results are immediately persisted to the database before returning
- Every result includes a deterministic hash for verification
- The run ledger maintains complete computation provenance

---

# 2. System Architecture

## 2.1 Overview

GSIP consists of six services communicating through APIs and message queues:

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Question                              │
│           "Maximize returns while keeping risk low"              │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    API Gateway (FastAPI)                          │
│                    POST /api/runs/start                           │
│   - Authentication                                                │
│   - Creates Run record in PostgreSQL                              │
│   - Starts Temporal workflow                                      │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│               Orchestrator (Temporal Workflow)                    │
│                                                                   │
│   Step 1: Formalize Objectives                                    │
│   Step 2: Build Evidence Pack                                     │
│   Step 3: Generate Scenarios (50+ minimum)                        │
│   Step 4: Execute Simulations (Ray workers)                       │
│   Step 5: Score & Rank (Judge service)                            │
│   Step 6: Optimization Loop (Bayesian/Evolutionary)               │
│   Step 7: Promote Finalists (higher fidelity)                     │
│   Step 8: Robustness Tests                                        │
│   Step 9: Assemble Final Report                                   │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Storage Layer                                │
│                                                                   │
│   PostgreSQL: Run ledger, scenarios, metrics, scores              │
│   MinIO: Large artifacts (trajectories, heatmaps)                 │
│   Redis: Result caching                                           │
│   Milvus: Document embeddings (Evidence service)                  │
└─────────────────────────────────────────────────────────────────┘
```

## 2.2 Component Details

### API Gateway (`services/api/`)

The FastAPI-based gateway handles:
- **Authentication**: JWT tokens with role-based access control
- **Run Management**: Start, monitor, and retrieve runs
- **SSE Streaming**: Real-time progress updates

```python
# Example: Starting a run
POST /api/runs/start
{
    "prompt": "Maximize portfolio returns while keeping risk low",
    "domain_pack": "finance-pack",
    "config": {
        "maxScenarios": 100,
        "maxWallTime": 3600
    }
}
```

### Orchestrator (`services/orchestrator/`)

Uses Temporal for durable workflow execution. The main workflow (`SimulationRunWorkflow`) coordinates the entire pipeline:

1. Calls `formalize_objectives` activity
2. Generates scenarios with `generate_structured_scenarios`
3. Executes simulations via `execute_simulation_batch`
4. Scores results using `judge_score_outcomes`
5. Runs optimization loop with `propose_next_batch` and `update_optimizer`
6. Promotes top candidates to higher fidelity
7. Assembles final report

### Sim Fabric (`services/sim_fabric/`)

Distributed simulation execution using Ray:
- Worker pool management
- Result caching (Redis)
- Artifact storage (MinIO)
- Invariant checking (bounds, NaN detection)

### Judge Service (`services/judge/`)

Deterministic scoring:
- Threshold-based metric scoring
- Weighted aggregation
- Benchmark comparisons
- Constraint penalty calculation

### Evidence Service (`services/evidence/`)

Document processing:
- PDF/DOCX ingestion
- Text chunking
- Embedding generation (sentence-transformers)
- Vector search (Milvus)

### Optimizer (`services/optimizer/`)

Optimization algorithms:
- Bayesian optimization with Gaussian Process surrogate
- NSGA-II evolutionary multi-objective optimization
- Thompson Sampling for multi-fidelity allocation

---

# 3. Methodology

## 3.1 Objective Formalization

The first challenge is transforming natural language into structured optimization objectives.

### 3.1.1 The Problem

Given input: `"Maximize my portfolio returns while keeping risk low"`

We need to extract:
- **Metrics**: What to measure (returns, risk metrics)
- **Direction**: Maximize or minimize
- **Constraints**: Hard limits to respect
- **Parameters**: What can be adjusted

### 3.1.2 Our Approach

We use a hybrid heuristic-LLM pipeline:

**Step 1: Domain Detection**

We maintain keyword vocabularies for each domain pack:

```python
DOMAIN_KEYWORDS = {
    "finance-pack": ["portfolio", "stock", "return", "sharpe", "volatility", "risk", ...],
    "spatial-pack": ["pollution", "diffusion", "grid", "heatmap", "emission", ...],
    "toy-pack": ["test", "demo", "distance", "target", ...]
}
```

The question is scored against each vocabulary, and the highest-scoring domain is selected:

```python
def detect_domain(question: str) -> str:
    question_lower = question.lower()
    scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in question_lower)
        scores[domain] = score
    return max(scores.items(), key=lambda x: x[1])[0]
```

**Step 2: Direction Detection**

We classify as minimization or maximization based on directional keywords:

```python
MINIMIZE_KEYWORDS = ["reduce", "minimize", "decrease", "lower", "less", "cut", ...]
MAXIMIZE_KEYWORDS = ["maximize", "increase", "improve", "boost", "grow", "best", ...]
```

**Step 3: Metric Selection**

Each domain has associated metrics:

```python
DOMAIN_METRICS = {
    "finance-pack": {
        "default": [
            {"name": "sharpe_ratio", "direction": "maximize", "weight": 1.0},
            {"name": "total_return", "direction": "maximize", "weight": 0.8},
            {"name": "max_drawdown", "direction": "minimize", "weight": 0.6}
        ]
    }
}
```

**Step 4: Constraint Extraction**

We identify constraints using pattern matching:

```python
# Example: "budget of $10,000"
budget_match = re.search(r'\$?(\d+(?:,\d{3})*)\s*(?:budget|cost)', question)
if budget_match:
    constraints.append({"name": "budget", "type": "max", "value": float(amount)})
```

**Step 5: LLM Enhancement (Optional)**

When available, we use GPT-4 to refine the extraction:

```python
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "Extract optimization objectives..."},
        {"role": "user", "content": f"Question: {question}"}
    ],
    response_format={"type": "json_object"}
)
```

### 3.1.3 Output: ObjectiveSpec

The formalization produces a structured specification:

```json
{
    "description": "Maximize my portfolio returns while keeping risk low",
    "metrics": [
        {"name": "sharpe_ratio", "direction": "maximize", "weight": 1.0},
        {"name": "total_return", "direction": "maximize", "weight": 0.8},
        {"name": "max_drawdown", "direction": "minimize", "weight": 0.6}
    ],
    "primary_direction": "maximize",
    "constraints": [
        {"name": "risk_level", "constraint_type": "max", "is_hard": false}
    ],
    "action_ranges": {
        "weight_spy": {"min": 0.0, "max": 1.0},
        "weight_bnd": {"min": 0.0, "max": 1.0},
        "weight_gld": {"min": 0.0, "max": 1.0},
        "weight_cash": {"min": 0.0, "max": 1.0}
    }
}
```

## 3.2 Scenario Generation

### 3.2.1 Requirements

1. Generate at least 50 scenarios per run
2. Achieve diverse coverage of the parameter space
3. Maintain deterministic reproducibility
4. Respect domain pack constraints

### 3.2.2 Multi-Strategy Approach

We combine four sampling strategies:

**Strategy 1: Grid Sampling (20% of budget)**

Systematic exploration at regular intervals:

```python
def _generate_grid_scenarios(action_ranges, count):
    n_dims = len(action_ranges)
    points_per_dim = int(count ** (1.0 / n_dims))
    
    grid_values = {}
    for param, bounds in action_ranges.items():
        grid_values[param] = [
            bounds["min"] + i * (bounds["max"] - bounds["min"]) / (points_per_dim - 1)
            for i in range(points_per_dim)
        ]
    
    return list(itertools.product(*grid_values.values()))
```

**Strategy 2: Latin Hypercube Sampling (30% of budget)**

Space-filling design that ensures each parameter range is sampled evenly:

```python
def _generate_lhs_scenarios(action_ranges, count, seed):
    rng = random.Random(seed)
    n_dims = len(action_ranges)
    
    samples = []
    for dim in range(n_dims):
        perm = list(range(count))
        rng.shuffle(perm)
        samples.append([
            (perm[i] + rng.random()) / count  # Stratified within each bin
            for i in range(count)
        ])
    
    # Scale to parameter ranges
    for i, (param, bounds) in enumerate(action_ranges.items()):
        samples[i] = [
            bounds["min"] + s * (bounds["max"] - bounds["min"])
            for s in samples[i]
        ]
    
    return zip(*samples)
```

**Strategy 3: Random Sampling (40% of budget)**

Uniform random exploration:

```python
def _generate_random_scenarios(action_ranges, count, seed):
    rng = random.Random(seed)
    scenarios = []
    for _ in range(count):
        actions = {
            param: rng.uniform(bounds["min"], bounds["max"])
            for param, bounds in action_ranges.items()
        }
        scenarios.append(actions)
    return scenarios
```

**Strategy 4: Boundary Scenarios (10% of budget)**

Extreme values for edge case testing:

```python
def _generate_boundary_scenarios(action_ranges, count):
    scenarios = []
    for i in range(count):
        actions = {}
        for param, bounds in action_ranges.items():
            choice = i % 3
            if choice == 0:
                actions[param] = bounds["min"]
            elif choice == 1:
                actions[param] = bounds["max"]
            else:
                actions[param] = (bounds["min"] + bounds["max"]) / 2
        scenarios.append(actions)
    return scenarios
```

### 3.2.3 Deterministic Hashing

Each scenario receives a SHA-256 hash for reproducibility:

```python
hash_data = {
    "run_id": run_id,
    "state": initial_state,
    "actions": actions,
    "seed": seed,
    "fidelity": fidelity
}
scenario_hash = hashlib.sha256(
    json.dumps(hash_data, sort_keys=True).encode()
).hexdigest()
```

This enables:
- Result caching: Identical scenarios return cached results
- Reproducibility verification: Same inputs → Same outputs
- Audit trail: Complete provenance for each result

## 3.3 Simulation Execution

### 3.3.1 Domain Pack Architecture

Each domain pack implements a standard interface:

```python
class DomainPackBase(ABC):
    name: str
    version: str
    
    @abstractmethod
    def state_schema(self) -> Type[BaseModel]:
        """Return Pydantic model for state validation."""
        pass
    
    @abstractmethod
    def action_schema(self) -> Type[BaseModel]:
        """Return Pydantic model for action validation."""
        pass
    
    @abstractmethod
    def simulate(
        self,
        state: BaseModel,
        actions: BaseModel,
        fidelity: Fidelity,
        seed: int,
        scenario_id: str,
        run_id: str
    ) -> OutcomeBundle:
        """Run the actual simulation."""
        pass
    
    @abstractmethod
    def score(
        self,
        outcome: OutcomeBundle,
        objectives: ObjectiveSpec
    ) -> MetricBundle:
        """Compute metrics from simulation outcome."""
        pass
```

### 3.3.2 Example: FinancePack

The FinancePack simulates portfolio backtesting:

**State Definition:**
```python
class FinanceState(BaseModel):
    initial_capital: float = 100000.0
    assets: List[str] = ["SPY", "BND", "GLD", "CASH"]
    expected_returns: Dict[str, float] = {"SPY": 0.10, "BND": 0.03, ...}
    volatilities: Dict[str, float] = {"SPY": 0.18, "BND": 0.05, ...}
    transaction_cost_bps: float = 10.0
```

**Action Definition:**
```python
class FinanceActions(BaseModel):
    weights: Dict[str, float] = {"SPY": 0.6, "BND": 0.3, "GLD": 0.1}
    rebalance_frequency: str = "monthly"
```

**Simulation Logic:**
```python
def simulate(self, state, actions, fidelity, seed, ...):
    # Generate synthetic returns
    rng = np.random.RandomState(seed)
    
    # Simulation granularity based on fidelity
    n_periods = {
        Fidelity.CHEAP: 36,   # Monthly for 3 years
        Fidelity.MID: 156,    # Weekly for 3 years
        Fidelity.HIGH: 756    # Daily for 3 years
    }[fidelity]
    
    # Generate returns for each asset
    returns = {}
    for asset in state.assets:
        mu = state.expected_returns[asset] / n_periods
        sigma = state.volatilities[asset] / sqrt(n_periods)
        returns[asset] = rng.normal(mu, sigma, n_periods)
    
    # Simulate portfolio evolution
    portfolio_value = state.initial_capital
    values = [portfolio_value]
    
    for t in range(n_periods):
        period_return = sum(
            actions.weights[asset] * returns[asset][t]
            for asset in state.assets
        )
        portfolio_value *= (1 + period_return)
        values.append(portfolio_value)
    
    return OutcomeBundle(
        final_state={"final_value": portfolio_value},
        trajectory=values,
        ...
    )
```

**Metric Computation:**
```python
def score(self, outcome, objectives):
    returns = outcome.raw_output["returns_array"]
    
    # Sharpe Ratio
    risk_free = 0.02 / 252
    excess_returns = returns - risk_free
    sharpe = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)
    
    # Maximum Drawdown
    cumulative = np.cumprod(1 + returns)
    rolling_max = np.maximum.accumulate(cumulative)
    drawdowns = (cumulative - rolling_max) / rolling_max
    max_drawdown = abs(np.min(drawdowns))
    
    return MetricBundle(
        metrics=[
            MetricValue(name="sharpe_ratio", value=sharpe),
            MetricValue(name="max_drawdown", value=max_drawdown),
            ...
        ]
    )
```

### 3.3.3 Multi-Fidelity Execution

Each domain pack supports three fidelity levels:

| Fidelity | Purpose | Typical Time | Use Case |
|----------|---------|--------------|----------|
| CHEAP | Quick approximation | 10-100ms | Initial exploration |
| MID | Standard precision | 100-500ms | Optimization iterations |
| HIGH | Full accuracy | 500ms-2s | Final ranking |

The optimizer uses cheap fidelity for exploration, then promotes top candidates to higher fidelity for accurate ranking.

## 3.4 Deterministic Scoring

### 3.4.1 The Scoring Pipeline

The Judge service computes scores using pure mathematical computation:

```
Raw Metrics → Threshold Scoring → Weighted Aggregation → Penalty Application → Final Score
```

### 3.4.2 Threshold-Based Metric Scoring

Each metric is scored against thresholds:

```python
THRESHOLD_SCORES = {
    "unacceptable": 0.0,
    "acceptable": 0.5,
    "good": 0.7,
    "very_good": 0.85,
    "excellent": 1.0
}

def score_value(value, threshold_spec):
    if threshold_spec.direction == "higher_is_better":
        if value >= threshold_spec.excellent:
            return 1.0
        elif value >= threshold_spec.very_good:
            return 0.85
        elif value >= threshold_spec.good:
            return 0.7
        elif value >= threshold_spec.acceptable:
            return 0.5
        else:
            return 0.0
```

### 3.4.3 Final Score Computation

```
final_score = raw_aggregate × feasibility_multiplier × (1 - total_penalty) - constraint_penalty
```

Where:
- `raw_aggregate` = weighted sum of metric scores
- `feasibility_multiplier` = 1.0 if feasible, 0.0 if infeasible
- `total_penalty` = confidence_penalty + uncertainty_penalty + robustness_penalty
- `constraint_penalty` = sum of constraint violation penalties

## 3.5 Bayesian Optimization

### 3.5.1 The Goal

Find the best parameter values by intelligently exploring the search space, using information from previous evaluations to guide exploration.

### 3.5.2 Gaussian Process Surrogate

We model the objective function as a Gaussian Process:

```python
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern, ConstantKernel

kernel = ConstantKernel(1.0) * Matern(length_scale=1.0, nu=2.5)
gp = GaussianProcessRegressor(kernel=kernel, normalize_y=True)
```

The GP provides:
- Mean prediction μ(x): Expected objective value
- Uncertainty σ(x): Confidence in the prediction

### 3.5.3 Expected Improvement Acquisition

We select the next point by maximizing Expected Improvement:

```python
def expected_improvement(x, gp, best_score):
    mu, sigma = gp.predict(x, return_std=True)
    
    improvement = mu - best_score
    z = improvement / sigma
    
    ei = improvement * norm.cdf(z) + sigma * norm.pdf(z)
    return ei
```

This balances:
- **Exploitation**: Points with high predicted value
- **Exploration**: Points with high uncertainty

### 3.5.4 Optimization Loop

```python
while not converged:
    # 1. Fit GP to observed data
    gp.fit(X_observed, y_observed)
    
    # 2. Find point that maximizes Expected Improvement
    x_next = optimize(expected_improvement, bounds)
    
    # 3. Evaluate the objective (run simulation)
    y_next = run_simulation(x_next)
    
    # 4. Update observations
    X_observed.append(x_next)
    y_observed.append(y_next)
    
    # 5. Check convergence
    if score_plateau_detected():
        converged = True
```

---

# 4. Implementation Details

## 4.1 The Run Ledger

All results are stored in PostgreSQL for audit compliance:

**runs table:**
- `id`: Unique run identifier
- `status`: pending | running | completed | failed
- `run_spec`: JSON configuration
- `created_at`, `completed_at`: Timestamps

**scenarios table:**
- `id`: Unique scenario identifier
- `run_id`: Parent run
- `scenario_hash`: SHA-256 for reproducibility
- `input_state`: JSON state
- `actions`: JSON actions
- `fidelity`: cheap | mid | high
- `seed`: Random seed

**metric_results table:**
- `scenario_instance_id`: Which execution
- `metric_name`: e.g., "sharpe_ratio"
- `metric_value`: The computed value
- `unit`: e.g., "USD", "%"

**judge_scores table:**
- `scenario_instance_id`: Which execution
- `rubric_version_id`: Which scoring rubric
- `score`: Final score (0-1)
- `breakdown`: JSON score decomposition

## 4.2 Caching

Results are cached in Redis using scenario hashes:

```python
cache_key = f"sim:{domain_pack}:{scenario_hash}"

# Check cache before simulation
if redis.exists(cache_key):
    return json.loads(redis.get(cache_key))

# Run simulation
result = domain_pack.simulate(...)

# Store in cache
redis.setex(cache_key, ttl=7*24*3600, value=json.dumps(result))
```

## 4.3 Distributed Execution

Ray handles parallel simulation:

```python
@ray.remote
class SimulationWorker:
    def __init__(self, domain_pack):
        self.pack = domain_pack
    
    def simulate(self, scenario):
        return self.pack.simulate(
            state=scenario["state"],
            actions=scenario["actions"],
            fidelity=scenario["fidelity"],
            seed=scenario["seed"],
            ...
        )

# Execute batch in parallel
workers = [SimulationWorker.remote(pack) for _ in range(n_workers)]
futures = [
    workers[i % n_workers].simulate.remote(scenarios[i])
    for i in range(len(scenarios))
]
results = ray.get(futures)
```

---

# 5. Domain Packs

## 5.1 ToyPack (Testing)

Simple 2D random walk toward a target:

**State:** Starting position (x, y), target position
**Actions:** Step direction (dx, dy), number of steps
**Metrics:** Final distance to target, efficiency, path length

Used for testing and validating the pipeline.

## 5.2 FinancePack (Portfolio Optimization)

Portfolio backtesting with synthetic returns:

**State:** Initial capital, asset universe, expected returns, volatilities
**Actions:** Asset weights, rebalance frequency
**Metrics:** Total return, Sharpe ratio, max drawdown, volatility, Sortino ratio

Fidelity affects granularity: monthly (cheap), weekly (mid), daily (high).

## 5.3 SpatialPack (Diffusion Modeling)

2D grid-based diffusion simulation:

**State:** Grid size, diffusion rate, decay rate, wind direction
**Actions:** Source locations, mitigation zones
**Metrics:** Coverage ratio, mean concentration, safe area ratio, threshold violations

Useful for pollution modeling, heat transfer, or epidemiological simulation.

---

# 6. The Non-Negotiable Truth Architecture

## 6.1 The Core Principle

The most important design principle in GSIP:

> **AI may assist with formulation and explanation, but all numerical results must come from simulation code and be immediately persisted.**

## 6.2 How It's Enforced

**Architectural Separation:**
- LLMs are used ONLY for:
  - Objective formalization (extracting intent from questions)
  - Explanation generation (describing already-computed results)
- LLMs are NEVER used for:
  - Producing metric values
  - Computing scores
  - Generating simulation outcomes

**Immediate Persistence:**
- Results are stored in the database BEFORE being returned
- This prevents any tampering or modification

**Deterministic Hashing:**
- Every scenario has a SHA-256 hash
- Identical inputs produce identical outputs
- Results can be verified by replay

**Complete Provenance:**
- Run ledger tracks every computation
- Software versions, seeds, and timestamps recorded
- Full audit trail for regulatory compliance

## 6.3 Why This Matters

In high-stakes domains (finance, healthcare, policy), decision-makers need to trust the numbers. If an AI system says "this allocation has a 1.2 Sharpe ratio," they need to know:

1. Was that number actually computed from data?
2. Can I reproduce this result?
3. What assumptions went into this calculation?

GSIP answers all three questions affirmatively.

---

# 7. Reproducibility and Testing

## 7.1 Smoke Tests

The system includes comprehensive tests proving the causal chain from question to results:

**Test 1: Different Questions → Different Objectives**
```python
def test_different_prompts_different_objectives():
    obj1 = formalize_objective("Maximize returns")
    obj2 = formalize_objective("Minimize risk")
    
    assert obj1.primary_direction == "maximize"
    assert obj2.primary_direction == "minimize"
```

**Test 2: Different Objectives → Different Rankings**
```python
def test_different_prompts_different_rankings():
    # Same scenarios, different objectives
    scores1 = score_scenarios(scenarios, objective_maximize_return)
    scores2 = score_scenarios(scenarios, objective_minimize_risk)
    
    ranking1 = sorted(scores1, reverse=True)[:5]
    ranking2 = sorted(scores2, reverse=True)[:5]
    
    assert ranking1 != ranking2  # Different objectives → Different winners
```

**Test 3: Same Seed → Same Results**
```python
def test_reproducibility():
    result1 = run_simulation(seed=42)
    result2 = run_simulation(seed=42)
    
    assert result1["scenario_hash"] == result2["scenario_hash"]
    assert result1["score"] == result2["score"]
```

**Test 4: Minimum Scenario Count**
```python
def test_minimum_scenarios():
    scenarios = generate_structured_scenarios(run_spec)
    assert len(scenarios) >= 50
```

---

# 8. Usage Example

## 8.1 Starting a Run

```bash
curl -X POST http://localhost:8000/api/runs/start \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Maximize portfolio returns while keeping risk under control",
    "domain_pack": "finance-pack",
    "config": {
        "maxScenarios": 100,
        "maxWallTime": 600
    }
  }'
```

Response:
```json
{
    "id": "run-uuid-12345",
    "status": "running",
    "created_at": "2026-02-01T12:00:00Z"
}
```

## 8.2 Monitoring Progress

```bash
curl http://localhost:8000/api/runs/run-uuid-12345
```

Response:
```json
{
    "id": "run-uuid-12345",
    "status": "running",
    "stages": [
        {"name": "formalize_objectives", "status": "completed"},
        {"name": "scenario_generation", "status": "completed"},
        {"name": "optimization_loop", "status": "in_progress"}
    ],
    "counters": {
        "scenarios_proposed": 50,
        "scenarios_simulated": 35,
        "scenarios_scored": 35
    },
    "current_best": {
        "score": 0.82,
        "actions": {"weight_spy": 0.55, "weight_bnd": 0.35, ...}
    }
}
```

## 8.3 Final Results

```json
{
    "id": "run-uuid-12345",
    "status": "completed",
    "summary": {
        "best_score": 0.91,
        "total_scenarios": 100,
        "stop_reason": "converged"
    },
    "top_scenarios": [
        {
            "rank": 1,
            "score": 0.91,
            "actions": {"weight_spy": 0.50, "weight_bnd": 0.30, ...},
            "metrics": {
                "sharpe_ratio": 1.35,
                "total_return": 0.12,
                "max_drawdown": 0.08
            }
        },
        ...
    ]
}
```

---

# 9. Limitations and Future Work

## 9.1 Current Limitations

1. **Keyword-Based Formalization**: May miss nuanced objectives not in the vocabulary
2. **Limited Domain Packs**: Currently only three domains implemented
3. **Single-User Runs**: No multi-user collaboration features
4. **LLM Dependency**: Enhanced formalization requires external API

## 9.2 Future Directions

1. **More Domain Packs**: Healthcare, logistics, energy systems
2. **Improved Formalization**: Fine-tuned models for objective extraction
3. **Interactive Refinement**: User feedback during optimization
4. **Federated Simulation**: Privacy-preserving distributed execution
5. **Explanation Generation**: Natural language summaries of results

---

# 10. Conclusion

GSIP demonstrates that it's possible to build AI-assisted decision support systems that accept natural language input while maintaining complete trust in numerical results.

The key insight is architectural separation: AI helps with understanding intent and explaining results, but all computation happens in verified simulation code with complete audit trails.

This approach enables:
- Accessibility: Non-experts can use simulation-based optimization
- Trust: All numbers are computed, not invented
- Compliance: Full audit trail for regulated industries
- Reproducibility: Deterministic seeding and hashing

GSIP is released as open-source software with the hope that it advances the field of trustworthy AI-assisted decision support.

---

# References

1. Temporal.io. "Temporal: Durable Execution Platform." https://temporal.io/
2. Ray Project. "Ray: A Unified Framework for Scaling AI." https://ray.io/
3. Shahriari, B., et al. "Taking the Human Out of the Loop: A Review of Bayesian Optimization." Proceedings of the IEEE (2016).
4. Deb, K., et al. "A Fast and Elitist Multiobjective Genetic Algorithm: NSGA-II." IEEE Transactions on Evolutionary Computation (2002).
5. Brown, T., et al. "Language Models are Few-Shot Learners." NeurIPS (2020).
6. Law, A.M. "Simulation Modeling and Analysis." McGraw-Hill (2015).

---

# Appendix A: API Reference

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/runs/start | Start a new simulation run |
| GET | /api/runs/{id} | Get run status and results |
| GET | /api/runs/{id}/stream | SSE stream of progress updates |
| POST | /api/score/compute | Compute deterministic score |

## ObjectiveSpec Schema

```json
{
    "description": "string",
    "metrics": [
        {
            "name": "string",
            "direction": "maximize | minimize",
            "weight": 0.0-1.0
        }
    ],
    "primary_direction": "maximize | minimize",
    "constraints": [
        {
            "name": "string",
            "constraint_type": "min | max | eq",
            "value": number,
            "is_hard": boolean
        }
    ],
    "action_ranges": {
        "param_name": {"min": number, "max": number}
    }
}
```

---

# Appendix B: Glossary

**Domain Pack**: A pluggable module that defines state schema, action schema, simulation logic, and scoring for a specific domain.

**Fidelity**: The accuracy level of a simulation. CHEAP = fast approximation, MID = standard, HIGH = full accuracy.

**ObjectiveSpec**: Structured specification of optimization objectives, extracted from natural language.

**Outcome Bundle**: Results from a single simulation execution, including final state, trajectory, and timing.

**Run Ledger**: The immutable audit trail stored in PostgreSQL, containing all computation provenance.

**Scenario**: A specific combination of state, actions, fidelity, and random seed to be simulated.

**Scenario Hash**: SHA-256 hash of scenario inputs, enabling caching and reproducibility verification.
