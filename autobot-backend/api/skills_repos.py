# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Skills Repo API — CRUD + sync for skill repositories."""

import logging
from typing import Any, Dict, List

from auth_middleware import check_admin_permission
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from skills.db import get_skills_engine
from skills.models import RepoType, SkillRepo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter()


class AddRepoRequest(BaseModel):
    """Request body for registering a new skill repository."""

    name: str = Field(..., description="Human-readable repo name")
    url: str = Field(..., description="git URL, local path, HTTP URL, or MCP URL")
    repo_type: RepoType = Field(...)
    auto_sync: bool = Field(False)
    sync_interval: int = Field(60, description="Sync interval in minutes")


async def _sync_packages(repo: SkillRepo) -> List[Dict[str, Any]]:
    """Discover skill packages from a repository using the appropriate syncer.

    Delegates to GitRepoSync, LocalDirSync, or MCPClientSync based on repo_type.
    Returns a list of package dicts, or empty list if repo_type is unknown.
    """
    from skills.sync import GitRepoSync, LocalDirSync, MCPClientSync

    syncs = {
        RepoType.GIT: lambda: GitRepoSync(repo.url).discover(),
        RepoType.LOCAL: lambda: LocalDirSync(repo.url).discover(),
        RepoType.MCP: lambda: MCPClientSync(repo.url).discover(),
    }
    syncer = syncs.get(repo.repo_type)
    if not syncer:
        return []
    return await syncer()


async def _get_repo_by_id(session: AsyncSession, repo_id: str) -> SkillRepo:
    """Look up a SkillRepo by primary key; raise 404 if not found."""
    result = await session.execute(select(SkillRepo).where(SkillRepo.id == repo_id))
    repo = result.scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=404, detail=f"Repo {repo_id} not found")
    return repo


@router.post("/", summary="Register a new skill repository")
async def add_repo(
    body: AddRepoRequest,
    _: None = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Register a new skill repository in the skills database."""
    engine = get_skills_engine()
    async with AsyncSession(engine) as session:
        existing = await session.scalar(
            select(SkillRepo).where(SkillRepo.name == body.name)
        )
        if existing is not None:
            raise HTTPException(
                status_code=409, detail=f"Repo '{body.name}' already registered"
            )
        repo = SkillRepo(
            name=body.name,
            url=body.url,
            repo_type=body.repo_type,
            auto_sync=body.auto_sync,
            sync_interval=body.sync_interval,
        )
        session.add(repo)
        await session.commit()
        await session.refresh(repo)
    logger.info("Registered skill repo: %s (%s)", repo.name, repo.repo_type)
    return {"id": repo.id, "name": repo.name, "status": "registered"}


@router.get("", summary="List all registered skill repositories")
@router.get("/", include_in_schema=False)
async def list_repos() -> List[Dict[str, Any]]:
    """Return all registered skill repositories."""
    engine = get_skills_engine()
    async with AsyncSession(engine) as session:
        result = await session.execute(select(SkillRepo))
        repos = result.scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "url": r.url,
            "repo_type": r.repo_type,
            "auto_sync": r.auto_sync,
            "sync_interval": r.sync_interval,
            "last_synced": r.last_synced,
            "skill_count": r.skill_count,
            "status": r.status,
        }
        for r in repos
    ]


@router.post("/{repo_id}/sync", summary="Sync packages from a repository")
async def sync_repo(
    repo_id: str,
    _: None = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Trigger a sync of skill packages from the specified repository."""
    engine = get_skills_engine()
    async with AsyncSession(engine) as session:
        repo = await _get_repo_by_id(session, repo_id)
        try:
            packages = await _sync_packages(repo)
        except (
            Exception
        ) as exc:  # intentionally broad: can be network, git, or filesystem error
            logger.error("Sync failed for repo '%s': %s", repo.name, exc)
            raise HTTPException(
                status_code=502, detail=f"Sync failed for repo '{repo.name}': {exc}"
            ) from exc
        repo.skill_count = len(packages)
        await session.commit()
    logger.info("Synced %d packages from repo: %s", len(packages), repo.name)
    return {"synced": len(packages), "repo": repo.name}


@router.get("/{repo_id}/browse", summary="Browse packages in a repository")
async def browse_repo(repo_id: str) -> Dict[str, Any]:
    """List the skill package names available in the specified repository."""
    engine = get_skills_engine()
    async with AsyncSession(engine) as session:
        repo = await _get_repo_by_id(session, repo_id)
        packages = await _sync_packages(repo)
    names = [p["name"] for p in packages]
    return {"packages": names, "count": len(names)}
