# GSIP Evidence Service

Document ingestion, semantic search, and claim verification.

## Overview

The Evidence Service provides:
- **Doc Ingestion**: Upload, chunk, embed, store in vector index
- **Semantic Search**: Top-k chunk retrieval with similarity scores
- **Evidence Packs**: Immutable records of chunks used for runs
- **Claim DB**: Atomic claims with provenance and verification

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Evidence Service                          │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    Document Pipeline                     ││
│  │  Upload → Extract → Chunk → Embed → Store in Milvus    ││
│  └─────────────────────────────────────────────────────────┘│
│              │                                               │
│  ┌───────────┼───────────┬───────────┬───────────┐          │
│  ▼           ▼           ▼           ▼           ▼          │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐│
│ │Chunking │ │Embedding│ │Vector   │ │Evidence │ │Claim    ││
│ │Strategies│ │Model   │ │Store    │ │Packs    │ │DB       ││
│ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘│
│                                         │           │        │
│                                         │     ┌─────┴─────┐  │
│                                         │     │ Verifier  │  │
│                                         │     │ Checks    │  │
│                                         │     └───────────┘  │
└─────────────────────────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   ┌────────┐  ┌────────┐  ┌────────┐
   │ Milvus │  │  MinIO │  │ Claims │
   │ Vectors│  │  Files │  │ Store  │
   └────────┘  └────────┘  └────────┘
```

## Modules

### chunking.py
Text chunking strategies:
- `sliding_window`: Fixed size with overlap
- `paragraph`: Split by paragraphs
- `sentence`: Split by sentences

### embeddings.py
Embedding generation using sentence-transformers:
- Default model: `all-MiniLM-L6-v2` (384 dimensions)
- Batch embedding support

### vector_store.py
Milvus vector store operations:
- Collection management
- Insert chunks with embeddings
- Semantic search with filters

### evidence_pack.py
Immutable evidence records:
- `EvidencePack`: Frozen record with hash
- `EvidencePackBuilder`: Builder pattern
- `EvidencePackStore`: In-memory storage

### claims.py
Claim extraction and verification:
- `Claim`: Structured triple (subject, predicate, object)
- `ClaimExtractor`: Extract claims from text
- `ClaimVerifier`: Detect conflicts
- `ClaimDB`: Storage and query

## Usage

### Document Ingestion

```python
from services.evidence import chunk_text, get_embeddings_batch, vector_store

# Chunk text
chunks = chunk_text(document_text, method="paragraph")

# Generate embeddings
texts = [c["content"] for c in chunks]
embeddings = get_embeddings_batch(texts)

# Store in vector DB
chunk_data = [
    {
        "id": f"doc-123_{i}",
        "document_id": "doc-123",
        "content": c["content"],
        "source": "report.pdf",
        "chunk_index": i,
    }
    for i, c in enumerate(chunks)
]
vector_store.insert(chunk_data, embeddings)
```

### Semantic Search

```python
from services.evidence import get_embedding, vector_store

# Search for relevant chunks
query_embedding = get_embedding("What is the ROI forecast?")
results = vector_store.search(
    query_embedding=query_embedding,
    limit=10,
)

for hit in results:
    print(f"Score: {hit['score']:.3f}")
    print(f"Content: {hit['content'][:100]}...")
```

### Evidence Packs

```python
from services.evidence import EvidencePackBuilder, evidence_pack_store

# Create immutable pack from search results
builder = EvidencePackBuilder(run_id="run-001", query="ROI forecast")
builder.add_chunks_from_search(search_results)
builder.with_domain_tags(["finance", "forecast"])

pack = builder.build()
evidence_pack_store.store(pack)

# Verify integrity
assert pack.verify_integrity()

# Get citations
citations = pack.to_citation_list()
```

### Claim Extraction

```python
from services.evidence import claim_db, ClaimType

# Extract claims from text
claims = claim_db.ingest_from_chunk(
    text="The ROI is 15% annually",
    source_document_id="doc-123",
    source_chunk_id="doc-123_0",
    source_name="report.pdf",
)

# Create claim manually
claim = claim_db.extractor.create_claim(
    subject="ROI",
    predicate="equals",
    obj="15%",
    claim_type=ClaimType.NUMERIC,
    source_document_id="doc-123",
    source_chunk_id="doc-123_0",
    source_text="The ROI is 15% annually",
    source_name="report.pdf",
    numeric_value=15.0,
    unit="%",
)
claim_db.add_claim(claim)
```

### Claim Verification

```python
# Run all verification checks
total_claims, total_conflicts = claim_db.verify_all()

# Get conflicts for a claim
conflicts = claim_db.get_conflicts_for_claim("claim-000001")

# Check cross-source consistency
claims = claim_db.get_claims_for_subject("ROI")
consistency = claim_db.verifier.cross_source_consistency(claims)
print(f"Consistency: {consistency['roi']:.2%}")

# Get high-confidence claims
trusted = claim_db.get_high_confidence_claims(min_confidence=0.9)
```

### Citing Claims

```python
# Get citation info for judge/experts
citation = claim_db.cite_claim("claim-000001")

print(f"Statement: {citation['statement']}")
print(f"Source: {citation['source']}")
print(f"Confidence: {citation['confidence']}")
print(f"Conflicts: {citation['conflict_count']}")
```

## API Endpoints

### Ingestion
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ingest` | POST | Upload and ingest document |
| `/ingest/{doc_id}` | DELETE | Delete document |

### Search
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/search` | POST | Semantic search |
| `/search/similar/{chunk_id}` | GET | Find similar chunks |

### Evidence Packs
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/packs` | POST | Create evidence pack |
| `/packs/{pack_id}` | GET | Get pack by ID |
| `/packs/{pack_id}/verify` | GET | Verify pack integrity |
| `/packs/{pack_id}/citations` | GET | Get citation list |
| `/packs/run/{run_id}` | GET | List packs for run |

### Claims
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/claims/create` | POST | Create claim manually |
| `/claims/extract` | POST | Extract claims from text |
| `/claims/verify` | POST | Run verification checks |
| `/claims/{claim_id}` | GET | Get claim |
| `/claims/{claim_id}/cite` | GET | Get citation info |
| `/claims/subject/{subject}` | GET | Claims by subject |
| `/claims/document/{doc_id}` | GET | Claims by document |
| `/claims/conflicts` | GET | List all conflicts |
| `/claims/high-confidence` | GET | High confidence claims |
| `/claims/summary` | GET | Summary statistics |

## Verifier Checks

### Cross-Source Consistency
Compares claims from different sources about the same subject.
Reduces confidence when sources disagree.

### Unit Normalization
Converts units to standard forms for comparison:
- Length → meters
- Mass → kilograms
- Time → seconds
- Money → USD (approximate)

### Freshness/Recency Conflicts
Detects when newer claims contradict older claims.
Flags potential outdated information.

## Conflict Types

| Type | Description |
|------|-------------|
| `NUMERIC_DISCREPANCY` | Values differ beyond tolerance |
| `UNIT_MISMATCH` | Incompatible units |
| `TEMPORAL_CONFLICT` | Time-based contradiction |
| `CATEGORICAL_CONFLICT` | Classification mismatch |
| `FRESHNESS_CONFLICT` | Newer data contradicts older |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MILVUS_HOST` | `localhost` | Milvus host |
| `MILVUS_PORT` | `19530` | Milvus port |
| `MILVUS_COLLECTION` | `gsip_evidence` | Collection name |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embedding model |
| `EMBEDDING_DIMENSION` | `384` | Vector dimension |
| `CHUNK_SIZE` | `512` | Default chunk size |
| `CHUNK_OVERLAP` | `50` | Default overlap |

## Why Claims?

> This system is used to prevent "facts" from becoming vibe-based.

Claims provide:
1. **Provenance**: Every fact traces back to a source
2. **Verification**: Cross-source checks detect inconsistencies
3. **Confidence**: Quantified trust based on conflicts
4. **Citations**: Judge and experts can cite specific claims
5. **Auditability**: Full trail of what evidence was used
