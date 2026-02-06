"""GSIP Evidence Service."""
from .chunking import chunk_text
from .embeddings import get_embedding, get_embeddings_batch, init_embeddings
from .vector_store import VectorStore, vector_store
from .evidence_pack import (
    ChunkReference,
    EvidencePack,
    EvidencePackBuilder,
    EvidencePackStore,
    evidence_pack_store,
)
from .claims import (
    Claim,
    ClaimConflict,
    ClaimType,
    ConflictType,
    ClaimDB,
    ClaimExtractor,
    ClaimVerifier,
    UnitNormalizer,
    claim_db,
)

__all__ = [
    # Chunking
    "chunk_text",
    # Embeddings
    "get_embedding",
    "get_embeddings_batch",
    "init_embeddings",
    # Vector store
    "VectorStore",
    "vector_store",
    # Evidence packs
    "ChunkReference",
    "EvidencePack",
    "EvidencePackBuilder",
    "EvidencePackStore",
    "evidence_pack_store",
    # Claims
    "Claim",
    "ClaimConflict",
    "ClaimType",
    "ConflictType",
    "ClaimDB",
    "ClaimExtractor",
    "ClaimVerifier",
    "UnitNormalizer",
    "claim_db",
]
