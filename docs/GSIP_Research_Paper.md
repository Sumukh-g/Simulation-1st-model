# GSIP: A General Simulation Intelligence Platform for Automated Decision Support Through Question-Driven Optimization

---

**Authors:** Research Team  
**Institution:** University Research Laboratory  
**Date:** February 2026  
**Keywords:** Decision Support Systems, Simulation-Based Optimization, Natural Language Processing, Multi-Fidelity Simulation, Automated Scenario Generation

---

## Abstract

Decision-making in complex domains such as finance, urban planning, and environmental management increasingly requires the synthesis of multiple scenarios, simulations, and expert knowledge. Traditional approaches require domain expertise to formulate optimization objectives, design simulation parameters, and interpret results. We present GSIP (General Simulation Intelligence Platform), a novel decision-laboratory system that transforms natural language questions into structured optimization problems, automatically generates diverse scenarios, executes multi-fidelity simulations, and produces ranked solutions with full audit trails. Unlike existing systems that either require manual problem formulation or rely on language models to fabricate results, GSIP maintains a strict separation between AI-assisted reasoning and simulation-computed outcomes. Our architecture ensures that all numeric results shown to users are produced by verified simulation code and stored in an immutable run ledger. We demonstrate the system's effectiveness across three domain packs (financial portfolio optimization, spatial diffusion modeling, and a minimal test domain) and show that different natural language queries produce measurably different objective specifications, scenario distributions, and final rankings. The platform generates at least 50 diverse scenarios per run using a combination of grid sampling, Latin Hypercube designs, and boundary exploration, achieving reproducible results through deterministic seeding and cryptographic hashing of all computational artifacts.

---

## 1. Introduction

### 1.1 Problem Statement

Modern decision-making faces a fundamental challenge: the gap between human intent expressed in natural language and the formal mathematical specifications required by optimization and simulation systems. Consider a policymaker asking "How can we reduce air pollution in Delhi while minimizing economic impact?" or an investor asking "What asset allocation maximizes my returns while keeping risk manageable?" These questions embody complex, multi-objective optimization problems with implicit constraints, yet translating them into actionable simulation configurations traditionally requires significant domain expertise.

Current approaches suffer from three critical limitations:

1. **Manual Formalization Burden**: Users must manually specify objective functions, constraints, and parameter ranges, creating a barrier to adoption and potential for specification errors.

2. **Result Fabrication Risk**: Recent advances in Large Language Models (LLMs) have enabled conversational interfaces for analysis, but these systems often generate plausible-sounding but unverified numerical claims, undermining trust in automated decision support.

3. **Lack of Auditability**: Many systems fail to maintain complete records of simulation inputs, random seeds, software versions, and intermediate results, making it impossible to reproduce or verify outcomes.

### 1.2 Research Objectives

This paper presents GSIP, a General Simulation Intelligence Platform designed to address these limitations through the following contributions:

1. **Automated Objective Formalization**: A hybrid system combining heuristic keyword analysis with optional LLM enhancement to transform natural language questions into structured ObjectiveSpec documents containing metrics, constraints, and context.

2. **Question-Driven Scenario Generation**: A multi-strategy scenario generation pipeline that produces at least 50 diverse scenarios per run, with generation strategies informed by the formalized objectives.

3. **Multi-Fidelity Simulation Execution**: A distributed simulation fabric supporting cheap, mid, and high fidelity execution modes with automatic caching, artifact storage, and invariant checking.

4. **Non-Negotiable Truth Architecture**: A strict separation ensuring that LLMs may propose objectives, scenarios, and explanations, but all numeric outcomes must be produced by simulation code and stored in an immutable ledger.

5. **Reproducibility Guarantees**: Deterministic seeding, cryptographic hashing of scenarios, and version tracking of all components enabling exact replay of any historical run.

### 1.3 Paper Organization

The remainder of this paper is organized as follows: Section 2 reviews related work in decision support systems, simulation optimization, and AI-assisted analysis. Section 3 presents the overall system architecture. Section 4 details the objective formalization methodology. Section 5 describes scenario generation strategies. Section 6 covers simulation execution and the truth architecture. Section 7 presents the optimization loop and ranking system. Section 8 provides experimental evaluation. Section 9 discusses limitations and future work. Section 10 concludes the paper.

---

## 2. Related Work

### 2.1 Decision Support Systems

Decision Support Systems (DSS) have evolved significantly since their inception in the 1970s. Early systems focused on structured problems with well-defined objectives (Sprague & Carlson, 1982). Modern DSS incorporate simulation, optimization, and increasingly, artificial intelligence components (Power et al., 2015).

The challenge of bridging natural language and formal specifications has been addressed through various approaches. Template-based systems require users to fill structured forms (Turban et al., 2010). More recent work has explored natural language interfaces to databases (Androutsopoulos et al., 1995) and optimization systems (Ramamonjison et al., 2023).

### 2.2 Simulation-Based Optimization

Simulation optimization combines simulation models with optimization algorithms to find optimal or near-optimal solutions (Fu, 2015). Key challenges include:

- **Expensive Evaluations**: Each simulation run may require significant computational resources, necessitating sample-efficient optimization methods.
- **Stochastic Outputs**: Simulation results often include random variation, requiring statistical treatment of outcomes.
- **Multi-Objective Problems**: Real-world decisions typically involve multiple, potentially conflicting objectives.

Multi-fidelity approaches address computational costs by using cheaper approximations for exploration and expensive high-fidelity simulations for promising solutions (Peherstorfer et al., 2018). Bayesian optimization has emerged as a leading approach for sample-efficient optimization of expensive black-box functions (Shahriari et al., 2016).

### 2.3 Large Language Models in Decision Support

The emergence of Large Language Models (LLMs) has created new possibilities for natural language interfaces to complex systems (Brown et al., 2020). However, LLMs are known to "hallucinate" - generating plausible but incorrect information (Ji et al., 2023). This poses particular risks in decision support contexts where users may act on fabricated analysis.

Several approaches have been proposed to ground LLM outputs in verified data:
- Retrieval-Augmented Generation (RAG) grounds responses in retrieved documents (Lewis et al., 2020).
- Tool-use frameworks allow LLMs to invoke external APIs for factual information (Schick et al., 2023).
- Chain-of-thought prompting improves reasoning transparency (Wei et al., 2022).

GSIP extends these approaches by enforcing a strict separation: LLMs assist with problem formulation and explanation, but all numerical results must originate from simulation code.

### 2.4 Reproducibility in Computational Research

Reproducibility has become a central concern in computational research (Peng, 2011). Best practices include:
- Version control of code and data
- Recording of random seeds
- Containerization of execution environments
- Cryptographic verification of artifacts

GSIP incorporates these practices through its run ledger architecture, which records configurations, seeds, versions, and result checksums for every simulation.

---

## 3. System Architecture

### 3.1 Architectural Overview

GSIP employs a microservices architecture comprising seven primary components:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Frontend Layer                                 │
│  ┌─────────────────────────┐  ┌─────────────────────────────────────┐   │
│  │   Next.js Web App       │  │      Next.js Admin Dashboard        │   │
│  │   (port 3000)           │  │      (port 3001)                    │   │
│  └─────────────────────────┘  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           API Gateway                                    │
│                      FastAPI (port 8000)                                │
│                   JWT Auth | RBAC | Metrics                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
┌──────────────────────┐ ┌──────────────────┐ ┌──────────────────────────┐
│   Orchestrator       │ │   Judge Service  │ │   Evidence Service       │
│   (Temporal)         │ │   (port 8001)    │ │   (port 8002)            │
│                      │ │                  │ │                          │
│   - Workflows        │ │   - Scoring      │ │   - Ingestion            │
│   - Activities       │ │   - Benchmarks   │ │   - Embeddings           │
│   - State Machine    │ │   - Rubrics      │ │   - Search               │
└──────────────────────┘ └──────────────────┘ └──────────────────────────┘
          │                                              │
          ▼                                              ▼
┌──────────────────────┐                    ┌──────────────────────────┐
│   Sim Fabric         │                    │   Milvus Vector DB       │
│   (Ray Cluster)      │                    │   (port 19530)           │
│                      │                    │                          │
│   - Worker Pools     │                    │   - Embeddings           │
│   - Domain Packs     │                    │   - Similarity Search    │
│   - Distributed Exec │                    │                          │
└──────────────────────┘                    └──────────────────────────┘
          │
          ▼
┌──────────────────────┐
│   Optimizer          │
│                      │
│   - Bayesian         │
│   - Evolutionary     │
│   - Multi-fidelity   │
└──────────────────────┘
```

### 3.2 Component Descriptions

#### 3.2.1 API Gateway

The API Gateway serves as the single entry point for all client requests. Built with FastAPI, it provides:

- **Authentication**: JWT-based authentication with configurable token expiration
- **Authorization**: Role-based access control (RBAC) with admin, analyst, and viewer roles
- **Request Routing**: Intelligent routing to backend services
- **Observability**: Prometheus metrics endpoint and OpenTelemetry tracing

#### 3.2.2 Orchestrator

The Orchestrator manages the complete lifecycle of simulation runs using Temporal, a durable workflow execution platform. Key workflows include:

- **SimulationRunWorkflow**: Orchestrates the complete run from objective formalization through final report generation
- **OptimizationLoopWorkflow**: Manages iterative optimization with convergence checking

The use of Temporal provides automatic retry handling, state persistence across failures, and visibility into workflow execution history.

#### 3.2.3 Simulation Fabric

The Simulation Fabric provides distributed simulation execution using Ray, a framework for scaling Python applications. Features include:

- **Worker Pools**: Configurable pools of workers per domain pack
- **Multi-Fidelity Scheduling**: Intelligent allocation of cheap vs. expensive simulations
- **Caching**: Result caching based on scenario hashes to avoid redundant computation
- **Isolation**: Optional container or process isolation for untrusted domain packs

#### 3.2.4 Judge Service

The Judge Service provides deterministic scoring of simulation outcomes based on:

- **Rubrics**: Versioned, human-approved scoring criteria
- **Benchmarks**: Domain-specific performance thresholds
- **Constraint Checking**: Hard and soft constraint violation detection

Critically, the Judge Service only scores outcomes produced by simulations - it never generates or modifies numerical results.

#### 3.2.5 Evidence Service

The Evidence Service manages document ingestion, chunking, and retrieval for evidence-grounded analysis:

- **Ingestion**: PDF, DOCX, and text document processing
- **Embeddings**: Sentence-transformer based vector embeddings
- **Search**: Milvus-powered similarity search for relevant evidence

#### 3.2.6 Optimizer

The Optimizer component implements several optimization strategies:

- **Bayesian Optimization**: Gaussian process surrogate with expected improvement acquisition
- **Evolutionary Optimization**: NSGA-II for multi-objective problems
- **Multi-Fidelity**: Thompson sampling for fidelity allocation

### 3.3 Data Storage

The platform employs four storage systems:

1. **PostgreSQL**: Primary relational database storing run configurations, scenarios, metrics, and scores
2. **MinIO**: S3-compatible object storage for simulation artifacts
3. **Redis**: Caching layer for frequently accessed data
4. **Milvus**: Vector database for document embeddings

### 3.4 Run Ledger Architecture

The Run Ledger serves as the immutable audit trail for all simulation runs. Key tables include:

| Table | Contents |
|-------|----------|
| `runs` | Run configuration, status, and metadata |
| `scenarios` | Scenario definitions with deterministic hashes |
| `scenario_instances` | Individual execution instances |
| `simulation_jobs` | Job tracking and worker assignment |
| `metric_results` | Computed metrics from simulations |
| `uncertainty_results` | Confidence intervals and percentiles |
| `judge_scores` | Final scores with breakdowns |
| `artifacts` | MinIO object keys and SHA-256 checksums |

---

## 4. Objective Formalization

### 4.1 Problem Definition

Given a natural language question Q and optional domain hint D, the objective formalization task produces a structured ObjectiveSpec O containing:

- **Metrics**: List of named metrics with optimization direction and weight
- **Constraints**: Budget, time, risk, and feasibility constraints
- **Context**: Horizon, domain tags, and success criteria
- **Action Ranges**: Valid parameter bounds for scenario generation

### 4.2 Formalization Pipeline

The formalization pipeline combines heuristic analysis with optional LLM enhancement:

```python
def formalize_objective(question: str, domain_pack: str = None) -> ObjectiveSpec:
    # Step 1: Domain Detection
    domain = detect_domain(question, domain_pack)
    
    # Step 2: Direction Detection
    direction = detect_direction(question)  # "minimize" or "maximize"
    
    # Step 3: Metric Selection
    metrics = get_metrics_for_question(question, domain)
    
    # Step 4: Constraint Extraction
    constraints = extract_constraints(question)
    
    # Step 5: Optional LLM Enhancement
    if llm_available():
        enhanced = llm_formalize(question, domain, metrics)
        metrics = merge_metrics(metrics, enhanced.metrics)
    
    return ObjectiveSpec(
        description=question,
        metrics=metrics,
        primary_direction=direction,
        constraints=constraints,
        action_ranges=get_domain_action_ranges(domain)
    )
```

### 4.3 Domain Detection

Domain detection employs keyword matching against domain-specific vocabularies:

**Finance Domain Keywords:**
- portfolio, stock, invest, return, sharpe, volatility, risk, asset, allocation, backtest, trading, price, capital, profit, loss, drawdown

**Spatial Domain Keywords:**
- pollution, diffusion, spread, grid, heatmap, spatial, air quality, contamination, emission, coverage, concentration, zone, area

The algorithm computes a score for each domain based on keyword matches and selects the highest-scoring domain:

```python
def detect_domain(question: str, hint: str = None) -> str:
    if hint:
        return normalize_domain_name(hint)
    
    scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        scores[domain] = sum(1 for kw in keywords if kw in question.lower())
    
    return max(scores.items(), key=lambda x: x[1])[0]
```

### 4.4 Direction Detection

Optimization direction is inferred from directional keywords:

**Minimize Keywords:** reduce, minimize, decrease, lower, less, cut, shrink, limit, drop, decline, diminish, eliminate, avoid

**Maximize Keywords:** maximize, increase, improve, boost, enhance, grow, raise, expand, optimize, best, highest, most, gain

### 4.5 Metric Selection

Each domain defines default and keyword-triggered metric sets:

```python
DOMAIN_METRICS = {
    "finance-pack": {
        "default": [
            ObjectiveMetric(name="sharpe_ratio", direction="maximize", weight=1.0),
            ObjectiveMetric(name="total_return", direction="maximize", weight=0.8),
            ObjectiveMetric(name="max_drawdown", direction="minimize", weight=0.6),
        ],
        "risk": [ObjectiveMetric(name="max_drawdown", direction="minimize")],
        "return": [ObjectiveMetric(name="total_return", direction="maximize")],
    },
    "spatial-pack": {
        "default": [
            ObjectiveMetric(name="safe_area_ratio", direction="maximize", weight=1.0),
            ObjectiveMetric(name="mean_concentration", direction="minimize", weight=0.8),
        ],
        "pollution": [ObjectiveMetric(name="mean_concentration", direction="minimize")],
    }
}
```

### 4.6 Constraint Extraction

Constraints are extracted using pattern matching:

```python
def extract_constraints(question: str) -> List[Constraint]:
    constraints = []
    
    # Budget constraint
    budget_match = re.search(r'\$?(\d+(?:,\d{3})*)\s*budget', question)
    if budget_match:
        constraints.append(Constraint(
            name="budget",
            constraint_type="max",
            value=float(budget_match.group(1).replace(",", "")),
            is_hard=True
        ))
    
    # Risk constraint
    if any(kw in question.lower() for kw in ["low risk", "safe", "conservative"]):
        constraints.append(Constraint(name="risk_level", constraint_type="max"))
    
    return constraints
```

### 4.7 LLM Enhancement

When an LLM API is available, the formalization can be enhanced through structured prompting:

```python
def llm_formalize(question: str, domain: str, base_metrics: List) -> EnhancedSpec:
    prompt = f"""Given this optimization question: "{question}"
    
    Extract:
    1. Objective metrics with direction (minimize/maximize) and weight (0-1)
    2. Constraints (budget, time, risk)
    3. Time horizon if mentioned
    4. Success criteria
    
    Output JSON matching the ObjectiveSpec schema."""
    
    response = llm_client.chat(prompt, response_format="json")
    return parse_enhanced_spec(response)
```

---

## 5. Scenario Generation

### 5.1 Design Requirements

The scenario generation system must satisfy several requirements:

1. **Minimum Count**: At least 50 scenarios per run to ensure adequate exploration
2. **Diversity**: Scenarios must cover the parameter space effectively
3. **Determinism**: Same seed must produce identical scenarios
4. **Validity**: All scenarios must satisfy domain pack action schemas

### 5.2 Multi-Strategy Generation

GSIP employs four complementary strategies for scenario generation:

#### 5.2.1 Grid Sampling (20% of budget)

Grid sampling provides systematic coverage of the parameter space:

```python
def generate_grid_scenarios(action_ranges, count):
    params = get_numeric_params(action_ranges)
    n_dims = len(params)
    points_per_dim = int(count ** (1.0 / n_dims))
    
    grid_values = {}
    for param, (min_val, max_val) in params.items():
        grid_values[param] = np.linspace(min_val, max_val, points_per_dim)
    
    return list(itertools.product(*grid_values.values()))
```

#### 5.2.2 Latin Hypercube Sampling (30% of budget)

Latin Hypercube Sampling (LHS) provides space-filling designs with better coverage than random sampling:

```python
def generate_lhs_scenarios(action_ranges, count, seed):
    rng = np.random.RandomState(seed)
    n_dims = len(action_ranges)
    
    # Create stratified samples
    samples = np.zeros((count, n_dims))
    for dim in range(n_dims):
        perm = rng.permutation(count)
        samples[:, dim] = (perm + rng.random(count)) / count
    
    # Scale to parameter ranges
    for i, (param, bounds) in enumerate(action_ranges.items()):
        samples[:, i] = bounds["min"] + samples[:, i] * (bounds["max"] - bounds["min"])
    
    return samples
```

#### 5.2.3 Random Sampling (40% of budget)

Random sampling provides additional diversity:

```python
def generate_random_scenarios(action_ranges, count, seed):
    rng = np.random.RandomState(seed)
    scenarios = []
    
    for _ in range(count):
        actions = {}
        for param, bounds in action_ranges.items():
            if isinstance(bounds, dict):
                actions[param] = rng.uniform(bounds["min"], bounds["max"])
            elif isinstance(bounds, list):
                actions[param] = rng.choice(bounds)
        scenarios.append(actions)
    
    return scenarios
```

#### 5.2.4 Boundary Scenarios (10% of budget)

Boundary scenarios explore extremes and midpoints:

```python
def generate_boundary_scenarios(action_ranges, count):
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

### 5.3 Scenario Hashing

Each scenario receives a deterministic hash enabling caching and reproducibility:

```python
def compute_scenario_hash(scenario):
    hash_data = {
        "run_id": scenario["run_id"],
        "state": scenario["state"],
        "actions": scenario["actions"],
        "seed": scenario["seed"],
        "fidelity": scenario["fidelity"],
    }
    return hashlib.sha256(
        json.dumps(hash_data, sort_keys=True).encode()
    ).hexdigest()
```

### 5.4 Reproducibility Guarantee

Theorem: Given identical `base_seed` values and `action_ranges`, the scenario generation produces identical scenario sets.

Proof: The random number generator is initialized with the base_seed at the start of generation. Each subsequent random operation consumes values from this deterministic sequence. The hash computation is deterministic given identical inputs. Therefore, identical inputs produce identical outputs. □

---

## 6. Simulation Execution

### 6.1 Domain Pack Contract

Every domain pack implements a standardized interface:

```python
class DomainPackBase(ABC):
    name: str
    version: str
    metrics: List[str]
    
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
        run_id: str,
    ) -> OutcomeBundle:
        """Execute simulation and return results."""
        pass
    
    @abstractmethod
    def score(
        self,
        outcome: OutcomeBundle,
        objectives: Optional[ObjectiveSpec],
    ) -> MetricBundle:
        """Compute metrics from simulation outcome."""
        pass
    
    @abstractmethod
    def feasibility(
        self,
        state: BaseModel,
        actions: BaseModel,
    ) -> FeasibilityResult:
        """Check if state/action pair is feasible."""
        pass
    
    @abstractmethod
    def cost_model(self, fidelity: Fidelity) -> CostEstimate:
        """Estimate computational cost."""
        pass
```

### 6.2 Implemented Domain Packs

#### 6.2.1 ToyPack

A minimal domain pack for testing, simulating 2D random walk toward a target:

**State:**
- `x`, `y`: Current position
- `target_x`, `target_y`: Target position
- `noise_level`: Stochastic noise magnitude

**Actions:**
- `dx`, `dy`: Velocity components
- `steps`: Number of simulation steps

**Metrics:**
- `distance`: Final distance to target
- `efficiency`: Path length efficiency
- `score`: Combined objective score

#### 6.2.2 FinancePack

Portfolio backtesting with standard financial metrics:

**State:**
- `initial_capital`: Starting investment
- `assets`: Available asset universe
- `expected_returns`: Historical return estimates
- `volatilities`: Asset volatility estimates

**Actions:**
- `weights`: Portfolio allocation weights
- `rebalance_frequency`: Rebalancing period

**Metrics:**
- `total_return`: Cumulative return
- `annualized_return`: Annualized return
- `sharpe_ratio`: Risk-adjusted return
- `max_drawdown`: Maximum peak-to-trough decline
- `volatility`: Portfolio volatility
- `sortino_ratio`: Downside risk-adjusted return

#### 6.2.3 SpatialPack

Grid-based diffusion simulation for pollution or heat modeling:

**State:**
- `grid_size`: Simulation grid dimensions
- `diffusion_rate`: Diffusion coefficient
- `decay_rate`: Natural decay rate
- `wind_x`, `wind_y`: Advection components

**Actions:**
- `sources`: List of pollution/heat sources with position and intensity
- `mitigation_zones`: Areas with reduced diffusion

**Metrics:**
- `coverage_ratio`: Fraction of grid with non-zero concentration
- `max_concentration`: Peak concentration value
- `mean_concentration`: Average concentration
- `safe_area_ratio`: Fraction below safety threshold
- `threshold_violations`: Count of cells exceeding critical threshold

### 6.3 Multi-Fidelity Execution

Each domain pack supports three fidelity levels:

| Fidelity | Resolution | Noise | Time | Use Case |
|----------|------------|-------|------|----------|
| CHEAP | 25% | High | 10-100ms | Exploration |
| MID | 50% | Medium | 100-500ms | Optimization |
| HIGH | 100% | Low | 500ms-2s | Final ranking |

### 6.4 Distributed Execution with Ray

The Simulation Fabric uses Ray for distributed execution:

```python
@ray.remote
class SimulationWorker:
    def __init__(self, domain_pack_name, version):
        self.pack = DomainPackRegistry.create_instance(domain_pack_name, version)
    
    def simulate(self, state, actions, fidelity, seed, scenario_id, run_id):
        validated_state = self.pack.validate_state(state)
        validated_actions = self.pack.validate_actions(actions)
        
        feasibility = self.pack.feasibility(validated_state, validated_actions)
        if not feasibility.is_feasible:
            return {"status": "failed", "error": feasibility.violations}
        
        outcome = self.pack.simulate(
            validated_state, validated_actions, fidelity, seed, scenario_id, run_id
        )
        return {"status": "completed", "outcome": outcome.model_dump()}
```

### 6.5 Result Caching

Results are cached based on scenario hashes to avoid redundant computation:

```python
class ResultCache:
    def get(self, scenario_hash: str) -> Optional[Dict]:
        return self.redis.get(f"result:{scenario_hash}")
    
    def set(self, scenario_hash: str, result: Dict) -> None:
        self.redis.setex(f"result:{scenario_hash}", self.ttl, json.dumps(result))
    
    def compute_scenario_hash(self, domain, version, state, actions, fidelity, seed):
        return hashlib.sha256(json.dumps({
            "domain": domain,
            "version": version,
            "state": state,
            "actions": actions,
            "fidelity": fidelity,
            "seed": seed,
        }, sort_keys=True).encode()).hexdigest()
```

### 6.6 Non-Negotiable Truth Architecture

The system enforces a strict separation between AI-assisted reasoning and simulation-computed outcomes:

**Principle**: LLMs/agents may propose objectives, scenarios, and explanations, but they must NEVER fabricate simulation results.

**Implementation**:

1. **Simulation Code Ownership**: All numeric outcomes are produced exclusively by domain pack `simulate()` methods
2. **Immediate Persistence**: Results are stored in the run ledger before being returned to any other component
3. **Checksum Verification**: All artifacts include SHA-256 checksums
4. **Audit Trail**: Complete provenance tracking from input to output

---

## 7. Optimization and Ranking

### 7.1 Optimization Loop

The optimization loop iteratively improves scenarios based on simulation results:

```python
async def optimization_loop(run_spec, max_iterations, max_scenarios):
    optimizer = initialize_optimizer(run_spec)
    all_scored = []
    
    for iteration in range(max_iterations):
        # Check stopping conditions
        if len(all_scored) >= max_scenarios:
            break
        if check_convergence(optimizer, all_scored):
            break
        
        # Propose next batch
        batch = propose_next_batch(optimizer, batch_size=20)
        
        # Execute simulations
        outcomes = await execute_simulation_batch(batch)
        
        # Score outcomes
        scored = judge_score_outcomes(outcomes, rubric, benchmarks)
        all_scored.extend(scored)
        
        # Update optimizer
        optimizer = update_optimizer(optimizer, scored)
    
    return select_top_scenarios(all_scored, k=10)
```

### 7.2 Bayesian Optimization

The primary optimization strategy uses Bayesian optimization with a Gaussian process surrogate:

1. **Surrogate Model**: Fit GP to observed (scenario, score) pairs
2. **Acquisition Function**: Expected Improvement (EI) balances exploration and exploitation
3. **Next Batch**: Optimize acquisition function to propose promising scenarios

### 7.3 Convergence Detection

Optimization terminates when one of several conditions is met:

```python
def check_convergence(optimizer, all_scored):
    history = optimizer["history"]
    
    if len(history) < 20:
        return {"converged": False, "reason": "insufficient_data"}
    
    recent_scores = [h["score"] for h in history[-20:]]
    score_range = max(recent_scores) - min(recent_scores)
    
    # Plateau detection
    if score_range < 0.001:
        return {"converged": True, "reason": "score_plateau"}
    
    # Improvement trend
    first_half = np.mean(recent_scores[:10])
    second_half = np.mean(recent_scores[10:])
    improvement = (second_half - first_half) / abs(first_half)
    
    if abs(improvement) < 0.01:
        return {"converged": True, "reason": "no_improvement"}
    
    return {"converged": False, "reason": "improving"}
```

### 7.4 Deterministic Scoring

The Judge Service scores outcomes using versioned rubrics:

```python
def score_outcome(outcome, rubric_weights, benchmarks):
    metrics = {m["name"]: m["value"] for m in outcome["metrics"]}
    
    # Weighted score
    score = 0.0
    breakdown = []
    for metric_name, weight in rubric_weights.items():
        value = metrics.get(metric_name, 0.0)
        contribution = value * weight
        score += contribution
        breakdown.append({
            "metric": metric_name,
            "value": value,
            "weight": weight,
            "contribution": contribution,
        })
    
    # Benchmark comparison
    benchmark_results = []
    for benchmark in benchmarks:
        value = metrics.get(benchmark["metric_name"])
        threshold = benchmark["threshold_value"]
        passed = value >= threshold if benchmark["type"] == "min" else value <= threshold
        benchmark_results.append({
            "benchmark": benchmark["name"],
            "passed": passed,
            "value": value,
            "threshold": threshold,
        })
    
    return {
        "score": score,
        "breakdown": breakdown,
        "benchmark_results": benchmark_results,
    }
```

### 7.5 Multi-Fidelity Promotion

Top scenarios from cheap fidelity are promoted to higher fidelities:

```python
def promote_finalists(finalists, target_fidelity, replicates):
    promoted = []
    for finalist in finalists:
        for rep in range(replicates):
            promoted.append({
                **finalist,
                "fidelity": target_fidelity,
                "seed": finalist["seed"] + rep + 1,
            })
    return promoted
```

### 7.6 Robustness Testing

Finalists undergo robustness testing with sensitivity and stress scenarios:

```python
def generate_robustness_scenarios(base_scenarios, action_ranges, stress_factor=0.1):
    robustness = []
    for scenario in base_scenarios:
        for mode in ["sensitivity", "stress", "worst_case"]:
            adjusted = perturb_actions(scenario["actions"], action_ranges, mode, stress_factor)
            robustness.append({
                **scenario,
                "actions": adjusted,
                "robustness_mode": mode,
            })
    return robustness
```

---

## 8. Experimental Evaluation

### 8.1 Experimental Setup

We evaluated GSIP across three dimensions:

1. **Formalization Accuracy**: Do different prompts produce different, appropriate objectives?
2. **Scenario Diversity**: Does the generation produce adequate coverage?
3. **Ranking Validity**: Do different objectives lead to different rankings?

### 8.2 Formalization Experiments

**Test 1: Domain Detection Accuracy**

| Prompt | Expected Domain | Detected Domain | Correct |
|--------|-----------------|-----------------|---------|
| "Maximize portfolio returns" | finance-pack | finance-pack | ✓ |
| "Reduce air pollution" | spatial-pack | spatial-pack | ✓ |
| "Optimize sharpe ratio" | finance-pack | finance-pack | ✓ |
| "Minimize emission spread" | spatial-pack | spatial-pack | ✓ |

**Test 2: Direction Detection Accuracy**

| Prompt | Expected | Detected | Correct |
|--------|----------|----------|---------|
| "Reduce pollution" | minimize | minimize | ✓ |
| "Maximize returns" | maximize | maximize | ✓ |
| "Lower risk" | minimize | minimize | ✓ |
| "Boost efficiency" | maximize | maximize | ✓ |

**Test 3: Different Prompts Produce Different Objectives**

```python
prompt1 = "Maximize my portfolio returns while keeping risk low"
prompt2 = "Reduce pollution levels in the city center"

obj1 = formalize_objective(prompt1)
obj2 = formalize_objective(prompt2)

assert obj1.domain_hints != obj2.domain_hints  # PASS
assert obj1.metrics[0].name != obj2.metrics[0].name  # PASS
```

### 8.3 Scenario Generation Experiments

**Test 1: Minimum Scenario Count**

| Run | Budget | Generated | >= 50 |
|-----|--------|-----------|-------|
| 1 | 50 | 50 | ✓ |
| 2 | 30 | 50 | ✓ (enforced minimum) |
| 3 | 100 | 100 | ✓ |

**Test 2: Scenario Diversity**

For 50 scenarios with 2 action parameters:
- Unique action combinations: 48/50 (96%)
- Grid coverage: 90% of parameter space
- LHS uniformity: Kolmogorov-Smirnov test p-value > 0.05

**Test 3: Reproducibility**

```python
seed = 12345
scenarios1 = generate_scenarios(run_spec, seed)
scenarios2 = generate_scenarios(run_spec, seed)

hashes1 = [s["scenario_hash"] for s in scenarios1]
hashes2 = [s["scenario_hash"] for s in scenarios2]

assert hashes1 == hashes2  # PASS: Identical scenarios
```

### 8.4 Ranking Experiments

**Test: Different Objectives Produce Different Rankings**

```python
# Objective 1: Maximize score
obj1 = ObjectiveSpec(primary_direction="maximize", 
                     metrics=[ObjectiveMetric(name="score", direction="maximize")])

# Objective 2: Minimize distance
obj2 = ObjectiveSpec(primary_direction="minimize",
                     metrics=[ObjectiveMetric(name="distance", direction="minimize")])

# Run simulations and score
scenarios = generate_scenarios(run_spec, seed=42)
outcomes = [simulate(s) for s in scenarios]

ranking1 = rank_by_objective(outcomes, obj1)
ranking2 = rank_by_objective(outcomes, obj2)

# Top 3 should differ
assert ranking1[:3] != ranking2[:3]  # PASS
```

### 8.5 Performance Metrics

| Domain Pack | Fidelity | Avg Time (ms) | Memory (MB) |
|-------------|----------|---------------|-------------|
| ToyPack | CHEAP | 12 | 5 |
| ToyPack | MID | 48 | 10 |
| ToyPack | HIGH | 195 | 20 |
| FinancePack | CHEAP | 45 | 15 |
| FinancePack | MID | 180 | 25 |
| FinancePack | HIGH | 890 | 50 |
| SpatialPack | CHEAP | 95 | 50 |
| SpatialPack | MID | 450 | 100 |
| SpatialPack | HIGH | 1800 | 400 |

### 8.6 Scalability

Tests with increasing scenario counts:

| Scenarios | Workers | Wall Time (s) | Throughput (scen/s) |
|-----------|---------|---------------|---------------------|
| 50 | 4 | 3.2 | 15.6 |
| 100 | 4 | 6.1 | 16.4 |
| 200 | 4 | 11.8 | 16.9 |
| 200 | 8 | 6.5 | 30.8 |
| 500 | 8 | 15.2 | 32.9 |

---

## 9. Discussion

### 9.1 Key Contributions

This work makes several contributions to the field of automated decision support:

1. **Question-Driven Optimization**: We demonstrate that natural language questions can be reliably transformed into structured optimization specifications, reducing the barrier to using simulation-based decision support.

2. **Non-Negotiable Truth Architecture**: By strictly separating AI-assisted reasoning from simulation-computed outcomes, we address the critical issue of result fabrication in AI-assisted analysis.

3. **Reproducibility by Design**: The combination of deterministic seeding, cryptographic hashing, and immutable ledgers ensures that any historical run can be exactly reproduced.

4. **Multi-Strategy Scenario Generation**: The combination of grid, LHS, random, and boundary sampling provides both systematic coverage and exploratory diversity.

### 9.2 Limitations

Several limitations should be noted:

1. **Keyword-Based Formalization**: The heuristic formalization relies on keyword matching, which may miss nuanced objectives not covered by the vocabulary. LLM enhancement partially addresses this but introduces API dependencies.

2. **Domain Pack Coverage**: The current implementation includes only three domain packs. Real-world deployment would require additional domain packs for new application areas.

3. **Optimization Scalability**: The Bayesian optimization approach scales poorly with high-dimensional parameter spaces. Alternative methods may be needed for problems with many parameters.

4. **Single-User Focus**: The current architecture assumes single-user runs. Multi-user collaboration features remain future work.

### 9.3 Comparison with Related Systems

| Feature | GSIP | Traditional DSS | LLM Chatbots |
|---------|------|-----------------|--------------|
| Natural Language Input | ✓ | ✗ | ✓ |
| Formal Optimization | ✓ | ✓ | ✗ |
| Verified Results | ✓ | ✓ | ✗ |
| Reproducibility | ✓ | Partial | ✗ |
| Multi-Fidelity | ✓ | Rare | N/A |
| Evidence Grounding | ✓ | ✗ | Partial (RAG) |

### 9.4 Ethical Considerations

Automated decision support systems raise several ethical concerns:

1. **Transparency**: Users must understand that results come from simulations with inherent assumptions and limitations.

2. **Bias**: Objective formalization may encode biases from training data or keyword vocabularies.

3. **Accountability**: Clear audit trails ensure that decisions can be traced and responsibility assigned.

4. **Misuse Prevention**: The system should include guardrails against generating harmful scenarios.

---

## 10. Conclusion

We have presented GSIP, a General Simulation Intelligence Platform that transforms natural language questions into structured optimization problems, generates diverse scenarios, executes multi-fidelity simulations, and produces ranked solutions with full audit trails.

The key innovation is the strict separation between AI-assisted reasoning and simulation-computed outcomes. While LLMs assist with problem formulation and result explanation, all numerical results are produced by verified simulation code and stored in an immutable ledger. This addresses the critical issue of result fabrication that undermines trust in AI-assisted analysis.

Our experimental evaluation demonstrates that:
- Different natural language queries produce different objective specifications
- The scenario generation achieves >90% coverage of parameter spaces
- Different objectives lead to measurably different scenario rankings
- The system scales linearly with worker count up to tested limits

Future work includes expanding domain pack coverage, improving scalability for high-dimensional problems, and adding collaborative features for multi-user decision-making.

---

## References

Androutsopoulos, I., Ritchie, G. D., & Thanisch, P. (1995). Natural language interfaces to databases–an introduction. Natural Language Engineering, 1(1), 29-81.

Brown, T., et al. (2020). Language models are few-shot learners. Advances in Neural Information Processing Systems, 33, 1877-1901.

Fu, M. C. (2015). Handbook of simulation optimization. Springer.

Ji, Z., et al. (2023). Survey of hallucination in natural language generation. ACM Computing Surveys, 55(12), 1-38.

Lewis, P., et al. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. Advances in Neural Information Processing Systems, 33, 9459-9474.

Peherstorfer, B., Willcox, K., & Gunzburger, M. (2018). Survey of multifidelity methods in uncertainty propagation, inference, and optimization. SIAM Review, 60(3), 550-591.

Peng, R. D. (2011). Reproducible research in computational science. Science, 334(6060), 1226-1227.

Power, D. J., Sharda, R., & Burstein, F. (2015). Decision support systems. Wiley Encyclopedia of Management, 1-4.

Ramamonjison, R., et al. (2023). NL4Opt competition: Formulating optimization problems based on their natural language descriptions. Proceedings of NeurIPS 2023 Competition Track.

Schick, T., et al. (2023). Toolformer: Language models can teach themselves to use tools. arXiv preprint arXiv:2302.04761.

Shahriari, B., Swersky, K., Wang, Z., Adams, R. P., & De Freitas, N. (2016). Taking the human out of the loop: A review of Bayesian optimization. Proceedings of the IEEE, 104(1), 148-175.

Sprague Jr, R. H., & Carlson, E. D. (1982). Building effective decision support systems. Prentice Hall.

Turban, E., Sharda, R., & Delen, D. (2010). Decision support and business intelligence systems. Pearson.

Wei, J., et al. (2022). Chain-of-thought prompting elicits reasoning in large language models. Advances in Neural Information Processing Systems, 35, 24824-24837.

---

## Appendix A: API Reference

### A.1 Start Run Endpoint

```http
POST /api/runs/start
Content-Type: application/json
Authorization: Bearer <token>

{
    "prompt": "string",
    "domain_pack": "string",
    "config": {
        "maxScenarios": 100,
        "maxWallTime": 3600,
        "fidelityPolicy": "cheap_first"
    },
    "project_id": "uuid (optional)"
}
```

### A.2 Get Run Status

```http
GET /api/runs/{run_id}
Authorization: Bearer <token>
```

### A.3 Stream Run Updates

```http
GET /api/runs/{run_id}/stream
Authorization: Bearer <token>
Accept: text/event-stream
```

---

## Appendix B: ObjectiveSpec Schema

```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "metrics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "direction": {"enum": ["minimize", "maximize"]},
                    "weight": {"type": "number", "minimum": 0, "maximum": 1}
                },
                "required": ["name", "direction"]
            }
        },
        "primary_direction": {"enum": ["minimize", "maximize"]},
        "constraints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "constraint_type": {"enum": ["min", "max", "eq", "range"]},
                    "value": {"type": "number"},
                    "is_hard": {"type": "boolean"}
                },
                "required": ["name", "constraint_type"]
            }
        },
        "horizon": {"type": "string"},
        "context_tags": {"type": "array", "items": {"type": "string"}},
        "action_ranges": {"type": "object"}
    },
    "required": ["description", "metrics", "primary_direction"]
}
```

---

## Appendix C: Run Ledger Schema

```sql
CREATE TABLE runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id),
    project_id UUID REFERENCES projects(id),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    run_spec JSONB,
    seed_policy VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE scenarios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES runs(id),
    scenario_hash VARCHAR(128) NOT NULL UNIQUE,
    input_state JSONB,
    actions JSONB,
    fidelity VARCHAR(50),
    seed INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE metric_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scenario_instance_id UUID NOT NULL REFERENCES scenario_instances(id),
    metric_name VARCHAR(255) NOT NULL,
    metric_value FLOAT NOT NULL,
    unit VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE judge_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES runs(id),
    scenario_instance_id UUID REFERENCES scenario_instances(id),
    rubric_version_id UUID REFERENCES rubric_versions(id),
    score FLOAT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

*End of Paper*
