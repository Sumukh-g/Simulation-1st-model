"""
Deterministic hashing for the run ledger.

The ledger is append-only and must be replayable: the same run spec and seed
have to produce the same scenario identities and the same content hashes on any
machine, at any time. Everything here therefore goes through one canonical
JSON encoding — sorted keys, no incidental whitespace, no locale or
insertion-order sensitivity — before it reaches SHA-256.

Note on scope: `compute_scenario_hash` here identifies a scenario *within a
run* (it includes `run_id`), which is what the audit trail needs. That is a
different question from the simulation cache's key in
`services/sim_fabric/cache.py`, which deliberately excludes `run_id` so an
identical simulation can be reused across runs. Both are correct for their
purpose; they are not interchangeable.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping
from uuid import UUID

__all__ = [
    "canonical_json",
    "sha256_hex",
    "compute_scenario_hash",
    "compute_run_hash",
    "compute_artifact_checksum",
    "verify_hash",
]

HASH_ALGORITHM = "sha256"
HASH_HEX_LENGTH = 64


def _encode_unsupported(obj: Any) -> Any:
    """
    Coerce the handful of non-JSON types the ledger legitimately carries.

    Anything else raises: a silent `str(obj)` fallback would let object
    identity (memory addresses, reprs) leak into a hash and destroy
    reproducibility without ever failing a test.
    """
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (set, frozenset)):
        return sorted(obj, key=repr)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="strict")
    if hasattr(obj, "model_dump"):  # pydantic v2 model
        return obj.model_dump(mode="json")
    raise TypeError(
        f"{type(obj).__name__} is not canonically serialisable; "
        "convert it explicitly before hashing so the ledger stays reproducible"
    )


def canonical_json(payload: Any) -> str:
    """Serialise `payload` to the one encoding the ledger hashes."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_encode_unsupported,
    )


def sha256_hex(data: str | bytes) -> str:
    """Hex SHA-256 of a string (UTF-8) or raw bytes."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def compute_scenario_hash(
    run_id: str,
    input_state: Mapping[str, Any],
    actions: Mapping[str, Any],
    fidelity: str,
    seed: int,
    domain_pack_id: str | None = None,
    domain_pack_version: str | None = None,
) -> str:
    """
    Identity of one scenario inside a run.

    The pack id and version are optional but should be supplied whenever they
    are known: the same state, actions, fidelity and seed evaluated against a
    different pack version is a different scenario, and the ledger must be able
    to tell those apart when a run is replayed.
    """
    return sha256_hex(
        canonical_json(
            {
                "run_id": run_id,
                "input_state": input_state,
                "actions": actions,
                "fidelity": fidelity,
                "seed": seed,
                "domain_pack_id": domain_pack_id,
                "domain_pack_version": domain_pack_version,
            }
        )
    )


def compute_run_hash(spec: Mapping[str, Any]) -> str:
    """Identity of a run spec — same spec in, same hash out."""
    return sha256_hex(canonical_json(spec))


def compute_artifact_checksum(data: bytes) -> str:
    """Content checksum for a stored artifact."""
    return sha256_hex(data)


def verify_hash(payload: Any, expected_hash: str, kind: str = "run") -> bool:
    """
    Recompute a hash from `payload` and compare it to `expected_hash`.

    `kind` selects how the payload is interpreted: "run" for a run spec,
    "scenario" for a mapping of `compute_scenario_hash` keyword arguments,
    "artifact" for raw bytes.
    """
    if kind == "run":
        actual = compute_run_hash(payload)
    elif kind == "scenario":
        actual = compute_scenario_hash(**payload)
    elif kind == "artifact":
        actual = compute_artifact_checksum(payload)
    else:
        raise ValueError(
            f"unknown hash kind {kind!r}; expected 'run', 'scenario' or 'artifact'"
        )

    return secrets.compare_digest(actual, expected_hash)
