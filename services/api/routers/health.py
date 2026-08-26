"""Health check endpoints."""
from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def health():
    return {"status": "healthy", "service": "gsip-api"}


@router.get("/llm")
async def llm_health():
    """Report LLM configuration without ever exposing key values.

    Returns which providers have credentials configured so operators can verify
    their setup. Does not make network calls (use scripts/check_llm.py for that).
    """
    from services.common import llm

    return {
        "enabled": llm.is_enabled(),
        "configured_providers": llm.available_providers(),
    }
