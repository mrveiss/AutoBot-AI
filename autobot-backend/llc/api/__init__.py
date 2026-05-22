"""LLC API router (GH#8251)."""

from fastapi import APIRouter

router = APIRouter(prefix="/llc", tags=["llc"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "module": "llc"}
