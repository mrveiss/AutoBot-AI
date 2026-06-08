# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Manager (Issue #731)

High-level manager for the skills system. Handles initialization,
per-user skill preferences (via Redis), and skill execution routing.
"""

import time
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_management.cache_wrapper import RedisCache
from skills.registry import SkillRegistry, get_skill_registry

logger = get_logger(__name__)

REDIS_SKILL_PREFIX = "skills:config:"
REDIS_SKILL_ENABLED_PREFIX = "skills:enabled:"
REDIS_USER_SKILLS_PREFIX = "skills:user:"


class SkillManager:
    """Manages skill lifecycle, configuration persistence, and execution.

    Uses Redis for persistent storage of skill configs and user preferences.
    Includes metrics tracking for skill performance monitoring (Issue #4339).
    """

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self._registry = registry or get_skill_registry()
        self._metrics: Any | None = None

    @property
    def registry(self) -> SkillRegistry:
        """Access the underlying skill registry."""
        return self._registry

    async def initialize(self) -> Dict[str, Any]:
        """Initialize the skills system: discover and load all skills.

        Returns summary of initialization results.
        """
        count = self._registry.discover_builtin_skills()
        await self._load_persisted_configs()

        return {
            "skills_discovered": count,
            "total_registered": self._registry.skill_count,
            "categories": list(self._registry.categories),
        }

    async def execute_skill(
        self,
        skill_name: str,
        action: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a skill action.

        Args:
            skill_name: Name of the skill to execute.
            action: Tool/action name within the skill.
            params: Parameters for the action.

        Returns:
            Result dict from the skill execution.
        """
        skill = self._registry.get(skill_name)
        if not skill:
            return {"success": False, "error": f"Skill '{skill_name}' not found"}
        if not skill.enabled:
            return {"success": False, "error": f"Skill '{skill_name}' is disabled"}

        manifest = skill.get_manifest()
        if action not in manifest.tools:
            return {
                "success": False,
                "error": f"Unknown action '{action}' for skill '{skill_name}'",
            }

        # Track execution with metrics (Issue #4339)
        start_time = time.time()
        result = None
        error_type = None

        try:
            result = await skill.execute(action, params)
            success = result.get("success", True)
            return result
        except Exception as e:
            logger.exception("Skill execution failed: %s.%s", skill_name, action)
            success = False
            error_type = type(e).__name__
            return {
                "success": False,
                "error": f"Execution failed for {skill_name}.{action}",
            }
        finally:
            # Log metrics asynchronously (non-blocking)
            duration_ms = (time.time() - start_time) * 1000
            try:
                metrics = await self._get_metrics()
                if metrics:
                    await metrics.log_invocation(
                        skill_id=skill_name,
                        action=action,
                        success=success,
                        duration_ms=duration_ms,
                        error_type=error_type,
                    )
            except Exception as e:
                logger.debug("Failed to log skill metrics: %s", e)

    async def get_user_skill_preferences(self, user_id: str) -> Dict[str, bool]:
        """Get per-user skill enable/disable preferences from Redis.

        Returns mapping of skill_name -> enabled.
        """
        redis_client = await _get_redis()
        if not redis_client:
            return {}
        cache = RedisCache(redis_client)
        return await cache.get_json(f"{REDIS_USER_SKILLS_PREFIX}{user_id}", default={})

    async def save_user_skill_preferences(self, user_id: str, preferences: Dict[str, bool]) -> bool:
        """Save per-user skill preferences to Redis."""
        redis_client = await _get_redis()
        if not redis_client:
            return False
        cache = RedisCache(redis_client)
        return await cache.set_json(f"{REDIS_USER_SKILLS_PREFIX}{user_id}", preferences)

    async def persist_skill_config(self, skill_name: str, config: Dict[str, Any]) -> bool:
        """Persist a skill's configuration to Redis."""
        redis_client = await _get_redis()
        if not redis_client:
            return False
        cache = RedisCache(redis_client)
        return await cache.set_json(f"{REDIS_SKILL_PREFIX}{skill_name}", config)

    async def persist_skill_enabled(self, skill_name: str, enabled: bool) -> bool:
        """Persist a skill's enabled/disabled state to Redis (Issue #993)."""
        redis_client = await _get_redis()
        if not redis_client:
            return False
        cache = RedisCache(redis_client)
        return await cache.set_json(f"{REDIS_SKILL_ENABLED_PREFIX}{skill_name}", enabled)

    async def _load_persisted_configs(self) -> None:
        """Load persisted configs and enabled states from Redis (Issues #731, #993)."""
        redis_client = await _get_redis()
        if not redis_client:
            return
        cache = RedisCache(redis_client)
        for skill_info in self._registry.list_skills():
            name = skill_info["name"]
            try:
                config = await cache.get_json(f"{REDIS_SKILL_PREFIX}{name}")
                if config is not None:
                    self._registry.update_config(name, config)
                    logger.debug("Loaded persisted config for skill: %s", name)
            except Exception:
                logger.warning("Failed to load config for skill: %s", name)
            try:
                enabled = await cache.get_json(f"{REDIS_SKILL_ENABLED_PREFIX}{name}")
                if enabled is not None:
                    if enabled:
                        self._registry.enable_skill(name)
                    else:
                        self._registry.disable_skill(name)
                    logger.debug("Restored enabled state for skill: %s", name)
            except Exception:
                logger.warning("Failed to load enabled state for skill: %s", name)

    def list_skills_by_category(self) -> Dict[str, List[Dict[str, Any]]]:
        """Group all skills by their category."""
        by_category: Dict[str, List[Dict[str, Any]]] = {}
        for skill_info in self._registry.list_skills():
            category = skill_info["category"]
            by_category.setdefault(category, []).append(skill_info)
        return by_category

    async def sync_external_repo(self, repo_id: str) -> List[Dict[str, Any]]:
        """Import skill packages from an external SkillRepo and persist them.

        Looks up the SkillRepo by *repo_id*, delegates to
        :class:`~skills.external_importer.ExternalSkillImporter` for git repos
        or HTTP catalogs, persists the resulting SkillPackage rows (SANDBOXED),
        and updates the repo's ``skill_count`` and ``last_synced`` timestamp.

        Args:
            repo_id: Primary key of the SkillRepo to sync.

        Returns:
            List of dicts ``{"name": ..., "version": ..., "id": ...}`` for
            each newly imported package.

        Raises:
            ValueError: If the repo is not found or its type is unsupported.
            RuntimeError: If the underlying import fails (e.g. git not available).
        """
        from sqlalchemy import select

        from autobot_shared.time_utils import now_utc
        from skills.db import skills_session_context
        from skills.external_importer import ExternalSkillImporter
        from skills.models import RepoType, SkillPackage, SkillRepo

        async with skills_session_context() as session:
            result = await session.execute(select(SkillRepo).where(SkillRepo.id == repo_id))
            repo = result.scalar_one_or_none()
            if repo is None:
                raise ValueError(f"SkillRepo '{repo_id}' not found")

            importer = ExternalSkillImporter()
            if repo.repo_type == RepoType.GIT:
                packages = await importer.import_git_repo(repo.url, repo_id=repo_id)
            elif repo.repo_type == RepoType.HTTP:
                catalog_entries = await importer.import_http_catalog(repo.url)
                packages = []
                for entry in catalog_entries:
                    try:
                        pkg = await importer.install_from_catalog(entry.get("name", "unknown"), entry, repo_id=repo_id)
                        packages.append(pkg)
                    except ValueError as exc:
                        logger.warning("Skipping catalog entry: %s", exc)
            else:
                raise ValueError(
                    f"sync_external_repo does not support repo_type '{repo.repo_type}'"
                    " — use skills.sync for GIT/LOCAL/MCP repo discovery"
                )

            imported: List[Dict[str, Any]] = []
            for pkg in packages:
                existing = await session.scalar(select(SkillPackage).where(SkillPackage.name == pkg.name))
                if existing is not None:
                    logger.debug("Skill '%s' already in DB, skipping", pkg.name)
                    continue
                session.add(pkg)
                imported.append({"name": pkg.name, "version": pkg.version, "id": pkg.id})

            repo.skill_count = len(imported)
            repo.last_synced = now_utc()

        logger.info(
            "sync_external_repo: imported %d package(s) from repo %s",
            len(imported),
            repo_id,
        )
        return imported

    async def install_from_hub(self, skill_id: str) -> Dict[str, Any]:
        """Install a skill from the community hub registry.

        Delegates to :class:`~skills.hub.SkillHub`, which handles registry
        lookup, governance, Redis persistence, and MCP process startup.

        Args:
            skill_id: Registry id or name of the skill to install.

        Returns:
            Dict with ``id``, ``name``, ``mcp_url``, ``version``, and ``installed_at``.
        """
        from skills.hub import SkillHub

        hub = SkillHub()
        installed = await hub.install(skill_id)
        return {
            "id": installed.id,
            "name": installed.name,
            "mcp_url": installed.mcp_url,
            "version": installed.version,
            "installed_at": installed.installed_at,
        }

    def search_skills(self, query: str) -> List[Dict[str, Any]]:
        """Search skills by name, description, or tags."""
        query_lower = query.lower()
        results = []
        for skill_info in self._registry.list_skills():
            if _matches_query(skill_info, query_lower):
                results.append(skill_info)
        return results

    async def _get_metrics(self) -> Any | None:
        """Get or create the SkillMetrics instance (lazy initialization)."""
        if self._metrics is None:
            try:
                from services.skill_management.skill_metrics import SkillMetrics

                self._metrics = SkillMetrics()
            except ImportError:
                logger.debug("SkillMetrics not available")
                return None
        return self._metrics


def _matches_query(skill_info: Dict[str, Any], query: str) -> bool:
    """Check if a skill matches a search query.

    Helper for search_skills (Issue #731).
    """
    if query in skill_info["name"].lower():
        return True
    if query in skill_info["description"].lower():
        return True
    for tag in skill_info.get("tags", []):
        if query in tag.lower():
            return True
    return False


async def _get_redis():
    """Get async Redis client, returning None if unavailable.

    Helper for SkillManager Redis operations (Issue #731).
    """
    try:
        from autobot_shared.redis_client import get_async_redis_client

        return await get_async_redis_client(database="main")
    except Exception:
        logger.debug("Redis not available for skill persistence")
        return None
