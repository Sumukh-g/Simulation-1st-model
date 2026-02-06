"""Health check endpoints."""
from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def health():
    return {"status": "healthy", "service": "gsip-api"}
