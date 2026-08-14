"""Document ingestion endpoints."""
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..chunking import chunk_text
from ..embeddings import get_embeddings_batch
from ..vector_store import vector_store

router = APIRouter()


class IngestResponse(BaseModel):
    """Ingestion response."""
    document_id: str
    filename: str
    chunks_created: int
    status: str


def extract_text(file_content: bytes, content_type: str, filename: str) -> str:
    """Extract text from file."""
    if content_type == "text/plain" or filename.endswith(".txt"):
        return file_content.decode("utf-8", errors="ignore")
    
    elif content_type == "application/pdf" or filename.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(file_content))
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {e}")
    
    elif "wordprocessingml" in content_type or filename.endswith(".docx"):
        try:
            from docx import Document
            import io
            doc = Document(io.BytesIO(file_content))
            text = "\n".join([para.text for para in doc.paragraphs])
            return text
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse DOCX: {e}")
    
    elif content_type == "application/json" or filename.endswith(".json"):
        import json
        try:
            data = json.loads(file_content.decode("utf-8"))
            return json.dumps(data, indent=2)
        except (ValueError, UnicodeDecodeError):
            return file_content.decode("utf-8", errors="ignore")
    
    elif content_type == "text/csv" or filename.endswith(".csv"):
        return file_content.decode("utf-8", errors="ignore")
    
    else:
        # Try as plain text
        return file_content.decode("utf-8", errors="ignore")


@router.post("", response_model=IngestResponse)
async def ingest_document(
    file: UploadFile = File(...),
    domain_tags: str = Form(""),
    chunking_method: str = Form("sliding_window"),
):
    """
    Ingest a document into the evidence store.
    
    1. Extract text from document
    2. Chunk the text
    3. Generate embeddings
    4. Store in Milvus
    """
    document_id = str(uuid.uuid4())
    
    # Read file content
    content = await file.read()
    
    # Extract text
    text = extract_text(content, file.content_type, file.filename)
    
    if not text.strip():
        raise HTTPException(status_code=400, detail="No text content extracted")
    
    # Chunk text
    chunks = chunk_text(text, method=chunking_method)
    
    if not chunks:
        raise HTTPException(status_code=400, detail="No chunks generated")
    
    # Prepare chunk data
    chunk_data = []
    for i, chunk in enumerate(chunks):
        chunk_data.append({
            "id": f"{document_id}_{i}",
            "document_id": document_id,
            "content": chunk["content"],
            "source": file.filename,
            "chunk_index": i,
        })
    
    # Generate embeddings
    texts = [c["content"] for c in chunk_data]
    embeddings = get_embeddings_batch(texts)
    
    # Store in vector DB
    try:
        vector_store.insert(chunk_data, embeddings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store: {e}")
    
    return IngestResponse(
        document_id=document_id,
        filename=file.filename,
        chunks_created=len(chunks),
        status="completed",
    )


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    """Delete a document and its chunks."""
    try:
        count = vector_store.delete_document(document_id)
        return {"deleted": count, "document_id": document_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
