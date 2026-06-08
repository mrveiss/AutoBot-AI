# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Community Skill Hub API Router (Issue #4412)

Endpoints for discovering and installing skills from the community registry.
"""

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from autobot_shared.logging_manager import get_logger
from skills.hub import InstalledSkill, SkillListing, get_skill_hub

logger = get_logger(__name__)

router = APIRouter(tags=["skills-hub"])


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class SkillListingOut(BaseModel):
    id: str
    name: str
    description: str
    mcp_url: str
    version: str
    tags: List[str] = Field(default_factory=list)

    @classmethod
    def from_listing(cls, s: SkillListing) -> "SkillListingOut":
        return cls(
            id=s.id,
            name=s.name,
            description=s.description,
            mcp_url=s.mcp_url,
            version=s.version,
            tags=s.tags,
        )


class InstalledSkillOut(BaseModel):
    id: str
    name: str
    mcp_url: str
    version: str
    installed_at: str

    @classmethod
    def from_installed(cls, s: InstalledSkill) -> "InstalledSkillOut":
        return cls(
            id=s.id,
            name=s.name,
            mcp_url=s.mcp_url,
            version=s.version,
            installed_at=s.installed_at,
        )


class SkillUpdateOut(BaseModel):
    id: str
    name: str
    current_version: str
    latest_version: str


class InstallRequest(BaseModel):
    skill_id: str = Field(..., description="Registry id or name of the skill to install")


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
async def install_skill(body: InstallRequest) -> InstalledSkillOut:
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
async def uninstall_skill(skill_id: str) -> dict:
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
