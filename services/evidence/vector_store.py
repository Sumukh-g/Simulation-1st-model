"""Milvus vector store operations."""
import logging
from typing import Any, Dict, List, Optional

from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility,
)

from .config import settings

logger = logging.getLogger(__name__)


class VectorStore:
    """Milvus vector store for evidence retrieval."""
    
    def __init__(self):
        self._connected = False
        self._collection: Optional[Collection] = None
    
    def connect(self) -> bool:
        """Connect to Milvus."""
        try:
            connections.connect(
                alias="default",
                host=settings.MILVUS_HOST,
                port=settings.MILVUS_PORT,
            )
            self._connected = True
            logger.info(f"Connected to Milvus at {settings.MILVUS_HOST}:{settings.MILVUS_PORT}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            return False
    
    def ensure_collection(self) -> bool:
        """Ensure collection exists."""
        if not self._connected:
            self.connect()
        
        collection_name = settings.MILVUS_COLLECTION
        
        if utility.has_collection(collection_name):
            self._collection = Collection(collection_name)
            self._collection.load()
            return True
        
        # Create collection
        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=100),
            FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=500),
            FieldSchema(name="chunk_index", dtype=DataType.INT64),
            FieldSchema(
                name="embedding",
                dtype=DataType.FLOAT_VECTOR,
                dim=settings.EMBEDDING_DIMENSION,
            ),
        ]
        
        schema = CollectionSchema(
            fields=fields,
            description="GSIP Evidence Chunks",
        )
        
        self._collection = Collection(
            name=collection_name,
            schema=schema,
        )
        
        # Create index
        index_params = {
            "metric_type": "COSINE",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 128},
        }
        self._collection.create_index("embedding", index_params)
        self._collection.load()
        
        logger.info(f"Created collection: {collection_name}")
        return True
    
    def insert(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]],
    ) -> int:
        """Insert chunks with embeddings."""
        self.ensure_collection()
        
        data = [
            [c["id"] for c in chunks],
            [c["document_id"] for c in chunks],
            [c["content"][:65000] for c in chunks],  # Truncate if needed
            [c["source"] for c in chunks],
            [c["chunk_index"] for c in chunks],
            embeddings,
        ]
        
        self._collection.insert(data)
        self._collection.flush()
        
        return len(chunks)
    
    def search(
        self,
        query_embedding: List[float],
        limit: int = 10,
        filter_expr: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar chunks."""
        self.ensure_collection()
        
        search_params = {
            "metric_type": "COSINE",
            "params": {"nprobe": 10},
        }
        
        results = self._collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param=search_params,
            limit=limit,
            expr=filter_expr,
            output_fields=["id", "document_id", "content", "source", "chunk_index"],
        )
        
        hits = []
        for hit in results[0]:
            hits.append({
                "id": hit.entity.get("id"),
                "document_id": hit.entity.get("document_id"),
                "content": hit.entity.get("content"),
                "source": hit.entity.get("source"),
                "chunk_index": hit.entity.get("chunk_index"),
                "score": hit.score,
            })
        
        return hits
    
    def delete_document(self, document_id: str) -> int:
        """Delete all chunks for a document."""
        self.ensure_collection()
        
        expr = f'document_id == "{document_id}"'
        result = self._collection.delete(expr)
        
        return result.delete_count


# Global instance
vector_store = VectorStore()
