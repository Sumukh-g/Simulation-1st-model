"""Evidence Pack endpoints."""
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..embeddings import get_embedding
from ..evidence_pack import (
    EvidencePackBuilder,
    evidence_pack_store,
)
from ..vector_store import vector_store

router = APIRouter()


class CreatePackRequest(BaseModel):
    """Request to create an evidence pack."""

    run_id: str
    query: str
    limit: int = 10
    domain_tags: List[str] = Field(default_factory=list)
    document_ids: Optional[List[str]] = None


class PackResponse(BaseModel):
    """Evidence pack response."""

    pack_id: str
    run_id: str
    query: str
    total_chunks: int
    hash: str
    verified: bool


@router.post("", response_model=PackResponse)
async def create_evidence_pack(request: CreatePackRequest):
    """
    Create an immutable evidence pack from search results.

    1. Perform semantic search for the query
    2. Bundle results into an immutable pack
    3. Store and return pack ID
    """
    # Generate query embedding
    query_embedding = get_embedding(request.query)

    # Build filter if document IDs specified
    filter_expr = None
    if request.document_ids:
        doc_list = ", ".join(f'"{d}"' for d in request.document_ids)
        filter_expr = f"document_id in [{doc_list}]"

    # Search
    try:
        hits = vector_store.search(
            query_embedding=query_embedding,
            limit=request.limit,
            filter_expr=filter_expr,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")

    if not hits:
        raise HTTPException(status_code=404, detail="No matching evidence found")

    # Build pack
    builder = EvidencePackBuilder(request.run_id, request.query)
    builder.add_chunks_from_search(hits)
    builder.with_domain_tags(request.domain_tags)
    builder.with_retrieval_params({
        "limit": request.limit,
        "document_ids": request.document_ids,
    })

    pack = builder.build()

    # Store
    evidence_pack_store.store(pack)

    return PackResponse(
        pack_id=pack.id,
        run_id=pack.run_id,
        query=pack.query,
        total_chunks=pack.total_chunks,
        hash=pack.hash,
        verified=pack.verify_integrity(),
    )


@router.get("/{pack_id}")
async def get_evidence_pack(pack_id: str):
    """Get an evidence pack by ID."""
    pack = evidence_pack_store.get(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail=f"Pack {pack_id} not found")

    return pack


@router.get("/{pack_id}/verify")
async def verify_evidence_pack(pack_id: str):
    """Verify integrity of an evidence pack."""
    pack = evidence_pack_store.get(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail=f"Pack {pack_id} not found")

    is_valid = pack.verify_integrity()

    return {
        "pack_id": pack_id,
        "verified": is_valid,
        "hash": pack.hash,
    }


@router.get("/{pack_id}/citations")
async def get_pack_citations(pack_id: str):
    """Get citation list for an evidence pack."""
    pack = evidence_pack_store.get(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail=f"Pack {pack_id} not found")

    return {
        "pack_id": pack_id,
        "run_id": pack.run_id,
        "citations": pack.to_citation_list(),
    }


@router.get("/run/{run_id}")
async def list_packs_for_run(run_id: str):
    """List all evidence packs for a run."""
    packs = evidence_pack_store.list_for_run(run_id)

    return {
        "run_id": run_id,
        "count": len(packs),
        "packs": [
            {
                "pack_id": p.id,
                "query": p.query,
                "total_chunks": p.total_chunks,
                "created_at": p.created_at.isoformat(),
            }
            for p in packs
        ],
    }
