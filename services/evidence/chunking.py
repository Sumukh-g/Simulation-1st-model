"""Document chunking strategies."""
from typing import List, Dict, Any
from .config import settings


def chunk_text(
    text: str,
    chunk_size: int = None,
    overlap: int = None,
    method: str = "sliding_window",
) -> List[Dict[str, Any]]:
    """
    Chunk text into smaller pieces.
    
    Args:
        text: Text to chunk
        chunk_size: Maximum chunk size in characters
        overlap: Overlap between chunks
        method: Chunking method ('sliding_window', 'paragraph', 'sentence')
    
    Returns:
        List of chunk dictionaries with content and metadata
    """
    chunk_size = chunk_size or settings.CHUNK_SIZE
    overlap = overlap or settings.CHUNK_OVERLAP
    
    if method == "sliding_window":
        return _sliding_window_chunk(text, chunk_size, overlap)
    elif method == "paragraph":
        return _paragraph_chunk(text, chunk_size)
    elif method == "sentence":
        return _sentence_chunk(text, chunk_size)
    else:
        return _sliding_window_chunk(text, chunk_size, overlap)


def _sliding_window_chunk(
    text: str,
    chunk_size: int,
    overlap: int,
) -> List[Dict[str, Any]]:
    """Sliding window chunking."""
    chunks = []
    start = 0
    chunk_id = 0
    
    while start < len(text):
        end = start + chunk_size
        chunk_text = text[start:end]
        
        # Try to break at word boundary
        if end < len(text):
            last_space = chunk_text.rfind(' ')
            if last_space > chunk_size // 2:
                end = start + last_space
                chunk_text = text[start:end]
        
        chunks.append({
            "chunk_id": chunk_id,
            "content": chunk_text.strip(),
            "start_char": start,
            "end_char": end,
            "method": "sliding_window",
        })
        
        chunk_id += 1
        start = end - overlap
    
    return chunks


def _paragraph_chunk(text: str, max_size: int) -> List[Dict[str, Any]]:
    """Chunk by paragraphs."""
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = ""
    chunk_id = 0
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        if len(current_chunk) + len(para) + 2 <= max_size:
            current_chunk += ("\n\n" if current_chunk else "") + para
        else:
            if current_chunk:
                chunks.append({
                    "chunk_id": chunk_id,
                    "content": current_chunk,
                    "method": "paragraph",
                })
                chunk_id += 1
            current_chunk = para
    
    if current_chunk:
        chunks.append({
            "chunk_id": chunk_id,
            "content": current_chunk,
            "method": "paragraph",
        })
    
    return chunks


def _sentence_chunk(text: str, max_size: int) -> List[Dict[str, Any]]:
    """Chunk by sentences."""
    # Simple sentence splitting
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    chunks = []
    current_chunk = ""
    chunk_id = 0
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        if len(current_chunk) + len(sentence) + 1 <= max_size:
            current_chunk += (" " if current_chunk else "") + sentence
        else:
            if current_chunk:
                chunks.append({
                    "chunk_id": chunk_id,
                    "content": current_chunk,
                    "method": "sentence",
                })
                chunk_id += 1
            current_chunk = sentence
    
    if current_chunk:
        chunks.append({
            "chunk_id": chunk_id,
            "content": current_chunk,
            "method": "sentence",
        })
    
    return chunks
