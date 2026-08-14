"""
GSIP core — the domain-agnostic trust layer.

`contract.py` holds the v2 grounded-architecture data contract verbatim and is
treated as frozen: Phase 1 splits it into the module layout from the brief §6
(provenance, classification, playbook, triage, clarification, fidelity,
outcomes, ledger) without letting the definitions drift.

Nothing in this package may contain domain knowledge. Domain expertise lives
only in packs.
"""
