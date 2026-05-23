"""LLC API router (GH#8251)."""

from fastapi import APIRouter

from .work_items import router as work_items_router

router = APIRouter(prefix="/llc", tags=["llc"])
router.include_router(work_items_router)


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "module": "llc"}
