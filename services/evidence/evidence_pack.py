"""EvidencePack: Immutable record of retrieved chunks used for a run."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChunkReference(BaseModel):
    """Reference to a chunk in the evidence pack."""

    chunk_id: str
    document_id: str
    source: str
    content: str
    score: float
    chunk_index: int = 0


class EvidencePack(BaseModel):
    """
    Immutable record of evidence chunks used for a run.

    Once created, an EvidencePack cannot be modified.
    All simulation runs reference their evidence pack by ID.
    """

    id: str
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    query: str  # Original retrieval query
    chunks: List[ChunkReference] = Field(default_factory=list)
    total_chunks: int = 0
    hash: str = ""  # Integrity hash

    # Metadata
    domain_tags: List[str] = Field(default_factory=list)
    retrieval_params: Dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        """Compute hash after initialization."""
        if not self.hash:
            self.hash = self._compute_hash()
        self.total_chunks = len(self.chunks)

    def _compute_hash(self) -> str:
        """Compute integrity hash of pack contents."""
        data = {
            "run_id": self.run_id,
            "query": self.query,
            "chunks": [c.model_dump() for c in self.chunks],
        }
        encoded = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def verify_integrity(self) -> bool:
        """Verify pack integrity by recomputing hash."""
        return self._compute_hash() == self.hash

    def get_chunk_ids(self) -> List[str]:
        """Get list of chunk IDs in pack."""
        return [c.chunk_id for c in self.chunks]

    def get_document_ids(self) -> List[str]:
        """Get unique document IDs referenced."""
        return list(set(c.document_id for c in self.chunks))

    def to_citation_list(self) -> List[Dict[str, Any]]:
        """Generate citation list for reporting."""
        citations = []
        for i, chunk in enumerate(self.chunks):
            citations.append({
                "index": i + 1,
                "source": chunk.source,
                "document_id": chunk.document_id,
                "chunk_id": chunk.chunk_id,
                "relevance_score": chunk.score,
                "excerpt": chunk.content[:200] + "..." if len(chunk.content) > 200 else chunk.content,
            })
        return citations


class EvidencePackBuilder:
    """Builder for creating EvidencePacks."""

    def __init__(self, run_id: str, query: str):
        self.run_id = run_id
        self.query = query
        self.chunks: List[ChunkReference] = []
        self.domain_tags: List[str] = []
        self.retrieval_params: Dict[str, Any] = {}

    def add_chunk(
        self,
        chunk_id: str,
        document_id: str,
        source: str,
        content: str,
        score: float,
        chunk_index: int = 0,
    ) -> "EvidencePackBuilder":
        """Add a chunk to the pack."""
        self.chunks.append(
            ChunkReference(
                chunk_id=chunk_id,
                document_id=document_id,
                source=source,
                content=content,
                score=score,
                chunk_index=chunk_index,
            )
        )
        return self

    def add_chunks_from_search(
        self,
        search_results: List[Dict[str, Any]],
    ) -> "EvidencePackBuilder":
        """Add chunks from search results."""
        for result in search_results:
            self.add_chunk(
                chunk_id=result.get("id", result.get("chunk_id", "")),
                document_id=result.get("document_id", ""),
                source=result.get("source", ""),
                content=result.get("content", ""),
                score=result.get("score", 0.0),
                chunk_index=result.get("chunk_index", 0),
            )
        return self

    def with_domain_tags(self, tags: List[str]) -> "EvidencePackBuilder":
        """Set domain tags."""
        self.domain_tags = tags
        return self

    def with_retrieval_params(self, params: Dict[str, Any]) -> "EvidencePackBuilder":
        """Set retrieval parameters."""
        self.retrieval_params = params
        return self

    def build(self) -> EvidencePack:
        """Build the immutable EvidencePack."""
        pack_id = hashlib.sha256(
            f"{self.run_id}:{self.query}:{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:16]

        return EvidencePack(
            id=f"ep-{pack_id}",
            run_id=self.run_id,
            query=self.query,
            chunks=self.chunks,
            domain_tags=self.domain_tags,
            retrieval_params=self.retrieval_params,
        )


class EvidencePackStore:
    """Storage for EvidencePacks."""

    def __init__(self):
        self._packs: Dict[str, EvidencePack] = {}

    def store(self, pack: EvidencePack) -> str:
        """Store an evidence pack."""
        self._packs[pack.id] = pack
        return pack.id

    def get(self, pack_id: str) -> Optional[EvidencePack]:
        """Retrieve an evidence pack."""
        return self._packs.get(pack_id)

    def list_for_run(self, run_id: str) -> List[EvidencePack]:
        """List all packs for a run."""
        return [p for p in self._packs.values() if p.run_id == run_id]

    def verify(self, pack_id: str) -> bool:
        """Verify integrity of a stored pack."""
        pack = self.get(pack_id)
        if not pack:
            return False
        return pack.verify_integrity()


# Global store
evidence_pack_store = EvidencePackStore()
