"""Health check and system status endpoints."""
import asyncio
from fastapi import APIRouter

from app.core.config import settings
from app.models.schema import HealthResponse
from app.services.llm_service import (
    is_model_loaded as llm_loaded,
    probe_vllm_connection,
)
from app.services.embedding_service import is_model_loaded as embedding_loaded
from app.services.rag_service import get_collection_stats

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint.

    Returns:
        System health status
    """
    try:
        stats = get_collection_stats()
        vector_db_ready = stats.get("count", 0) >= 0
    except Exception:
        vector_db_ready = False

    model_loaded = llm_loaded()
    if settings.LLM_PROVIDER == "vllm":
        try:
            model_loaded, _ = await asyncio.wait_for(
                asyncio.to_thread(probe_vllm_connection),
                timeout=settings.VLLM_PROBE_TIMEOUT_SECONDS + 1.0,
            )
        except asyncio.TimeoutError:
            model_loaded = False

    return HealthResponse(
        status="healthy" if all([model_loaded, vector_db_ready]) else "initializing",
        version="0.1.0",
        model_loaded=model_loaded,
        embedding_loaded=embedding_loaded(),
        vector_db_ready=vector_db_ready,
    )
