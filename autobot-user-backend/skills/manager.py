# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Manager (Issue #731)

High-level manager for the skills system. Handles initialization,
per-user skill preferences (via Redis), and skill execution routing.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from skills.registry import SkillRegistry, get_skill_registry

logger = logging.getLogger(__name__)

REDIS_SKILL_PREFIX = "skills:config:"
REDIS_USER_SKILLS_PREFIX = "skills:user:"


class SkillManager:
    """Manages skill lifecycle, configuration persistence, and execution.

    Uses Redis for persistent storage of skill configs and user preferences.
    """

    def __init__(self, registry: Optional[SkillRegistry] = None) -> None:
        self._registry = registry or get_skill_registry()

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

        try:
            result = await skill.execute(action, params)
            return result
        except Exception:
            logger.exception("Skill execution failed: %s.%s", skill_name, action)
            return {
                "success": False,
                "error": f"Execution failed for {skill_name}.{action}",
            }

    async def get_user_skill_preferences(self, user_id: str) -> Dict[str, bool]:
        """Get per-user skill enable/disable preferences from Redis.

        Returns mapping of skill_name -> enabled.
        """
        redis_client = _get_redis()
        if not redis_client:
            return {}
        key = f"{REDIS_USER_SKILLS_PREFIX}{user_id}"
        try:
            raw = await redis_client.get(key)
            if raw:
                return json.loads(raw)
        except Exception:
            logger.exception("Failed to load user skill prefs: %s", user_id)
        return {}

    async def save_user_skill_preferences(
        self, user_id: str, preferences: Dict[str, bool]
    ) -> bool:
        """Save per-user skill preferences to Redis."""
        redis_client = _get_redis()
        if not redis_client:
            return False
        key = f"{REDIS_USER_SKILLS_PREFIX}{user_id}"
        try:
            await redis_client.set(key, json.dumps(preferences))
            return True
        except Exception:
            logger.exception("Failed to save user skill prefs: %s", user_id)
            return False

    async def persist_skill_config(
        self, skill_name: str, config: Dict[str, Any]
    ) -> bool:
        """Persist a skill's configuration to Redis."""
        redis_client = _get_redis()
        if not redis_client:
            return False
        key = f"{REDIS_SKILL_PREFIX}{skill_name}"
        try:
            await redis_client.set(key, json.dumps(config))
            return True
        except Exception:
            logger.exception("Failed to persist skill config: %s", skill_name)
            return False

    async def _load_persisted_configs(self) -> None:
        """Load persisted configs from Redis and apply to skills.

        Helper for initialize (Issue #731).
        """
        redis_client = _get_redis()
        if not redis_client:
            return
        for skill_info in self._registry.list_skills():
            name = skill_info["name"]
            key = f"{REDIS_SKILL_PREFIX}{name}"
            try:
                raw = await redis_client.get(key)
                if raw:
                    config = json.loads(raw)
                    self._registry.update_config(name, config)
                    logger.debug("Loaded persisted config for skill: %s", name)
            except Exception:
                logger.warning("Failed to load config for skill: %s", name)

    def list_skills_by_category(self) -> Dict[str, List[Dict[str, Any]]]:
        """Group all skills by their category."""
        by_category: Dict[str, List[Dict[str, Any]]] = {}
        for skill_info in self._registry.list_skills():
            category = skill_info["category"]
            by_category.setdefault(category, []).append(skill_info)
        return by_category

    def search_skills(self, query: str) -> List[Dict[str, Any]]:
        """Search skills by name, description, or tags."""
        query_lower = query.lower()
        results = []
        for skill_info in self._registry.list_skills():
            if _matches_query(skill_info, query_lower):
                results.append(skill_info)
        return results


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


def _get_redis():
    """Get async Redis client, returning None if unavailable.

    Helper for SkillManager Redis operations (Issue #731).
    """
    try:
        from autobot_shared.redis_client import get_redis_client

        return get_redis_client(async_client=True, database="main")
    except Exception:
        logger.debug("Redis not available for skill persistence")
        return None
