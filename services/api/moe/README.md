# GSIP Mixture of Experts (MoE) Committee

Structured expert committee for planning, analysis, and reporting.

## Key Principle

**Experts produce STRUCTURED JSON, not prose.**

The MoE committee helps with planning and explanation, but:
- Simulation results are ground truth
- LLMs propose and explain but don't invent data
- All outputs are structured and machine-readable

## Components

### Router

Routes tasks to appropriate experts based on:
- Task type (planning, analysis, critique, etc.)
- Stakes level (determines model tier)
- Complexity (determines if ensemble needed)

### Experts

| Expert | Description |
|--------|-------------|
| Planner | Creates structured plans for runs |
| Evidence Curator | Retrieves and validates evidence |
| Cause Modeler | Identifies causal relationships |
| Scenario Generator | Generates scenario variations |
| Math/Stats | Mathematical and statistical analysis |
| Critic | Identifies issues and weaknesses |
| Red Team | Adversarial analysis and risks |
| Judge Explainer | Explains scoring results |
| Report Writer | Generates structured reports |

### Arbitration Engine

Merges outputs from multiple experts:
- Consensus merge for assumptions and benchmarks
- Union + scoring for scenario ideas
- Tournament selection when simulation results are available

## Expert Contracts

Each expert has defined input/output schemas:

```python
class ExpertInput(BaseModel):
    task: str
    context: Dict[str, Any]
    evidence_refs: List[str]
    constraints: List[str]

class ExpertContract(BaseModel):
    expert_id: str
    output_type: str
    payload: Dict[str, Any]  # Structured data, NOT prose
    confidence: float
    assumptions: List[str]
    evidence_refs: List[str]
    risks: List[str]
    requires_escalation: bool
```

## Escalation Policy

The router can escalate based on:
- **Disagreement**: Experts disagree above threshold
- **Uncertainty**: Confidence is low
- **High Stakes**: Decision is critical

Escalation actions:
- Upgrade LLM tier
- Upgrade simulation fidelity
- Add more experts
- Require human review

## Usage

```python
from services.api.moe import MoECommittee, MoETask, TaskStage

committee = MoECommittee()
task = MoETask(task="Analyze portfolio risk", stage=TaskStage.STATS_ANALYSIS, stakes=0.8)
report = await committee.run(task)

# report.routing includes experts, model tier, and k-candidates
# report.arbitration contains consensus assumptions and scenario ranking
# report.escalation describes any required escalation actions
```
