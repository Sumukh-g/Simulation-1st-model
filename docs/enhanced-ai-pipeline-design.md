# Enhanced AI Pipeline Design: First Principles Problem Understanding

This document captures the design decisions and implementation plan for enhancing the GSIP pipeline with:
1. **First Principles Problem Understanding** — AI deeply analyzes questions using fundamental principles
2. **Clarification Questions** — AI identifies unknowns and asks the user before proceeding
3. **AI-Assisted Scenario Generation** — Scenarios grounded in real-world context
4. **Enriched State and Context** — Simulation receives rich, contextual information

---

## Table of Contents

1. [Current vs. Enhanced Pipeline](#1-current-vs-enhanced-pipeline)
2. [What is a Domain Pack?](#2-what-is-a-domain-pack)
3. [First Principles Problem Understanding](#3-first-principles-problem-understanding)
4. [Clarification Questions Checklist](#4-clarification-questions-checklist)
5. [AI-Assisted Scenario Generation](#5-ai-assisted-scenario-generation)
6. [Enriched State and Context Flow](#6-enriched-state-and-context-flow)
7. [End-to-End Workflow](#7-end-to-end-workflow)
8. [Data Structures](#8-data-structures)
9. [Examples](#9-examples)
10. [Implementation Plan](#10-implementation-plan)

---

## 1. Current vs. Enhanced Pipeline

### Current Pipeline

| Step | Current Approach | Uses AI? |
|------|------------------|----------|
| Formalization | Keyword extraction + optional LLM for objectives/metrics | Optional |
| Scenario Generation | Algorithmic sampling (Grid, LHS, Random, Boundary) | No |
| State | Generic defaults from domain pack | No |
| Simulate | Domain pack code runs with state + actions | No |
| Scoring | Deterministic math (rubrics, benchmarks) | No |
| Explanation | LLM summarizes results | Optional |

### Enhanced Pipeline (Proposed)

| Step | Enhanced Approach | Uses AI? |
|------|-------------------|----------|
| **Problem Understanding** | First principles analysis, domain detection, real-world context gathering | **Yes** |
| **Clarification Questions** | AI identifies unknowns, asks user for missing information | **Yes** |
| **Scenario Generation** | AI-assisted proposals + algorithmic expansion, grounded in reality | **Yes** |
| **State** | Enriched with real-world data from Problem Understanding | AI-informed |
| **Simulate** | Domain pack receives context/summary for awareness | Context-aware |
| Scoring | Deterministic math (unchanged) | No |
| Explanation | LLM summarizes results (unchanged) | Optional |

---

## 2. What is a Domain Pack?

A **domain pack** is the **simulation logic** for a specific subject/domain. It defines:

| Component | Purpose | Example (Generator) |
|-----------|---------|---------------------|
| **State** | Initial conditions / environment | Magnet strength, coil turns, RPM |
| **Actions** | Levers the optimizer can vary | Increase RPM, add coil turns |
| **Simulate** | The physics/logic of what happens | Faraday's law calculation |
| **Metrics** | How to measure outcomes | Power output, efficiency |
| **Feasibility** | What's valid/invalid | RPM within mechanical limits |
| **Cost Model** | Estimate compute cost per fidelity | Cheap = simple calc, High = detailed sim |

### Domain Pack Contract

Every domain pack implements:

```
DomainPackBase
├── state_schema()      → Pydantic model for initial conditions
├── action_schema()     → Pydantic model for actions/levers
├── simulate()          → Runs the simulation, returns OutcomeBundle
├── score()             → Computes metrics from outcome
├── feasibility()       → Checks if state+actions are valid
└── cost_model()        → Estimates compute cost for fidelity level
```

### Key Insight

- **Domain pack = simulation logic for a specific subject**
- The platform (formalization, scenarios, optimization, scoring) is **generic**
- Domain expertise lives **only** in the domain pack

---

## 3. First Principles Problem Understanding

### What It Does

When the AI receives a question, it doesn't just extract keywords. It:

1. **Identifies the core objective** — What is the user really trying to achieve?
2. **Applies first principles** — What fundamental laws/equations govern this?
3. **Decomposes into factors** — What variables affect the outcome?
4. **Derives actionable levers** — What can we change?
5. **Identifies constraints** — What limits us (physics, cost, safety)?
6. **Gathers real-world context** — If a specific subject is mentioned (Delhi, a specific generator), gather relevant data

### First Principles Thinking Process

```
User Question
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 1: PARSE THE GOAL                                      │
│                                                             │
│ "How to increase electricity generation of this generator?" │
│                                                             │
│ → Goal: Maximize electrical power output                    │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 2: IDENTIFY FIRST PRINCIPLES                           │
│                                                             │
│ Domain: Electromagnetic generator                           │
│                                                             │
│ Governing equations:                                        │
│   • P = V × I (Power = Voltage × Current)                   │
│   • V = N × dΦ/dt (Faraday's Law)                           │
│   • R = ρL/A (Resistance depends on wire properties)        │
│                                                             │
│ → These equations tell us what physically matters           │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 3: DECOMPOSE INTO FACTORS                              │
│                                                             │
│ From the equations, what variables affect power output?     │
│                                                             │
│   • Magnetic field strength (Φ)                             │
│   • Number of coil turns (N)                                │
│   • Rotation speed (dΦ/dt)                                  │
│   • Wire resistance (R)                                     │
│   • Load impedance                                          │
│   • Cooling capacity (limits current)                       │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 4: DERIVE ACTIONABLE LEVERS                            │
│                                                             │
│ What can we actually change?                                │
│                                                             │
│   • Increase magnet strength → More flux → More voltage     │
│   • Add more coil turns → More voltage (but more R)         │
│   • Increase RPM → Higher dΦ/dt → More voltage              │
│   • Use thicker wire → Lower R → More current capacity      │
│   • Improve cooling → Higher max current                    │
│   • Optimize air gap → Better flux linkage                  │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 5: IDENTIFY CONSTRAINTS                                │
│                                                             │
│ What limits us?                                             │
│                                                             │
│   • Material limits (max magnet strength, wire current)     │
│   • Mechanical limits (max RPM before failure)              │
│   • Thermal limits (overheating damages coils)              │
│   • Cost constraints (budget for materials)                 │
│   • Size/weight constraints (physical envelope)             │
│   • Safety requirements (voltage/current limits)            │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 6: IDENTIFY UNKNOWNS (→ Clarification Questions)       │
│                                                             │
│ What information is missing?                                │
│                                                             │
│   • What type of generator? (AC/DC, synchronous, induction) │
│   • Current specifications? (existing power, RPM, size)     │
│   • What's the budget?                                      │
│   • Are there size/weight constraints?                      │
│   • What's the use case? (grid, portable, industrial)       │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Clarification Questions Checklist

### The Concept

Before proceeding with simulation, the AI should identify **every unanswered question** it has after first principles analysis. These are presented to the user as a **checklist** for clarification.

### Categories of Clarification Questions

| Category | Purpose | Example Questions |
|----------|---------|-------------------|
| **Subject Specifics** | What exactly are we simulating? | "What type of generator? AC or DC?" |
| **Current State** | What's the starting point? | "What's the current power output?" |
| **Constraints** | What limits the solution? | "Is there a budget limit?" "Size constraints?" |
| **Goals** | Clarify the objective | "Maximize power or efficiency?" "Trade-off preference?" |
| **Context** | Real-world factors | "Where will this be used?" "Environmental conditions?" |
| **Data Availability** | What info does the user have? | "Do you have the generator's specifications?" |

### Clarification Question Structure

Each question should have:

```
{
  "id": "q1",
  "category": "subject_specifics",
  "question": "What type of generator is this?",
  "why_needed": "Different generator types have different physics (AC vs DC, synchronous vs induction)",
  "options": ["AC Synchronous", "AC Induction", "DC Brushed", "DC Brushless", "Other"],
  "is_required": true,
  "default_if_skipped": "AC Synchronous (assumed)"
}
```

### Workflow with Clarification

```
User Question
     │
     ▼
Problem Understanding (First Principles)
     │
     ▼
┌─────────────────────────────────────┐
│ Generate Clarification Questions    │
│                                     │
│ □ What type of generator?           │
│ □ Current power output?             │
│ □ Budget constraints?               │
│ □ Size/weight limits?               │
│ □ Operating environment?            │
└─────────────────────────────────────┘
     │
     ▼
Present to User → User Answers (or skips with defaults)
     │
     ▼
Enriched Problem Understanding
     │
     ▼
Continue to Scenario Generation
```

### Handling Unanswered Questions

| User Response | System Behavior |
|---------------|-----------------|
| Answers all | Proceed with full context |
| Answers some | Use answers + defaults for rest |
| Skips all | Use reasonable defaults, note assumptions |

All assumptions are **logged** in the run ledger for audit.

---

## 5. AI-Assisted Scenario Generation

### Current Approach (Algorithmic Only)

- Grid sampling (systematic)
- Latin Hypercube Sampling (space-filling)
- Random sampling (exploration)
- Boundary scenarios (extremes)

**Problem:** Scenarios are mathematically diverse but may not be **realistically meaningful**.

### Enhanced Approach (AI-Assisted)

1. **AI proposes candidate scenarios** based on real-world knowledge and first principles understanding
2. **Algorithmic sampling expands** around these candidates for diversity
3. **All scenarios are grounded** in the context from Problem Understanding

### Example: "Reduce pollution in Delhi"

| Current (Algorithmic) | Enhanced (AI-Assisted) |
|-----------------------|------------------------|
| Random source positions on grid | Sources placed at real Delhi industrial zones (Anand Vihar, Okhla) |
| Random mitigation zones | Mitigation zones at real sensitive areas (schools, hospitals, residential) |
| Generic wind patterns | Winter NW wind pattern typical for Delhi |
| No seasonal awareness | Scenarios for winter (high pollution) vs monsoon (low) |

### AI-Assisted Scenario Generation Workflow

```
Problem Understanding (with real-world context)
     │
     ├── Context: "Delhi, winter, industrial pollution sources"
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│ AI Proposes Candidate Scenarios                             │
│                                                             │
│ Scenario A: "Add green belt in South Delhi"                 │
│   → actions: { mitigation_zones: [{x: 60, y: 20, ...}] }    │
│                                                             │
│ Scenario B: "Restrict vehicles in Connaught Place"          │
│   → actions: { source_reduction: [{x: 50, y: 50, -30%}] }   │
│                                                             │
│ Scenario C: "Relocate Anand Vihar industrial zone"          │
│   → actions: { sources: [{x: 45, y: 80, intensity: 0}] }    │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│ Algorithmic Expansion                                       │
│                                                             │
│ For each AI candidate:                                      │
│   • Generate variations (LHS around the candidate)          │
│   • Add boundary cases                                      │
│   • Ensure diversity                                        │
│                                                             │
│ Total: 50+ scenarios (AI-seeded + algorithmic expansion)    │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
Scenario Set (grounded in reality)
```

---

## 6. Enriched State and Context Flow

### The Problem

Currently, state is generic:
```
state = { "grid_size": 100, "diffusion_rate": 0.1, ... }
```

The simulation doesn't "know" it's simulating Delhi—it just sees numbers.

### The Solution

**Problem Understanding produces context that flows into:**

1. **State** — Initial conditions are populated with real-world data
2. **Context/Summary** — A summary object is passed to simulate() for awareness

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Problem Understanding Output                                │
│                                                             │
│ {                                                           │
│   "domain": "spatial/pollution",                            │
│   "subject": "Delhi, India",                                │
│   "context": {                                              │
│     "geography": { "bounds": [...], "grid_size": 200 },     │
│     "known_sources": [                                      │
│       { "name": "Anand Vihar", "x": 45, "y": 80 }           │
│     ],                                                      │
│     "seasonal_factors": { "season": "winter" },             │
│     "population_zones": [...]                               │
│   },                                                        │
│   "first_principles": { ... },                              │
│   "actions": [ ... ],                                       │
│   "constraints": [ ... ],                                   │
│   "summary": "Delhi is a megacity with severe winter..."    │
│ }                                                           │
└─────────────────────────────────────────────────────────────┘
          │
          │
    ┌─────┴─────┬─────────────────┐
    ▼           ▼                 ▼
┌────────┐ ┌─────────┐ ┌──────────────────┐
│ State  │ │ Actions │ │ Context/Summary  │
│        │ │ (for    │ │ (passed to       │
│ (init  │ │ scenario│ │ simulate())      │
│ conds) │ │ gen)    │ │                  │
└────────┘ └─────────┘ └──────────────────┘
    │           │                 │
    └───────────┴─────────────────┘
                    │
                    ▼
            ┌──────────────┐
            │  simulate()  │
            │              │
            │ Has access   │
            │ to state,    │
            │ actions, AND │
            │ context      │
            └──────────────┘
```

### Enriched State Example

**Before (generic):**
```json
{
  "grid_size": 100,
  "diffusion_rate": 0.1,
  "sources": []
}
```

**After (enriched from Problem Understanding):**
```json
{
  "grid_size": 200,
  "diffusion_rate": 0.08,
  "wind_x": 0.3,
  "wind_y": -0.1,
  "sources": [
    { "x": 45, "y": 80, "intensity": 0.9, "label": "Anand Vihar Industrial" },
    { "x": 50, "y": 50, "intensity": 0.7, "label": "ITO Traffic Hub" }
  ],
  "sensitive_zones": [
    { "x": 30, "y": 40, "type": "hospital", "label": "AIIMS" }
  ],
  "season": "winter",
  "context_summary": "Simulating winter pollution in Delhi with known industrial and traffic sources."
}
```

---

## 7. End-to-End Workflow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           USER QUESTION                                 │
│                                                                         │
│  "How to reduce pollution in Delhi?" or                                 │
│  "How to increase electricity generation of this generator?"            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. PROBLEM UNDERSTANDING (AI + First Principles)                        │
│                                                                         │
│    • Detect domain (spatial/pollution, energy/generator)                │
│    • Apply first principles (physics, equations, governing laws)        │
│    • Decompose into fundamental factors                                 │
│    • Derive actionable levers                                           │
│    • Identify constraints                                               │
│    • Gather real-world context (if subject is specific)                 │
│    • Generate list of unknowns                                          │
│                                                                         │
│    Output: ProblemUnderstanding + ClarificationQuestions                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. CLARIFICATION (Interactive)                                          │
│                                                                         │
│    • Present checklist of unanswered questions to user                  │
│    • User answers, skips, or accepts defaults                           │
│    • Log all answers and assumptions                                    │
│                                                                         │
│    Output: Enriched ProblemUnderstanding                                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. SCENARIO GENERATION (AI-Assisted + Algorithmic)                      │
│                                                                         │
│    • AI proposes candidate scenarios based on real-world context        │
│    • Algorithmic sampling expands around candidates                     │
│    • All scenarios grounded in Problem Understanding                    │
│                                                                         │
│    Output: Scenario set (50+ scenarios)                                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. ENRICHED STATE                                                       │
│                                                                         │
│    • Initial state populated from Problem Understanding                 │
│    • Real-world data (locations, sources, conditions)                   │
│    • Context summary attached                                           │
│                                                                         │
│    Output: State object + Context/Summary                               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 5. SIMULATION (Domain Pack)                                             │
│                                                                         │
│    • Domain pack receives: state, actions, context                      │
│    • Runs simulation logic (deterministic, code-only)                   │
│    • Returns OutcomeBundle with numeric results                         │
│                                                                         │
│    Output: Simulation outcomes (numbers from code, NOT AI)              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 6. SCORING & OPTIMIZATION                                               │
│                                                                         │
│    • Deterministic scoring (rubrics, benchmarks)                        │
│    • Bayesian / evolutionary optimization                               │
│    • Iterate until budget exhausted or convergence                      │
│                                                                         │
│    Output: Ranked solutions, Pareto front                               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 7. REPORT & EXPLANATION (AI)                                            │
│                                                                         │
│    • Summarize results in natural language                              │
│    • Link back to first principles analysis                             │
│    • Explain why top solutions work                                     │
│                                                                         │
│    Output: Human-readable report                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Data Structures

### ProblemUnderstanding

```python
class ProblemUnderstanding(BaseModel):
    """Output of first principles problem analysis."""
    
    # Domain and subject
    domain: str                          # e.g., "energy/generator", "spatial/pollution"
    subject: Optional[str]               # e.g., "Delhi", "AC synchronous generator"
    
    # Objective
    objective: str                       # e.g., "maximize electrical power output"
    objective_direction: str             # "maximize" | "minimize"
    
    # First principles analysis
    first_principles: FirstPrinciplesAnalysis
    
    # Derived actions and constraints
    actions: List[ActionSpec]
    constraints: List[ConstraintSpec]
    metrics: List[MetricSpec]
    
    # Real-world context (if applicable)
    context: Optional[RealWorldContext]
    
    # Summary for simulation
    summary: str
    
    # Unknowns that need clarification
    clarification_questions: List[ClarificationQuestion]


class FirstPrinciplesAnalysis(BaseModel):
    """First principles breakdown."""
    
    governing_equations: List[str]       # e.g., ["P = V × I", "V = N × dΦ/dt"]
    fundamental_factors: List[FundamentalFactor]
    assumptions: List[str]


class FundamentalFactor(BaseModel):
    """A factor that affects the outcome."""
    
    name: str                            # e.g., "magnetic_field_strength"
    description: str                     # e.g., "Strength of permanent magnets"
    effect: str                          # e.g., "Increases voltage proportionally"
    governing_principle: str             # e.g., "Faraday's Law"


class ClarificationQuestion(BaseModel):
    """A question to ask the user for clarification."""
    
    id: str
    category: str                        # "subject_specifics", "constraints", "goals", "context"
    question: str
    why_needed: str                      # Explains why this info matters
    options: Optional[List[str]]         # Multiple choice options, if applicable
    is_required: bool
    default_if_skipped: Optional[str]    # Default assumption if user skips


class RealWorldContext(BaseModel):
    """Real-world context for a specific subject."""
    
    geography: Optional[Dict[str, Any]]  # Bounds, coordinates, grid mapping
    known_entities: List[Dict[str, Any]] # Sources, zones, landmarks
    seasonal_factors: Optional[Dict[str, Any]]
    environmental_conditions: Optional[Dict[str, Any]]
    data_sources: List[str]              # Where this info came from
```

### EnrichedState

```python
class EnrichedState(BaseModel):
    """State enriched with real-world context."""
    
    # Domain pack state fields (varies by pack)
    # ... (defined by pack's state_schema)
    
    # Context fields (common)
    context_summary: str                 # Human-readable summary
    subject: Optional[str]               # What we're simulating
    season: Optional[str]                # Temporal context
    data_sources: List[str]              # Provenance of enrichment data
    assumptions: List[str]               # Assumptions made during enrichment
```

### ClarificationResponse

```python
class ClarificationResponse(BaseModel):
    """User's response to clarification questions."""
    
    answers: Dict[str, Any]              # question_id → answer
    skipped: List[str]                   # question_ids the user skipped
    defaults_applied: Dict[str, str]     # question_id → default used
```

---

## 9. Examples

### Example 1: Generator Question

**User Question:** "How to increase electricity generation of this generator?"

**First Principles Analysis:**

| Aspect | Analysis |
|--------|----------|
| Domain | energy/generator |
| Governing Equations | P = V × I, V = N × dΦ/dt |
| Fundamental Factors | Magnet strength, coil turns, RPM, wire resistance, cooling |
| Actionable Levers | Increase magnet strength, add turns, increase RPM, improve cooling |
| Constraints | Max RPM (mechanical), max temperature (thermal), budget (cost) |

**Clarification Questions:**

| # | Question | Why Needed |
|---|----------|------------|
| 1 | What type of generator? (AC/DC) | Different physics |
| 2 | Current power output? | Baseline for improvement |
| 3 | Current RPM? | Determines headroom |
| 4 | Budget constraints? | Limits material options |
| 5 | Size/weight limits? | Physical constraints |

---

### Example 2: Delhi Pollution Question

**User Question:** "How to reduce pollution in Delhi?"

**First Principles Analysis:**

| Aspect | Analysis |
|--------|----------|
| Domain | spatial/pollution |
| Subject | Delhi, India |
| Governing Equations | Diffusion equation, advection (wind), decay |
| Fundamental Factors | Source locations, source intensities, wind patterns, diffusion rate |
| Actionable Levers | Add mitigation zones, reduce source intensity, relocate sources |
| Constraints | Budget, land availability, political feasibility |

**Real-World Context:**

| Data | Value |
|------|-------|
| Known pollution hotspots | Anand Vihar, ITO, Okhla |
| Seasonal factors | Winter inversion → worse pollution |
| Wind patterns | NW winds in winter |
| Sensitive zones | AIIMS, schools, residential areas |

**AI-Proposed Scenarios:**

| Scenario | Description | Actions |
|----------|-------------|---------|
| A | Green belt in South Delhi | Add mitigation zone at (60, 20) |
| B | Vehicle restriction in Connaught Place | Reduce source at (50, 50) by 30% |
| C | Relocate Anand Vihar industrial | Remove source at (45, 80) |

---

## 10. Implementation Plan

### Phase 1: Enhanced Problem Understanding

| Task | Description | Components |
|------|-------------|------------|
| 1.1 | Create `ProblemUnderstanding` data structures | `services/orchestrator/models/problem_understanding.py` |
| 1.2 | Implement first principles analysis activity | `services/orchestrator/activities/problem_understanding.py` |
| 1.3 | Create AI prompt templates for first principles thinking | System prompts for domain analysis |
| 1.4 | Integrate with existing formalization | Extend `formalize_objectives` activity |

### Phase 2: Clarification Questions

| Task | Description | Components |
|------|-------------|------------|
| 2.1 | Create `ClarificationQuestion` data structures | Models for questions and responses |
| 2.2 | Implement question generation logic | Derive questions from unknowns |
| 2.3 | Add API endpoint for clarification flow | `POST /api/runs/{id}/clarify` |
| 2.4 | Update workflow to pause for clarification | Temporal workflow with human-in-the-loop |
| 2.5 | Update web UI for clarification | Checklist component in chat |

### Phase 3: AI-Assisted Scenario Generation

| Task | Description | Components |
|------|-------------|------------|
| 3.1 | Create scenario proposal activity | `services/orchestrator/activities/scenario_proposer.py` |
| 3.2 | Implement AI scenario generation | LLM proposes candidates based on context |
| 3.3 | Integrate with algorithmic expansion | Combine AI candidates + LHS/grid |
| 3.4 | Update scenario generation pipeline | Modify `generate_structured_scenarios` |

### Phase 4: Enriched State and Context

| Task | Description | Components |
|------|-------------|------------|
| 4.1 | Extend state schema to include context | Add `context_summary`, `subject`, etc. |
| 4.2 | Implement state enrichment logic | Populate state from ProblemUnderstanding |
| 4.3 | Update simulate() signature (optional) | Add context parameter |
| 4.4 | Update domain packs to use context | Packs can read context for awareness |

### Phase 5: Testing and Integration

| Task | Description | Components |
|------|-------------|------------|
| 5.1 | Unit tests for problem understanding | Test first principles analysis |
| 5.2 | Integration tests for clarification flow | Test human-in-the-loop workflow |
| 5.3 | E2E tests with real questions | Test full pipeline with examples |
| 5.4 | Update documentation | HOW_IT_WORKS.md, architecture.md |

---

## Design Principles (Preserved)

Throughout this enhancement, the following principles are **preserved**:

| Principle | How It's Preserved |
|-----------|--------------------|
| **Non-Negotiable Truth** | AI informs context and scenarios, but simulation code still produces all numbers |
| **Reproducibility** | AI-generated scenarios are captured in run spec; same spec → same scenarios |
| **Audit Trail** | All AI outputs (problem understanding, clarifications, proposed scenarios) are logged in run ledger |
| **Deterministic Scoring** | Scoring remains pure math; no AI in scoring |
| **Domain Pack Contract** | Contract unchanged; context is additive, not breaking |

---

## Summary

This document outlines an enhanced pipeline where:

1. **Problem Understanding uses first principles thinking** — AI deeply analyzes questions using fundamental laws and equations
2. **Clarification questions are generated** — AI identifies unknowns and asks the user before proceeding
3. **Scenario generation is AI-assisted** — AI proposes realistic scenarios grounded in real-world context
4. **State is enriched with context** — Simulation receives rich, contextual information about what it's simulating
5. **Trust is preserved** — All numbers still come from simulation code, not AI

The result is a system that **understands questions deeply**, **asks for missing information**, **generates meaningful scenarios**, and **simulates with awareness of real-world context**—while maintaining the trustworthiness and auditability that defines GSIP.
