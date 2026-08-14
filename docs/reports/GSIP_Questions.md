# GSIP: More Questions
## Frequently Asked, Stakeholder, Due Diligence, and Discussion Questions

**Document version:** 1.0  
**Last updated:** February 2025

This document collects questions that stakeholders, investors, partners, and technical reviewers often ask about the General Simulation Intelligence Platform (GSIP). Use it for FAQs, due diligence, internal alignment, and discussion.

---

## Part A — Product and Value

### A.1 What is GSIP in one sentence?
A platform that turns natural-language questions into optimization results by running real simulations (not AI-invented numbers) and storing every result in an audit-ready ledger.

### A.2 Who is it for?
Organizations that need to answer “what if?” and “what’s best?” in complex domains (e.g. finance, policy, operations) and require trustworthy, reproducible numbers and full provenance for audit or compliance.

### A.3 Why not just use ChatGPT or another LLM?
General-purpose chatbots can invent plausible-looking statistics. GSIP uses AI only for understanding the question and explaining results; every numeric outcome is produced by simulation code and stored in the ledger, so numbers are computable and verifiable.

### A.4 What makes the numbers “trustworthy”?
Only domain-pack simulation code produces numeric results. Those results are persisted immediately, tagged with scenario hashes and seeds, and stored in the run ledger. Same inputs yield the same outputs (reproducibility). No LLM can overwrite or fabricate these values.

### A.5 What domains does it support today?
ToyPack (testing), FinancePack (portfolio backtesting), and SpatialPack (e.g. pollution/diffusion). More domains (e.g. healthcare, logistics, energy) are planned as additional domain packs.

### A.6 Can we add our own simulation logic?
Yes. You implement the domain pack contract (state schema, action schema, simulate, score, feasibility, cost_model) and register the pack. The rest of the pipeline (formalization, scenario generation, optimization, Judge, ledger) works with your pack.

### A.7 How long does a typical run take?
Depends on scenario count, fidelity mix, and hardware. With tens to low hundreds of scenarios and Ray workers, runs can complete in minutes to tens of minutes. Wall-time and scenario limits are configurable per run.

### A.8 Can we use our own data (e.g. historical returns, maps)?
Yes where the domain pack supports it. State and actions can carry your parameters; custom packs can read from your data stores. Evidence service can ingest your documents for context and citations.

---

## Part B — Technical

### B.1 Where does the “AI” run?
AI (e.g. LLM) is used only in optional steps: objective formalization (parsing the question) and post-hoc explanation. Simulation, scoring, and optimization are deterministic code (domain packs, Judge, Optimizer).

### B.2 How is reproducibility guaranteed?
Deterministic scenario hashes (SHA-256 of inputs), fixed seeds per scenario, and stored run spec and domain pack version. Re-running with the same run spec and seed policy reproduces the same scenario set and results (within floating-point tolerance where applicable).

### B.3 What if the formalizer misinterprets the question?
You can extend keyword sets and prompts, or use the optional LLM step. Future UX may allow editing objectives/constraints before the optimization loop. Today, running with a different prompt or domain pack is the main lever.

### B.4 How do you scale to many scenarios?
Sim Fabric uses Ray for distributed execution; workers run scenarios in parallel. Caching by scenario hash avoids re-running identical scenarios. Optimizer focuses the budget on promising regions.

### B.5 What’s in the “run ledger”?
PostgreSQL stores runs, scenarios, scenario_instances, metric_results, judge_scores, artifacts (with MinIO keys and checksums). Run spec, domain pack version, seeds, and hashes give full provenance.

### B.6 Is the system stateless?
No. Workflow state lives in Temporal; application state (runs, results) in PostgreSQL and MinIO. Redis is used for cache. The system is designed for durability and replay.

### B.7 How do you handle failures mid-run?
Temporal workflows and activities have retries and timeouts. Partial results are persisted as the run progresses. On failure, the run can be inspected and optionally restarted or replayed where supported.

### B.8 What about security and multi-tenancy?
JWT auth, RBAC (e.g. admin, analyst, viewer), tenant isolation at the data layer, and audit events for privileged actions. Multi-tenancy is assumed in design; isolation can be tightened for SaaS.

---

## Part C — Business and Market

### C.1 What’s the business model?
Platform can be licensed (on-prem or private cloud), offered as SaaS (subscription or usage-based), or extended with domain packs and professional services. Revenue can come from subscriptions, pack add-ons, and implementation/training.

### C.2 Who are the main competitors?
Generic AI assistants (no simulation guarantee); traditional simulation/optimization tools (manual setup, no question-driven UX); vertical tools (narrow domain, no unified platform). GSIP differentiates by combining natural language, simulation-only numerics, and full audit trail.

### C.3 What’s the pricing model?
Not fixed in product; can be tiered by runs/scenarios/seats, with premium tiers for more packs, SLA, and support. Usage-based pricing aligns cost with value.

### C.4 What’s the go-to-market strategy?
Options: land in one vertical (e.g. finance or policy), design-partner pilots, product-led growth with a free/low-cost tier, or enterprise-first sales. Messaging centers on “real simulations, full audit trail, no invented numbers.”

### C.5 What’s the revenue potential?
Depends on pricing, conversion, and market size. Architecture supports both SMB/team (volume) and enterprise (higher ACV, custom packs, compliance). Services add margin on top of platform.

### C.6 Is it open source?
Core pipeline and SDK can be open (open-core model); specific domain packs or enterprise features can remain proprietary. Full open source is an option to drive adoption; closed is an option for maximum control.

---

## Part D — Compliance and Risk

### D.1 Can we use this in regulated industries (e.g. finance)?
Designed for audit: ledger, hashes, seeds, versioning, RBAC, audit events. Sector-specific regulations may require additional controls or certifications; the architecture supports building those on top.

### D.2 How do you prevent “garbage in, garbage out”?
Formalization quality is improved via keywords and optional LLM; rubrics and benchmarks are versioned and sourced. Users (or admins) control domain pack choice and run config. Evidence service links reports to source chunks.

### D.3 What if a domain pack has a bug?
Bugs affect only that pack’s outcomes; they don’t let an LLM invent numbers. Versioning and run ledger allow identifying which pack version was used; replays help reproduce and fix issues.

### D.4 What about data residency and privacy?
Deployment can be on-prem or in a chosen cloud/region. Document ingestion (Evidence) and any PII are deployment-specific; architecture does not require sending sensitive text to third-party LLMs beyond optional formalization (configurable).

### D.5 How do you handle bias in objectives or rubrics?
Objectives and rubrics are explicit and versioned; bias is in the open. Best practice: document rationale for rubrics and benchmarks, review with domain experts, and use evidence citations in reports.

---

## Part E — Roadmap and Maturity

### E.1 What’s implemented today?
Core pipeline: API, Temporal workflow, formalization, scenario generation, Sim Fabric (Ray), Judge, Optimizer, Evidence, run ledger, web app (chat, workspace, SSE). Three domain packs (Toy, Finance, Spatial). Tests: smoke e2e, API, domain packs, evidence, ledger, optimizer, scoring, sim fabric.

### E.2 What’s next (product)?
Optional problem-understanding and candidate-solution steps; more domain packs (e.g. healthcare, logistics, energy); UI improvements (scenario compare, Pareto view, heatmaps); richer formalization (e.g. fine-tuned or better LLM use).

### E.3 What’s next (operations)?
Production hardening: observability (traces, dashboards), runbooks, managed services where appropriate; scaling and multi-tenancy tuning; security review and compliance alignment for target verticals.

### E.4 How do you decide quality “done”?
Definition of Done and Quality Gates (reproducibility, evidence, simulation, optimization, Judge, security, observability, UI) define “done” for features and releases. Tests and gates must pass before release.

### E.5 What are the main limitations today?
Keyword-based formalization can miss nuance; only three domain packs; no multi-user collaboration features; optional LLM formalization depends on external API. See research paper “Limitations and Future Work” for more.

---

## Part F — Stakeholder and Due Diligence

### F.1 Why will enterprises adopt this instead of building in-house?
Faster time-to-value (question → report), built-in audit trail, and no need to build formalization, scenario generation, optimization, and Judge from scratch. Custom packs extend rather than replace the platform.

### F.2 What’s the defensibility / moat?
Combination of: Non-Negotiable Truth architecture (trust), domain pack ecosystem (vertical depth), run ledger (compliance), and integration effort (workflows, Judge, Evidence). Execution and vertical focus deepen the moat.

### F.3 What could kill the product?
Failure to close quality gates and deliver trust; slow domain pack rollout; poor UX; strong “simulation + audit” offerings from large vendors. Mitigation: vertical focus, clear messaging, and continuous improvement of formalization and UX.

### F.4 What’s the team/skills need?
Product/engineering for platform and packs; domain experts for rubrics and benchmarks; DevOps for deployment and observability; optionally sales and customer success for enterprise.

### F.5 What would you do with more funding?
Accelerate domain packs and vertical depth; invest in formalization quality and UX (e.g. scenario compare, Pareto); production hardening and compliance; go-to-market (design partners, sales, marketing).

### F.6 How do you measure success?
Product: run completion rate, scenarios per run, time to first result, reproducibility pass rate. Business: active orgs, runs per month, MRR/ARR, conversion. Trust: audit usage, evidence linkage, compliance feedback.

### F.7 What’s the exit or long-term vision?
Could be: standalone category leader in “trustworthy AI-assisted decision support”; acquisition by a larger vendor (data/analytics, vertical software); or infrastructure that powers many vertical products. Vision: every high-stakes decision that needs simulation has a question-driven, auditable option.

### F.8 What’s the biggest open question?
Whether one or two verticals should be owned first (finance vs policy vs operations) and whether go-to-market should be product-led or enterprise-first. Answer depends on capacity and target customer.

---

## Part G — Discussion and Workshops

Use these for internal alignment or workshops:

1. **Trust:** What would it take for a compliance officer to approve GSIP for a regulated use case in your industry?  
2. **Pricing:** How would you price “runs per month” vs “seats” vs “scenarios” for your target segment?  
3. **Packs:** Which next domain pack would create the most value for your roadmap (healthcare, logistics, energy, other)?  
4. **Formalization:** How would you let users correct or refine objectives before the optimization loop without making the UI too complex?  
5. **Evidence:** How should reports cite evidence chunks so that auditors can trace claims to sources?  
6. **Open source:** What would you open-source first (e.g. SDK, one pack, full core) and what would stay closed?  
7. **Partners:** Which type of partner (consultancy, SI, vertical vendor) would best accelerate adoption in your target market?  
8. **Metrics:** What single metric would you use to judge “GSIP is working” in the first 12 months?

---

*End of Questions Document*
