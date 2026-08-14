"""Claim DB endpoints."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..claims import (
    ClaimType,
    claim_db,
)

router = APIRouter()


class CreateClaimRequest(BaseModel):
    """Request to create a claim manually."""

    subject: str
    predicate: str
    object: str
    claim_type: ClaimType
    source_document_id: str
    source_chunk_id: str
    source_text: str
    source_name: str
    numeric_value: Optional[float] = None
    unit: Optional[str] = None
    claim_date: Optional[datetime] = None
    confidence: float = 1.0


class ExtractClaimsRequest(BaseModel):
    """Request to extract claims from text."""

    text: str
    source_document_id: str
    source_chunk_id: str
    source_name: str


class VerifyRequest(BaseModel):
    """Request to verify claims."""

    claim_ids: Optional[List[str]] = None  # Empty = verify all


class CitationRequest(BaseModel):
    """Request to get citation for a claim."""

    claim_id: str


@router.post("/create")
async def create_claim(request: CreateClaimRequest):
    """Create a claim manually."""
    claim = claim_db.extractor.create_claim(
        subject=request.subject,
        predicate=request.predicate,
        obj=request.object,
        claim_type=request.claim_type,
        source_document_id=request.source_document_id,
        source_chunk_id=request.source_chunk_id,
        source_text=request.source_text,
        source_name=request.source_name,
        numeric_value=request.numeric_value,
        unit=request.unit,
        claim_date=request.claim_date,
        confidence=request.confidence,
    )

    claim_db.add_claim(claim)

    return {"claim_id": claim.id, "status": "created"}


@router.post("/extract")
async def extract_claims(request: ExtractClaimsRequest):
    """Extract claims from text automatically."""
    claims = claim_db.ingest_from_chunk(
        text=request.text,
        source_document_id=request.source_document_id,
        source_chunk_id=request.source_chunk_id,
        source_name=request.source_name,
    )

    return {
        "claims_extracted": len(claims),
        "claim_ids": [c.id for c in claims],
        "claims": [
            {
                "id": c.id,
                "subject": c.subject,
                "predicate": c.predicate,
                "object": c.object,
                "confidence": c.confidence,
            }
            for c in claims
        ],
    }


@router.post("/verify")
async def verify_claims(request: VerifyRequest = None):
    """
    Run verification checks on claims.

    Checks:
    - Cross-source consistency
    - Unit normalization
    - Freshness/recency conflicts
    """
    total_claims, total_conflicts = claim_db.verify_all()

    return {
        "total_claims_checked": total_claims,
        "total_conflicts_found": total_conflicts,
        "summary": claim_db.summary(),
    }


@router.get("/{claim_id}")
async def get_claim(claim_id: str):
    """Get a claim by ID."""
    claim = claim_db.get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")

    conflicts = claim_db.get_conflicts_for_claim(claim_id)

    return {
        "claim": claim,
        "conflicts": conflicts,
    }


@router.get("/{claim_id}/cite")
async def cite_claim(claim_id: str):
    """Get citation info for a claim."""
    citation = claim_db.cite_claim(claim_id)

    if "error" in citation:
        raise HTTPException(status_code=404, detail=citation["error"])

    return citation


@router.get("/subject/{subject}")
async def get_claims_by_subject(subject: str):
    """Get all claims about a subject."""
    claims = claim_db.get_claims_for_subject(subject)

    return {
        "subject": subject,
        "count": len(claims),
        "claims": claims,
    }


@router.get("/document/{document_id}")
async def get_claims_by_document(document_id: str):
    """Get all claims from a document."""
    claims = claim_db.get_claims_for_document(document_id)

    return {
        "document_id": document_id,
        "count": len(claims),
        "claims": claims,
    }


@router.get("/conflicts")
async def list_conflicts():
    """List all conflicts."""
    conflicts = list(claim_db._conflicts.values())

    return {
        "count": len(conflicts),
        "conflicts": [
            {
                "id": c.id,
                "type": c.conflict_type.value,
                "severity": c.severity,
                "description": c.description,
                "claim_a_id": c.claim_a_id,
                "claim_b_id": c.claim_b_id,
                "resolved": c.resolved,
            }
            for c in conflicts
        ],
    }


@router.get("/high-confidence")
async def get_high_confidence_claims(min_confidence: float = 0.8):
    """Get claims with high confidence."""
    claims = claim_db.get_high_confidence_claims(min_confidence)

    return {
        "min_confidence": min_confidence,
        "count": len(claims),
        "claims": [
            {
                "id": c.id,
                "subject": c.subject,
                "predicate": c.predicate,
                "object": c.object,
                "confidence": c.confidence,
                "source": c.source_name,
            }
            for c in claims
        ],
    }


@router.get("/summary")
async def get_claims_summary():
    """Get summary statistics of the claim database."""
    return claim_db.summary()


@router.get("/consistency/{subject}")
async def get_consistency_for_subject(subject: str):
    """Get cross-source consistency score for a subject."""
    claims = claim_db.get_claims_for_subject(subject)
    consistency = claim_db.verifier.cross_source_consistency(claims)

    return {
        "subject": subject,
        "claim_count": len(claims),
        "consistency_score": consistency.get(subject.lower(), 1.0),
        "sources": list(set(c.source_name for c in claims)),
    }
