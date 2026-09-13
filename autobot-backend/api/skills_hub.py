# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Community Skill Hub API Router (Issue #4412)

Endpoints for discovering and installing skills from the community registry.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from api.schemas_skills_hub import InstalledSkillOut, SkillHubInstallRequest, SkillListingOut, SkillUpdateOut
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.logging_manager import get_logger
from skills.hub import get_skill_hub

logger = get_logger(__name__)

# #16368: every route needs an authenticated caller, including any route added
# later. Installing or removing a hub skill also needs admin, per route: an
# install can start the entry's inline Python as an MCP subprocess.
router = APIRouter(tags=["skills-hub"], dependencies=[Depends(get_current_user)])


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("/search", response_model=List[SkillListingOut], summary="Search hub registry")
async def search_hub(q: str = "") -> List[SkillListingOut]:
    """Search the community skill registry by name or description."""
    hub = await get_skill_hub()
    results = await hub.search(q)
    return [SkillListingOut.from_listing(s) for s in results]


@router.post("/install", response_model=InstalledSkillOut, summary="Install a hub skill")
async def install_skill(body: SkillHubInstallRequest, _: None = Depends(check_admin_permission)) -> InstalledSkillOut:
    """Install a community skill from the hub registry."""
    hub = await get_skill_hub()
    try:
        installed = await hub.install(body.skill_id)
    except ValueError as exc:
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=404, detail="Internal server error") from exc
    except PermissionError as exc:
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=403, detail="Internal server error") from exc
    except Exception as exc:
        logger.exception("Hub install failed for '%s'", body.skill_id)
        raise HTTPException(status_code=500, detail=f"Install failed: {exc}") from exc
    return InstalledSkillOut.from_installed(installed)


@router.delete("/install/{skill_id}", summary="Uninstall a hub skill")
async def uninstall_skill(skill_id: str, _: None = Depends(check_admin_permission)) -> dict:
    """Remove a previously installed hub skill."""
    hub = await get_skill_hub()
    try:
        await hub.uninstall(skill_id)
    except ValueError as exc:
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=404, detail="Internal server error") from exc
    except Exception as exc:
        logger.exception("Hub uninstall failed for '%s'", skill_id)
        raise HTTPException(status_code=500, detail=f"Uninstall failed: {exc}") from exc
    return {"status": "uninstalled", "skill_id": skill_id}


@router.get("/installed", response_model=List[InstalledSkillOut], summary="List installed hub skills")
async def list_installed() -> List[InstalledSkillOut]:
    """List all community skills installed from the hub."""
    hub = await get_skill_hub()
    skills = await hub.list_installed()
    return [InstalledSkillOut.from_installed(s) for s in skills]


@router.get("/updates", response_model=List[SkillUpdateOut], summary="Check for hub skill updates")
async def check_updates() -> List[SkillUpdateOut]:
    """Return installed hub skills that have a newer version available."""
    hub = await get_skill_hub()
    updates = await hub.check_updates()
    return [
        SkillUpdateOut(
            id=u.id,
            name=u.name,
            current_version=u.current_version,
            latest_version=u.latest_version,
        )
        for u in updates
    ]
