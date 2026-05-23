"""LLC API router (GH#8251)."""

from fastapi import APIRouter

from .activity import router as activity_router
from .agent_api import router as agent_router
from .api_keys import router as api_keys_router
from .approvals import router as approvals_router
from .budget import router as budget_router
from .companies import router as companies_router
from .goals import router as goals_router
from .secrets import router as secrets_router
from .sprints import router as sprints_router
from .work_items import router as work_items_router

router = APIRouter(prefix="/llc", tags=["llc"])
router.include_router(activity_router)
router.include_router(approvals_router)
router.include_router(budget_router)
router.include_router(companies_router)
router.include_router(goals_router)
router.include_router(secrets_router)
router.include_router(sprints_router)
router.include_router(work_items_router)
router.include_router(api_keys_router)
router.include_router(agent_router)


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "module": "llc"}
