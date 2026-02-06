"""Claim DB: Atomic claims with provenance and verification."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class ClaimType(str, Enum):
    """Type of claim."""

    NUMERIC = "numeric"  # Quantitative fact
    CATEGORICAL = "categorical"  # Classification/category
    TEMPORAL = "temporal"  # Time-based claim
    RELATIONAL = "relational"  # Relationship between entities
    DEFINITIONAL = "definitional"  # Definition or description


class ConflictType(str, Enum):
    """Type of conflict between claims."""

    NUMERIC_DISCREPANCY = "numeric_discrepancy"
    UNIT_MISMATCH = "unit_mismatch"
    TEMPORAL_CONFLICT = "temporal_conflict"
    CATEGORICAL_CONFLICT = "categorical_conflict"
    FRESHNESS_CONFLICT = "freshness_conflict"


class Claim(BaseModel):
    """
    Atomic claim extracted from a document.

    Structured as a triple: (subject, predicate, object)
    with full provenance tracking.
    """

    id: str
    # Triple structure
    subject: str  # Entity the claim is about
    predicate: str  # Property/relationship
    object: str  # Value or related entity
    claim_type: ClaimType

    # Provenance
    source_document_id: str
    source_chunk_id: str
    source_text: str  # Original text excerpt
    source_name: str
    extraction_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # For temporal claims
    claim_date: Optional[datetime] = None  # When the claim was true
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None

    # Numeric claims
    numeric_value: Optional[float] = None
    unit: Optional[str] = None
    normalized_value: Optional[float] = None  # After unit normalization
    normalized_unit: Optional[str] = None

    # Confidence and verification
    confidence: float = 1.0  # 0-1, may be reduced by conflicts
    verified: bool = False
    conflicts: List[str] = Field(default_factory=list)  # Conflict IDs

    # Metadata
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ClaimConflict(BaseModel):
    """Conflict between two claims."""

    id: str
    claim_a_id: str
    claim_b_id: str
    conflict_type: ConflictType
    severity: float = 0.5  # 0-1, how severe the conflict is
    description: str
    resolution: Optional[str] = None  # How it was resolved
    resolved: bool = False

    # Details
    details: Dict[str, Any] = Field(default_factory=dict)


class UnitNormalizer:
    """Normalize units to standard forms."""

    # Unit conversion factors to base units
    CONVERSIONS = {
        # Length (to meters)
        "km": ("m", 1000.0),
        "m": ("m", 1.0),
        "cm": ("m", 0.01),
        "mm": ("m", 0.001),
        "mi": ("m", 1609.34),
        "miles": ("m", 1609.34),
        "ft": ("m", 0.3048),
        "feet": ("m", 0.3048),
        "in": ("m", 0.0254),
        "inches": ("m", 0.0254),
        # Mass (to kg)
        "kg": ("kg", 1.0),
        "g": ("kg", 0.001),
        "mg": ("kg", 0.000001),
        "lb": ("kg", 0.453592),
        "lbs": ("kg", 0.453592),
        "pounds": ("kg", 0.453592),
        "oz": ("kg", 0.0283495),
        "ton": ("kg", 907.185),
        "tonnes": ("kg", 1000.0),
        # Time (to seconds)
        "s": ("s", 1.0),
        "sec": ("s", 1.0),
        "seconds": ("s", 1.0),
        "min": ("s", 60.0),
        "minutes": ("s", 60.0),
        "hr": ("s", 3600.0),
        "hours": ("s", 3600.0),
        "days": ("s", 86400.0),
        "weeks": ("s", 604800.0),
        "years": ("s", 31536000.0),
        # Money (to USD, approximate)
        "usd": ("usd", 1.0),
        "$": ("usd", 1.0),
        "eur": ("usd", 1.1),
        "€": ("usd", 1.1),
        "gbp": ("usd", 1.25),
        "£": ("usd", 1.25),
        # Percentage
        "%": ("%", 1.0),
        "percent": ("%", 1.0),
        "pct": ("%", 1.0),
    }

    @classmethod
    def normalize(
        cls, value: float, unit: str
    ) -> Tuple[float, str]:
        """Normalize a value to base unit."""
        unit_lower = unit.lower().strip()

        if unit_lower in cls.CONVERSIONS:
            base_unit, factor = cls.CONVERSIONS[unit_lower]
            return value * factor, base_unit

        # Unknown unit, return as-is
        return value, unit

    @classmethod
    def are_comparable(cls, unit_a: str, unit_b: str) -> bool:
        """Check if two units are comparable."""
        unit_a_lower = unit_a.lower().strip()
        unit_b_lower = unit_b.lower().strip()

        if unit_a_lower == unit_b_lower:
            return True

        base_a = cls.CONVERSIONS.get(unit_a_lower, (unit_a_lower, 1.0))[0]
        base_b = cls.CONVERSIONS.get(unit_b_lower, (unit_b_lower, 1.0))[0]

        return base_a == base_b


class ClaimExtractor:
    """Extract atomic claims from text."""

    # Patterns for common claim types
    NUMERIC_PATTERNS = [
        r"(\w+(?:\s+\w+)*)\s+(?:is|was|are|were|equals?|=)\s+(\d+(?:\.\d+)?)\s*(\w+)?",
        r"(\w+(?:\s+\w+)*)\s*[:]\s*(\d+(?:\.\d+)?)\s*(\w+)?",
        r"(?:the\s+)?(\w+(?:\s+\w+)*)\s+of\s+(\d+(?:\.\d+)?)\s*(\w+)?",
    ]

    def __init__(self):
        self._claim_counter = 0

    def _generate_claim_id(self) -> str:
        """Generate unique claim ID."""
        self._claim_counter += 1
        return f"claim-{self._claim_counter:06d}"

    def extract_from_text(
        self,
        text: str,
        source_document_id: str,
        source_chunk_id: str,
        source_name: str,
    ) -> List[Claim]:
        """Extract claims from text."""
        claims = []

        # Extract numeric claims
        claims.extend(
            self._extract_numeric_claims(
                text, source_document_id, source_chunk_id, source_name
            )
        )

        return claims

    def _extract_numeric_claims(
        self,
        text: str,
        source_document_id: str,
        source_chunk_id: str,
        source_name: str,
    ) -> List[Claim]:
        """Extract numeric claims from text."""
        claims = []

        for pattern in self.NUMERIC_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                groups = match.groups()
                if len(groups) >= 2:
                    subject = groups[0].strip()
                    try:
                        value = float(groups[1])
                    except ValueError:
                        continue

                    unit = groups[2].strip() if len(groups) > 2 and groups[2] else ""

                    # Normalize
                    norm_value, norm_unit = UnitNormalizer.normalize(value, unit) if unit else (value, "")

                    claim = Claim(
                        id=self._generate_claim_id(),
                        subject=subject,
                        predicate="has_value",
                        object=str(value) + (" " + unit if unit else ""),
                        claim_type=ClaimType.NUMERIC,
                        source_document_id=source_document_id,
                        source_chunk_id=source_chunk_id,
                        source_text=match.group(0),
                        source_name=source_name,
                        numeric_value=value,
                        unit=unit if unit else None,
                        normalized_value=norm_value,
                        normalized_unit=norm_unit if norm_unit else None,
                    )
                    claims.append(claim)

        return claims

    def create_claim(
        self,
        subject: str,
        predicate: str,
        obj: str,
        claim_type: ClaimType,
        source_document_id: str,
        source_chunk_id: str,
        source_text: str,
        source_name: str,
        numeric_value: Optional[float] = None,
        unit: Optional[str] = None,
        claim_date: Optional[datetime] = None,
        confidence: float = 1.0,
    ) -> Claim:
        """Create a claim manually."""
        norm_value, norm_unit = None, None
        if numeric_value is not None and unit:
            norm_value, norm_unit = UnitNormalizer.normalize(numeric_value, unit)

        return Claim(
            id=self._generate_claim_id(),
            subject=subject,
            predicate=predicate,
            object=obj,
            claim_type=claim_type,
            source_document_id=source_document_id,
            source_chunk_id=source_chunk_id,
            source_text=source_text,
            source_name=source_name,
            numeric_value=numeric_value,
            unit=unit,
            normalized_value=norm_value,
            normalized_unit=norm_unit,
            claim_date=claim_date,
            confidence=confidence,
        )


class ClaimVerifier:
    """Verify claims for consistency and conflicts."""

    def __init__(
        self,
        numeric_tolerance: float = 0.1,  # 10% difference threshold
        recency_threshold_days: int = 365,  # Claims older than this may conflict
    ):
        self.numeric_tolerance = numeric_tolerance
        self.recency_threshold_days = recency_threshold_days
        self._conflict_counter = 0

    def _generate_conflict_id(self) -> str:
        """Generate unique conflict ID."""
        self._conflict_counter += 1
        return f"conflict-{self._conflict_counter:06d}"

    def verify_claims(
        self,
        claims: List[Claim],
    ) -> Tuple[List[Claim], List[ClaimConflict]]:
        """
        Verify a list of claims for consistency.

        Returns:
            (updated_claims, conflicts)
        """
        conflicts: List[ClaimConflict] = []

        # Group claims by subject
        by_subject: Dict[str, List[Claim]] = {}
        for claim in claims:
            key = claim.subject.lower()
            if key not in by_subject:
                by_subject[key] = []
            by_subject[key].append(claim)

        # Check each group for conflicts
        for subject, group in by_subject.items():
            if len(group) < 2:
                continue

            # Check all pairs
            for i, claim_a in enumerate(group):
                for claim_b in group[i + 1:]:
                    # Check for conflicts
                    conflict = self._check_pair(claim_a, claim_b)
                    if conflict:
                        conflicts.append(conflict)
                        # Update claim confidence
                        claim_a.conflicts.append(conflict.id)
                        claim_b.conflicts.append(conflict.id)
                        # Reduce confidence based on severity
                        claim_a.confidence *= (1 - conflict.severity * 0.3)
                        claim_b.confidence *= (1 - conflict.severity * 0.3)

        return claims, conflicts

    def _check_pair(
        self,
        claim_a: Claim,
        claim_b: Claim,
    ) -> Optional[ClaimConflict]:
        """Check a pair of claims for conflicts."""
        # Same subject, check predicate
        if claim_a.predicate != claim_b.predicate:
            return None

        # Numeric discrepancy
        if (
            claim_a.claim_type == ClaimType.NUMERIC
            and claim_b.claim_type == ClaimType.NUMERIC
        ):
            return self._check_numeric_conflict(claim_a, claim_b)

        # Freshness/recency conflict
        if claim_a.claim_date and claim_b.claim_date:
            return self._check_freshness_conflict(claim_a, claim_b)

        return None

    def _check_numeric_conflict(
        self,
        claim_a: Claim,
        claim_b: Claim,
    ) -> Optional[ClaimConflict]:
        """Check for numeric discrepancy."""
        # First check units
        if claim_a.unit and claim_b.unit:
            if not UnitNormalizer.are_comparable(claim_a.unit, claim_b.unit):
                return ClaimConflict(
                    id=self._generate_conflict_id(),
                    claim_a_id=claim_a.id,
                    claim_b_id=claim_b.id,
                    conflict_type=ConflictType.UNIT_MISMATCH,
                    severity=0.3,
                    description=f"Incompatible units: {claim_a.unit} vs {claim_b.unit}",
                    details={
                        "unit_a": claim_a.unit,
                        "unit_b": claim_b.unit,
                    },
                )

        # Compare normalized values
        val_a = claim_a.normalized_value or claim_a.numeric_value
        val_b = claim_b.normalized_value or claim_b.numeric_value

        if val_a is None or val_b is None:
            return None

        # Compute relative difference
        avg = (abs(val_a) + abs(val_b)) / 2
        if avg < 1e-10:
            return None

        diff = abs(val_a - val_b) / avg

        if diff > self.numeric_tolerance:
            severity = min(1.0, diff)  # Cap at 1.0
            return ClaimConflict(
                id=self._generate_conflict_id(),
                claim_a_id=claim_a.id,
                claim_b_id=claim_b.id,
                conflict_type=ConflictType.NUMERIC_DISCREPANCY,
                severity=severity,
                description=(
                    f"Numeric values differ by {diff*100:.1f}%: "
                    f"{val_a} vs {val_b}"
                ),
                details={
                    "value_a": val_a,
                    "value_b": val_b,
                    "difference": diff,
                    "source_a": claim_a.source_name,
                    "source_b": claim_b.source_name,
                },
            )

        return None

    def _check_freshness_conflict(
        self,
        claim_a: Claim,
        claim_b: Claim,
    ) -> Optional[ClaimConflict]:
        """Check for freshness/recency conflicts."""
        if not claim_a.claim_date or not claim_b.claim_date:
            return None

        # Order by date
        newer, older = (claim_a, claim_b) if claim_a.claim_date > claim_b.claim_date else (claim_b, claim_a)

        age_days = (newer.claim_date - older.claim_date).days

        if age_days > self.recency_threshold_days:
            # Check if values differ
            if newer.object != older.object:
                severity = min(1.0, age_days / (self.recency_threshold_days * 2))
                return ClaimConflict(
                    id=self._generate_conflict_id(),
                    claim_a_id=claim_a.id,
                    claim_b_id=claim_b.id,
                    conflict_type=ConflictType.FRESHNESS_CONFLICT,
                    severity=severity,
                    description=(
                        f"Claim from {newer.claim_date.date()} differs from "
                        f"older claim from {older.claim_date.date()} ({age_days} days older)"
                    ),
                    details={
                        "newer_date": newer.claim_date.isoformat(),
                        "older_date": older.claim_date.isoformat(),
                        "age_days": age_days,
                        "newer_value": newer.object,
                        "older_value": older.object,
                    },
                )

        return None

    def cross_source_consistency(
        self,
        claims: List[Claim],
    ) -> Dict[str, float]:
        """
        Compute cross-source consistency scores.

        Returns a dict mapping subject to consistency score.
        """
        by_subject: Dict[str, List[Claim]] = {}
        for claim in claims:
            key = claim.subject.lower()
            if key not in by_subject:
                by_subject[key] = []
            by_subject[key].append(claim)

        consistency: Dict[str, float] = {}

        for subject, group in by_subject.items():
            if len(group) < 2:
                consistency[subject] = 1.0
                continue

            # Count unique sources
            sources = set(c.source_document_id for c in group)

            # Count agreements vs conflicts
            agreements = 0
            total_pairs = 0

            for i, claim_a in enumerate(group):
                for claim_b in group[i + 1:]:
                    total_pairs += 1
                    # Check if they agree (no conflict)
                    if claim_a.source_document_id != claim_b.source_document_id:
                        conflict = self._check_pair(claim_a, claim_b)
                        if conflict is None:
                            agreements += 1

            if total_pairs > 0:
                consistency[subject] = agreements / total_pairs
            else:
                consistency[subject] = 1.0

        return consistency


class ClaimDB:
    """Database for storing and querying claims."""

    def __init__(self):
        self._claims: Dict[str, Claim] = {}
        self._conflicts: Dict[str, ClaimConflict] = {}
        self._by_subject: Dict[str, List[str]] = {}  # subject -> claim IDs
        self._by_document: Dict[str, List[str]] = {}  # doc ID -> claim IDs

        self.extractor = ClaimExtractor()
        self.verifier = ClaimVerifier()

    def add_claim(self, claim: Claim) -> str:
        """Add a claim to the database."""
        self._claims[claim.id] = claim

        # Index by subject
        subject_key = claim.subject.lower()
        if subject_key not in self._by_subject:
            self._by_subject[subject_key] = []
        self._by_subject[subject_key].append(claim.id)

        # Index by document
        if claim.source_document_id not in self._by_document:
            self._by_document[claim.source_document_id] = []
        self._by_document[claim.source_document_id].append(claim.id)

        return claim.id

    def add_conflict(self, conflict: ClaimConflict) -> str:
        """Add a conflict to the database."""
        self._conflicts[conflict.id] = conflict
        return conflict.id

    def get_claim(self, claim_id: str) -> Optional[Claim]:
        """Get a claim by ID."""
        return self._claims.get(claim_id)

    def get_claims_for_subject(self, subject: str) -> List[Claim]:
        """Get all claims about a subject."""
        subject_key = subject.lower()
        claim_ids = self._by_subject.get(subject_key, [])
        return [self._claims[cid] for cid in claim_ids if cid in self._claims]

    def get_claims_for_document(self, document_id: str) -> List[Claim]:
        """Get all claims from a document."""
        claim_ids = self._by_document.get(document_id, [])
        return [self._claims[cid] for cid in claim_ids if cid in self._claims]

    def get_conflicts_for_claim(self, claim_id: str) -> List[ClaimConflict]:
        """Get all conflicts involving a claim."""
        return [
            c for c in self._conflicts.values()
            if c.claim_a_id == claim_id or c.claim_b_id == claim_id
        ]

    def ingest_from_chunk(
        self,
        text: str,
        source_document_id: str,
        source_chunk_id: str,
        source_name: str,
    ) -> List[Claim]:
        """Extract and ingest claims from a chunk."""
        claims = self.extractor.extract_from_text(
            text, source_document_id, source_chunk_id, source_name
        )

        for claim in claims:
            self.add_claim(claim)

        return claims

    def verify_all(self) -> Tuple[int, int]:
        """
        Run verification on all claims.

        Returns:
            (total_claims, total_conflicts)
        """
        all_claims = list(self._claims.values())
        updated_claims, conflicts = self.verifier.verify_claims(all_claims)

        for conflict in conflicts:
            self.add_conflict(conflict)

        return len(all_claims), len(conflicts)

    def get_high_confidence_claims(
        self,
        min_confidence: float = 0.8,
    ) -> List[Claim]:
        """Get claims with high confidence."""
        return [
            c for c in self._claims.values()
            if c.confidence >= min_confidence
        ]

    def get_conflicting_claims(self) -> List[Claim]:
        """Get claims that have conflicts."""
        return [
            c for c in self._claims.values()
            if len(c.conflicts) > 0
        ]

    def cite_claim(self, claim_id: str) -> Dict[str, Any]:
        """
        Get citation info for a claim.

        Used by judge/experts to cite claims as evidence.
        """
        claim = self.get_claim(claim_id)
        if not claim:
            return {"error": f"Claim {claim_id} not found"}

        conflicts = self.get_conflicts_for_claim(claim_id)

        return {
            "claim_id": claim.id,
            "statement": f"{claim.subject} {claim.predicate} {claim.object}",
            "source": claim.source_name,
            "source_document_id": claim.source_document_id,
            "source_chunk_id": claim.source_chunk_id,
            "source_text": claim.source_text,
            "confidence": claim.confidence,
            "verified": claim.verified,
            "has_conflicts": len(conflicts) > 0,
            "conflict_count": len(conflicts),
            "claim_date": claim.claim_date.isoformat() if claim.claim_date else None,
        }

    def summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
        return {
            "total_claims": len(self._claims),
            "total_conflicts": len(self._conflicts),
            "claims_with_conflicts": len(self.get_conflicting_claims()),
            "high_confidence_claims": len(self.get_high_confidence_claims()),
            "subjects_tracked": len(self._by_subject),
            "documents_processed": len(self._by_document),
        }


# Global instance
claim_db = ClaimDB()
