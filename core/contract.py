"""
GSIP — core data contract (Phase 1)

Verbatim from the v2 grounded-architecture spec, §13 "Data structures".
This is the single source of truth for the provenance model, the gate,
classification, triage, clarification, fidelity, and outcome types.

Drop this into the workspace (e.g. core/) and use it as-is. It may be split
into the per-module layout from the brief (§6) — provenance.py, classification.py,
playbook.py, triage.py, clarification.py, fidelity.py, outcomes.py — but the
definitions must not drift from what is below.

Target: Python 3.12, pydantic v2.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Provenance ──────────────────────────────────────────────────────────────
class Provenance(str, Enum):
    USER_SUPPLIED = "user_supplied"   # grounded
    MEASURED = "measured"             # grounded
    RETRIEVED = "retrieved"           # grounded (attributable)
    COMPUTED = "computed"             # grounded (inherits weakest parent)
    DEFAULT = "default"               # ungrounded, declared
    LLM_RECALL = "llm_recall"         # ungrounded, unverified ← the floor


GROUNDED = {
    Provenance.USER_SUPPLIED,
    Provenance.MEASURED,
    Provenance.RETRIEVED,
    Provenance.COMPUTED,
}


class ParameterValue(BaseModel):
    """A value is never bare — it carries origin and uncertainty."""
    name: str
    value: Any
    provenance: Provenance
    source_id: Optional[str] = None          # dataset/API/sensor id for RETRIEVED/MEASURED
    uncertainty: Optional[float] = None       # std / half-width; wide default if ungrounded
    parents: list[str] = Field(default_factory=list)  # for COMPUTED: names of inputs it derives from
    notes: Optional[str] = None


# ─── Classification & playbooks ──────────────────────────────────────────────
class ProblemTag(BaseModel):
    type: str            # e.g. "spatial/dispersion"
    confidence: float    # calibrated


class ProblemClassification(BaseModel):
    tags: list[ProblemTag]          # multi-label, ranked
    abstained: bool = False         # open-set: no validated frame
    generic_mode: bool = False      # proceed generically with heightened flags


class Playbook(BaseModel):
    problem_type: str
    version: str                              # curated + versioned; human-ratified
    required_factors: list[str]
    characteristic_questions: list[str]
    candidate_models: list[str]               # domain packs applicable to this class
    sensitivity_priors: dict[str, float]      # factor → prior criticality
    known_pitfalls: list[str]
    applicability_bounds: list[str]


# ─── Triage ──────────────────────────────────────────────────────────────────
class Criticality(str, Enum):
    CRITICAL = "critical"
    MODERATE = "moderate"
    LOW = "low"


class ParameterCriticality(BaseModel):
    name: str
    criticality: Criticality
    sensitivity: float    # empirical (Morris) or prior
    source: str           # "morris_screening" | "playbook_prior"


class TriageResult(BaseModel):
    ranked: list[ParameterCriticality]


# ─── Clarification ───────────────────────────────────────────────────────────
class ClarificationQuestion(BaseModel):
    id: str
    parameter: str                          # which value this grounds
    question: str
    why_needed: str
    produces_provenance: Provenance          # what grounding this yields
    options: Optional[list[str]] = None
    is_required: bool                        # true if the parameter is CRITICAL
    default_if_skipped: Optional[Any] = None


# ─── Domain-pack fidelity ────────────────────────────────────────────────────
class FidelityTier(str, Enum):
    TOY = "toy"
    REDUCED_ORDER = "reduced_order"
    VALIDATED = "validated"
    CALIBRATED = "calibrated"


class ValidationStatus(str, Enum):
    UNVALIDATED = "unvalidated"
    BACKTESTED = "backtested"
    EXPERT_REVIEWED = "expert_reviewed"
    GROUND_TRUTH_CALIBRATED = "ground_truth_calibrated"


class DomainPackFidelity(BaseModel):
    fidelity_tier: FidelityTier
    validation_status: ValidationStatus
    applicability_bounds: list[str]
    known_limitations: list[str]
    reference: Optional[str] = None

    @property
    def is_predictive(self) -> bool:
        return self.fidelity_tier in {FidelityTier.VALIDATED, FidelityTier.CALIBRATED}


# ─── The gate ────────────────────────────────────────────────────────────────
class GateVerdict(str, Enum):
    RUN = "run"
    FLAG = "flag"
    BLOCK = "block"


class ProvenanceGateDecision(BaseModel):
    parameter: str
    criticality: Criticality
    provenance: Provenance
    verdict: GateVerdict
    action: Optional[str] = None    # e.g. "trigger_clarification:q3"
    override: bool = False          # true if user forced a blocked run


def gate(pc: ParameterCriticality, pv: ParameterValue) -> ProvenanceGateDecision:
    """
    Combines criticality (how much a parameter moves the answer) with
    provenance (how well-grounded it is) → RUN / FLAG / BLOCK.

    The single rule that matters: a decision-critical parameter may never
    silently take an LLM-recalled value.
    """
    grounded = pv.provenance in GROUNDED

    if pc.criticality == Criticality.CRITICAL:
        if grounded:
            verdict = GateVerdict.RUN
        elif pv.provenance == Provenance.DEFAULT:
            verdict = GateVerdict.FLAG
        else:  # LLM_RECALL
            verdict = GateVerdict.BLOCK
    elif pc.criticality == Criticality.MODERATE:
        verdict = (
            GateVerdict.RUN
            if grounded or pv.provenance == Provenance.DEFAULT
            else GateVerdict.FLAG
        )
    else:  # LOW
        verdict = GateVerdict.RUN

    return ProvenanceGateDecision(
        parameter=pc.name,
        criticality=pc.criticality,
        provenance=pv.provenance,
        verdict=verdict,
    )


# ─── Enriched state & outcomes ───────────────────────────────────────────────
class EnrichedState(BaseModel):
    values: dict[str, ParameterValue]   # every field carries provenance
    subject: Optional[str] = None
    context_summary: str
    assumptions: list[str]


class OutcomeBundle(BaseModel):
    metrics: dict[str, float]
    uncertainty: dict[str, float]       # per-metric band
    fidelity: DomainPackFidelity        # travels WITH the numbers


class ConfidenceReport(BaseModel):
    fidelity: DomainPackFidelity
    grounded_critical: list[str]
    ungrounded_critical: list[str]      # non-empty ⇒ result is caveated/illustrative
    overrides: list[str]
    output_bands: dict[str, float]
    verdict: str                        # "predictive" | "illustrative" | "blocked"
