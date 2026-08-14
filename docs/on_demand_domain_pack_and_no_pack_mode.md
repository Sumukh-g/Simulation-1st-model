# Final Plan: On-Demand Domain Pack Creation & No-Pack Mode

## Goal

Give the user two ways to start a run when a suitable domain pack may or may not exist:

1. **Domain pack path** — use an existing pack, or **create one** for this problem.
2. **No domain pack path** — proceed without selecting/creating a pack.

When creating a pack, do **not** invent one blindly. Build it by classifying the problem, comparing how similar problems are solved, listing candidate methods, then generating the pack from the chosen method.

---

## User-facing options

At run start, the UI offers:

| Option | Meaning |
|--------|---------|
| **Use existing domain pack** | Pick a registered pack (e.g. FinancePack, SpatialPack, user-authored). |
| **Create a domain pack for this problem** | Classify → similar methods → choose method → draft/register pack → run. |
| **No domain pack** | Skip pack selection; use AI-defined simulation/calculation for this run only. |

Suggested API field:

```text
simulation_mode: "domain_pack" | "create_pack" | "no_pack"
domain_pack: optional string   # required only for domain_pack
```

---

## Option A — Create domain pack (core process)

Triggered when the user chooses **Create a domain pack**, or when no matching pack exists and they opt to create one.

### Pipeline

```text
User problem
    │
    ▼
1. Classify problem type (within its domain; multi-label OK)
    │  e.g. finance/valuation, spatial/dispersion, energy/electromechanical
    ▼
2. Retrieve / propose how similar problems are solved
    │  Compare this problem to known problem classes and prior approaches
    ▼
3. List candidate methods (broad catalog)
    │  Example (stock valuation):
    │    • DCF
    │    • Trading comps / multiples
    │    • Residual income
    │    • Dividend discount
    │    • Monte Carlo / scenario valuation
    ▼
4. User selects a method (or accepts a recommended default)
    │
    ▼
5. Generate domain pack from the chosen method
    │    state_schema   — inputs the method needs
    │    action_schema  — levers the optimizer can vary
    │    simulate()     — deterministic implementation of the method
    │    score / metrics / feasibility / cost_model
    │    fidelity descriptor (e.g. TOY or REDUCED_ORDER until validated)
    ▼
6. Human ratify / confirm (recommended before trusting results)
    │
    ▼
7. Register pack (versioned) → continue normal GSIP run
       scenarios → simulate via pack → Judge → optimize → report
```

### Design rules for pack creation

- Classification answers: *what type of problem is this?*
- Method catalog answers: *what is used to solve similar problems?*
- The pack is derived from the **chosen method**, not from free-form hallucination of outcomes.
- All **result numbers** still come from pack `simulate()` code, not from the LLM asserting answers.
- New packs should be labelled honestly (e.g. `TOY` / `UNVALIDATED` until reviewed).
- Prefer **draft → user confirms → run** over silent auto-run.

### Example

**Prompt:** “Find the correct stock price for company X.”

1. Classify → `finance/valuation`
2. Similar methods → DCF, comps, residual income, …
3. User picks → DCF
4. System drafts a DCF pack (cash flows, WACC, growth as state; valuation metrics as outcomes)
5. User confirms critical inputs / assumptions
6. Pack registered → normal optimization/simulation loop

---

## Option B — No domain pack

Triggered when the user explicitly chooses **No domain pack**.

### Behavior

- `domain_pack` is not required.
- System produces an AI-defined simulation/calculation spec for this run.
- Scenarios and calculations execute in a **sandbox**.
- Downstream stages (Judge, aggregate, report) can stay the same **if** outcomes match the expected metric shape.
- Results must be clearly labelled **illustrative / experimental** (weaker trust than a ratified pack).

### When to use

- Exploration / prototyping
- One-off questions where authoring a pack is not worth it yet
- User explicitly accepts lower grounding

### When not to use as default

- Decisions that need auditability and reuse
- Anything presented as predictive without a real pack

---

## Option C — Use existing pack (unchanged)

Current behavior:

- User selects a registered pack.
- Formalize → scenarios → `pack.simulate()` → Judge → optimize → report.

---

## How the three options relate

```text
                    Start run
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
  Existing pack    Create pack       No pack
        │               │               │
        │         classify → methods     │
        │         → generate pack        │
        │               │               │
        └───────► pack.simulate() ◄─────┘
                        │         (sandbox AI spec)
                        ▼
              Judge / optimize / report
```

Create-pack **joins** the normal pack path after registration.  
No-pack is a **parallel** execution path.

---

## API / workflow sketch

### Start run

```json
{
  "prompt": "Find fair value for company X",
  "simulation_mode": "create_pack",
  "domain_pack": null,
  "config": { "maxScenarios": 50 }
}
```

or

```json
{
  "prompt": "Quick what-if without a pack",
  "simulation_mode": "no_pack",
  "domain_pack": null
}
```

or

```json
{
  "prompt": "Reduce pollution in the city center",
  "simulation_mode": "domain_pack",
  "domain_pack": "SpatialPack"
}
```

### Extra endpoints (create-pack flow)

- `POST /api/runs/{id}/classify` — problem classification result
- `GET  /api/runs/{id}/candidate-methods` — list of similar-problem methods
- `POST /api/runs/{id}/select-method` — user picks method
- `POST /api/runs/{id}/confirm-pack` — ratify drafted pack and continue
- For no-pack: no pack confirmation; optional ack that results are illustrative

### Workflow pauses

- Create-pack: pause after classification/method list and again after pack draft (human-in-the-loop).
- No-pack: optional single ack pause; then AI-spec → execute → Judge.

---

## Alignment with GSIP principles

| Principle | Create-pack | No-pack |
|-----------|-------------|---------|
| Numbers from code, not LLM prose | Yes (`simulate()`) | Only if sandboxed calc is code/spec execution, not free-form LLM numbers |
| Classification before solving | Yes (required) | Optional but recommended |
| Method catalog from similar problems | Yes (required) | Optional “suggested approaches” only |
| Human ratification | Strongly recommended | Soft warning / illustrative label |
| Reuse / versioning | Pack registered and reusable | Run-local only |

---

## Implementation phases (suggested)

| Phase | Deliverable | Difficulty |
|-------|-------------|------------|
| 1 | UI + API `simulation_mode` (`domain_pack` \| `create_pack` \| `no_pack`) | Easy–medium |
| 2 | Classifier + candidate-methods list (playbook / similar-problem catalog) | Medium |
| 3 | Human-in-loop select method + confirm | Medium |
| 4 | Pack generator from chosen method (schemas + `simulate` stub/implementation) | Hard |
| 5 | Register pack + resume normal workflow | Medium |
| 6 | No-pack sandboxed execution path + illustrative labelling | Medium–hard |
| 7 | Honest report: which mode, which method, fidelity/caveats | Medium |

---

## Non-goals / guardrails

- Do **not** silently invent a pack and present results as grounded.
- Do **not** let “no pack” be the default for high-stakes runs.
- Do **not** skip classification/method listing when in **create_pack** mode — that process *is* how the pack is created.
- Do **not** treat LLM-recalled inputs inside a new pack as measured facts (still subject to provenance/clarification when that layer lands).

---

## Success criteria

1. User can start a run with an existing pack, create a new pack, or choose no pack.
2. Create-pack always shows: problem class → list of similar solving methods → chosen method → generated pack.
3. Created packs can be registered and reused.
4. No-pack runs complete with clear “illustrative / no domain pack” labelling.
5. In pack modes, outcome numbers come from deterministic simulation code.

---

## One-line summary

**Either create a domain pack by classifying the problem and building it from methods used on similar problems, or explicitly run with no domain pack — never silently skip the choice.**
