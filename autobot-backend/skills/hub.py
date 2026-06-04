# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Community Skill Hub (Issue #4412)

Client for discovering and installing externally published MCP skills from
a registry. Hub-installed skills pass through governance and persist to Redis
like generated skills, and run as MCP subprocesses via MCPProcessManager when
inline skill_py content is available.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

REDIS_HUB_PREFIX = "skills:hub:"
_INDEX_TTL_SECONDS = 300  # 5-minute registry cache
_hub_lock = asyncio.Lock()


@dataclass
class SkillListing:
    """A skill entry returned from the hub registry."""

    id: str
    name: str
    description: str
    mcp_url: str
    version: str
    tags: list[str] = field(default_factory=list)


@dataclass
class InstalledSkill:
    """Record of a hub-installed skill."""

    id: str
    name: str
    mcp_url: str
    version: str
    installed_at: str = ""


@dataclass
class SkillUpdate:
    """A pending update for an installed hub skill."""

    id: str
    name: str
    current_version: str
    latest_version: str


class SkillHub:
    """Discover and install community skills from a registry.

    The registry is a JSON index fetched from ``ssot_config.misc.skill_hub_url``.
    Each installed skill record is persisted to Redis under ``skills:hub:<id>``.
    """

    def __init__(self, hub_url: str | None = None) -> None:
        if hub_url is None:
            try:
                from autobot_shared.ssot_config import config as ssot

                hub_url = ssot.misc.skill_hub_url
            except Exception:
                hub_url = ""
        self._hub_url = _validate_hub_url(hub_url)
        self._index: list[dict[str, Any]] | None = None
        self._index_fetched_at: float = 0.0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def search(self, query: str) -> list[SkillListing]:
        """Return skills from the registry whose name or description match *query*."""
        index = await self._fetch_index()
        q = query.lower()
        results = []
        for entry in index:
            if q in entry.get("name", "").lower() or q in entry.get("description", "").lower():
                results.append(_listing_from_entry(entry))
        return results

    async def install(self, skill_id: str) -> InstalledSkill:
        """Download, validate, and register a skill from the hub.

        Steps:
        1. Fetch skill manifest from registry index.
        2. Governance gate — only FULL_AUTO passes without admin review.
        3. Persist record to Redis under skills:hub:{skill_id}.
        4. If the entry contains skill_py content, start MCP subprocess.
        """
        entry = await self._find_entry(skill_id)
        if entry is None:
            raise ValueError(f"Skill '{skill_id}' not found in hub registry")

        skill_name = entry["name"]
        mcp_url = entry.get("mcp_url", "")
        version = entry.get("version", "latest")

        # Governance gate — raise for both SEMI_AUTO (queued) and LOCKED (denied)
        from skills.governance import GovernanceEngine
        from skills.models import GovernanceMode

        engine = GovernanceEngine(mode=GovernanceMode.SEMI_AUTO)
        activation = await engine.request_activation(
            skill_name=skill_name,
            requested_by="hub",
            reason=f"Community hub install: {skill_id}",
        )
        if not activation.approved:
            msg = (
                f"Hub skill '{skill_name}' queued for admin approval (approval_id={activation.approval_id})"
                if activation.requires_human_review
                else f"Governance denied activation of hub skill '{skill_name}': {activation.reason}"
            )
            raise PermissionError(msg)

        from autobot_shared.time_utils import now_utc

        installed_at = now_utc().isoformat()
        # Use skill_id (registry id) as the persistent record key — not a generated UUID
        record: dict[str, Any] = {
            "id": skill_id,
            "name": skill_name,
            "mcp_url": mcp_url,
            "version": version,
            "installed_at": installed_at,
        }
        await self._persist_record(skill_id, record)

        # If the entry supplies inline Python, start it as a local MCP subprocess
        skill_py: str | None = entry.get("skill_py")
        if skill_py:
            try:
                from skills.mcp_process import get_mcp_manager

                mgr = await get_mcp_manager()
                await mgr.start(skill_name, skill_py)
                logger.info("Started hub skill MCP process: %s", skill_name)
            except Exception as exc:
                logger.warning("Could not start hub skill process for '%s': %s", skill_name, exc)

        return InstalledSkill(
            id=skill_id,
            name=skill_name,
            mcp_url=mcp_url,
            version=version,
            installed_at=installed_at,
        )

    async def uninstall(self, skill_id: str) -> None:
        """Remove a hub-installed skill from Redis (and stop its MCP process)."""
        record = await self._load_record(skill_id)
        if record is None:
            raise ValueError(f"Hub skill '{skill_id}' is not installed")

        skill_name = record.get("name", "")

        try:
            from skills.mcp_process import get_mcp_manager

            mgr = await get_mcp_manager()
            await mgr.stop(skill_name)
        except Exception as exc:
            logger.debug("MCP process stop for '%s': %s", skill_name, exc)

        await self._delete_record(skill_id)
        logger.info("Uninstalled hub skill '%s' (%s)", skill_name, skill_id)

    async def list_installed(self) -> list[InstalledSkill]:
        """Return all hub-installed skills persisted in Redis."""
        redis = await _get_redis()
        if redis is None:
            return []
        try:
            result = []
            async for key in redis.scan_iter(match=f"{REDIS_HUB_PREFIX}*"):
                key_str = key.decode() if isinstance(key, bytes) else key
                raw = await redis.get(key_str)
                if raw:
                    rec = json.loads(raw)
                    result.append(
                        InstalledSkill(
                            id=rec.get("id", ""),
                            name=rec.get("name", ""),
                            mcp_url=rec.get("mcp_url", ""),
                            version=rec.get("version", ""),
                            installed_at=rec.get("installed_at", ""),
                        )
                    )
            return result
        except Exception as exc:
            logger.warning("Failed to list installed hub skills: %s", exc)
            return []

    async def check_updates(self) -> list[SkillUpdate]:
        """Compare installed versions against the current registry index."""
        installed = await self.list_installed()
        if not installed:
            return []
        index = await self._fetch_index()
        index_by_name = {e["name"]: e for e in index}
        updates = []
        for skill in installed:
            entry = index_by_name.get(skill.name)
            if entry and entry.get("version", skill.version) != skill.version:
                updates.append(
                    SkillUpdate(
                        id=skill.id,
                        name=skill.name,
                        current_version=skill.version,
                        latest_version=entry["version"],
                    )
                )
        return updates

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_index(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self._index is not None and (now - self._index_fetched_at) < _INDEX_TTL_SECONDS:
            return self._index
        if not self._hub_url:
            logger.debug("skill_hub_url not configured — returning empty index")
            return []
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(self._hub_url)
                resp.raise_for_status()
                data = resp.json()
                self._index = data.get("skills", [])
                self._index_fetched_at = now
                return self._index
        except Exception as exc:
            logger.warning("Failed to fetch hub index from '%s': %s", self._hub_url, exc)
            return self._index or []

    async def _find_entry(self, skill_id: str) -> dict[str, Any] | None:
        index = await self._fetch_index()
        for entry in index:
            if entry.get("id") == skill_id or entry.get("name") == skill_id:
                return entry
        return None

    async def _persist_record(self, skill_id: str, record: dict[str, Any]) -> None:
        redis = await _get_redis()
        if redis is None:
            return
        try:
            await redis.set(f"{REDIS_HUB_PREFIX}{skill_id}", json.dumps(record))
        except Exception as exc:
            logger.warning("Failed to persist hub skill record: %s", exc)

    async def _load_record(self, skill_id: str) -> dict[str, Any] | None:
        redis = await _get_redis()
        if redis is None:
            return None
        try:
            raw = await redis.get(f"{REDIS_HUB_PREFIX}{skill_id}")
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.warning("Failed to load hub skill record '%s': %s", skill_id, exc)
            return None

    async def _delete_record(self, skill_id: str) -> None:
        redis = await _get_redis()
        if redis is None:
            return
        try:
            await redis.delete(f"{REDIS_HUB_PREFIX}{skill_id}")
        except Exception as exc:
            logger.warning("Failed to delete hub skill record '%s': %s", skill_id, exc)


# ------------------------------------------------------------------
# Module-level singleton (asyncio-safe factory)
# ------------------------------------------------------------------

_hub_singleton: SkillHub | None = None


async def get_skill_hub() -> SkillHub:
    """Return the module-level SkillHub singleton (asyncio-safe init)."""
    global _hub_singleton
    if _hub_singleton is None:
        async with _hub_lock:
            if _hub_singleton is None:
                _hub_singleton = SkillHub()
    return _hub_singleton


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _validate_hub_url(url: str) -> str:
    """Reject non-http(s) URLs to prevent SSRF."""
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        logger.warning("skill_hub_url rejected (non-http scheme '%s'): %s", parsed.scheme, url)
        return ""
    return url


def _listing_from_entry(entry: dict[str, Any]) -> SkillListing:
    return SkillListing(
        id=entry.get("id", entry.get("name", "")),
        name=entry.get("name", ""),
        description=entry.get("description", ""),
        mcp_url=entry.get("mcp_url", ""),
        version=entry.get("version", ""),
        tags=entry.get("tags", []),
    )


async def _get_redis():
    try:
        from autobot_shared.redis_client import get_async_redis_client

        return await get_async_redis_client(database="main")
    except Exception:
        logger.debug("Redis not available for hub persistence")
        return None
