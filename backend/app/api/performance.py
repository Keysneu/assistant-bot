"""Performance API endpoints for Gemma4/vLLM observability."""

from fastapi import APIRouter

from app.models.schema import PerformanceOverviewResponse
from app.services.performance_service import get_performance_overview

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("/overview", response_model=PerformanceOverviewResponse)
async def performance_overview() -> PerformanceOverviewResponse:
    """Get latest Gemma4 deployment performance summary."""
    return PerformanceOverviewResponse(**get_performance_overview())
