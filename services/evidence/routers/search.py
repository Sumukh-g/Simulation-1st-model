"""Search endpoints."""
from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..embeddings import get_embedding
from ..vector_store import vector_store

router = APIRouter()


class SearchResult(BaseModel):
    """Search result item."""
    chunk_id: str
    document_id: str
    content: str
    source: str
    score: float


class SearchResponse(BaseModel):
    """Search response."""
    query: str
    results: List[SearchResult]
    total: int


class SearchRequest(BaseModel):
    """Search request."""
    query: str
    limit: int = 10
    document_id: Optional[str] = None


@router.post("", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    Semantic search for relevant evidence.
    
    Uses vector similarity to find chunks matching the query.
    """
    # Generate query embedding
    query_embedding = get_embedding(request.query)
    
    # Build filter
    filter_expr = None
    if request.document_id:
        filter_expr = f'document_id == "{request.document_id}"'
    
    # Search
    try:
        hits = vector_store.search(
            query_embedding=query_embedding,
            limit=request.limit,
            filter_expr=filter_expr,
        )
    except Exception:
        # Return empty results on error
        hits = []
    
    results = [
        SearchResult(
            chunk_id=hit["id"],
            document_id=hit["document_id"],
            content=hit["content"],
            source=hit["source"],
            score=hit["score"],
        )
        for hit in hits
    ]
    
    return SearchResponse(
        query=request.query,
        results=results,
        total=len(results),
    )


@router.get("/similar/{chunk_id}")
async def find_similar(
    chunk_id: str,
    limit: int = Query(default=5, le=20),
):
    """Find chunks similar to a given chunk."""
    # Would retrieve the chunk's embedding and search
    # For now, return placeholder
    return {
        "chunk_id": chunk_id,
        "similar": [],
        "message": "Not yet implemented",
    }
