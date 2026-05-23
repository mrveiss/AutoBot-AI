"""LLC API router (GH#8251)."""

from fastapi import APIRouter

from .goals import router as goals_router

router = APIRouter(prefix="/llc", tags=["llc"])
router.include_router(goals_router)


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "module": "llc"}
