"""Embedding generation."""
import logging
from typing import List, Optional

from .config import settings

logger = logging.getLogger(__name__)

_model = None


def init_embeddings():
    """Initialize the embedding model."""
    global _model
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
        logger.info(f"Loaded embedding model: {settings.EMBEDDING_MODEL}")
    except Exception as e:
        logger.warning(f"Failed to load embedding model: {e}")
        _model = None


def get_embedding(text: str) -> Optional[List[float]]:
    """Generate embedding for text."""
    if _model is None:
        # Fallback: return zero vector
        return [0.0] * settings.EMBEDDING_DIMENSION
    
    embedding = _model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for multiple texts."""
    if _model is None:
        return [[0.0] * settings.EMBEDDING_DIMENSION for _ in texts]
    
    embeddings = _model.encode(texts, convert_to_numpy=True)
    return [e.tolist() for e in embeddings]
