# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Skill Registry (Issue #731)

Central registry for discovering, registering, and managing skill instances.
Handles skill lifecycle (load, enable, disable) and dependency validation.
"""

import importlib
import pkgutil
import threading
from typing import Any, Dict, List, Set, Type

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from prepared_facts import SkillRoutingIndex
from skills.base_skill import BaseSkill, SkillHealth, SkillManifest, SkillStatus
from skills.dependency_resolver import check_missing_dependencies, resolve_dependencies

logger = get_logger(__name__)


class SkillRegistry:
    """Central registry for skill discovery, registration, and lifecycle.

    Thread-safe singleton that manages all registered skills.
    """

    def __init__(self) -> None:
        self._skills: Dict[str, BaseSkill] = {}
        self._skill_classes: Dict[str, Type[BaseSkill]] = {}
        self._lock = threading.Lock()
        self._routing_index: SkillRoutingIndex | None = None

    def register(self, skill_class: Type[BaseSkill]) -> None:
        """Register a skill class and create its instance.

        Args:
            skill_class: A class extending BaseSkill.
        """
        manifest = skill_class.get_manifest()
        name = manifest.name
        with self._lock:
            if name in self._skills:
                logger.warning("Skill '%s' already registered, skipping", name)
                return
            instance = skill_class()
            self._skills[name] = instance
            self._skill_classes[name] = skill_class
            logger.info("Registered skill: %s v%s", name, manifest.version)
        # #7431 ADR-006: publish skill_promoted so blocked plans waiting on
        # a matching capability can be re-routed and resumed via the
        # BlockedPlanResumer subscriber. Fire-and-forget; never raises if
        # Redis is unavailable (logged at debug).
        self._publish_skill_promoted(name, manifest.tools)
        self._rebuild_routing_index()

    def _rebuild_routing_index(self) -> None:
        """Rebuild the pre-tokenized skill routing index from current registry state.

        Called after every register() and unregister() so hot-path lookups are
        always O(1) dict access into a frozen snapshot — no per-request regex.
        Acquires the lock only to snapshot the skill list; index construction
        runs outside the lock so tokenization work does not block concurrents.
        """
        with self._lock:
            skill_list = self.list_skills()
        try:
            self._routing_index = SkillRoutingIndex.build_at_startup(skill_list)
        except Exception as exc:
            logger.warning("Failed to rebuild routing index: %s", exc)
            self._routing_index = None

    def get_routing_index(self) -> SkillRoutingIndex | None:
        """Return the current pre-built skill routing index, or None if not built."""
        return self._routing_index

    @staticmethod
    def _publish_skill_promoted(name: str, tools: List[str]) -> None:
        """Best-effort publish of skill_promoted to Redis pub-sub (#7431).

        Lazy import keeps SkillRegistry independent of the publisher module
        at load time. Silent on import failure or Redis unavailability:
        skill registration must succeed even if the resume path is offline.
        """
        try:
            from skills.skill_promotion_publisher import publish_skill_promoted
        except ImportError:
            return
        try:
            publish_skill_promoted(name, tools)
        except Exception as exc:  # never let publish plumbing break the registry
            logger.debug("skill_promoted publish failed: %s", exc)

    def reload(self) -> int:
        """Re-discover builtin skills, registering any newly added modules.

        Called after a skill is promoted to disk so the new skill becomes
        available without a full backend restart (Issue #951).

        Returns the count of newly registered skills.
        """
        existing = set(self._skills.keys())
        discovered = self.discover_builtin_skills()
        new_names = set(self._skills.keys()) - existing
        if new_names:
            logger.info("Hot-reloaded %d new skill(s): %s", len(new_names), new_names)
        return discovered

    def unregister(self, name: str) -> bool:
        """Remove a skill from the registry.

        Returns True if the skill was found and removed.
        """
        with self._lock:
            if name not in self._skills:
                return False
            skill = self._skills[name]
            if skill.enabled:
                skill.disable()
            del self._skills[name]
            del self._skill_classes[name]
            logger.info("Unregistered skill: %s", name)
        self._rebuild_routing_index()
        return True

    def get(self, name: str) -> BaseSkill | None:
        """Get a skill instance by name."""
        return self._skills.get(name)

    def list_skills(self) -> List[Dict[str, Any]]:
        """List all registered skills with their manifest and status."""
        results = []
        for name, skill in self._skills.items():
            manifest = skill.get_manifest()
            results.append(
                {
                    "name": manifest.name,
                    "version": manifest.version,
                    "description": manifest.description,
                    "author": manifest.author,
                    "category": manifest.category,
                    "status": skill.status.value,
                    "enabled": skill.enabled,
                    "tools": manifest.tools,
                    "triggers": manifest.triggers,
                    "dependencies": manifest.dependencies,
                    "tags": manifest.tags,
                }
            )
        return results

    def get_skill_detail(self, name: str) -> Dict[str, Any] | None:
        """Get full detail for a single skill including config schema."""
        skill = self._skills.get(name)
        if not skill:
            return None
        manifest = skill.get_manifest()
        return {
            "name": manifest.name,
            "version": manifest.version,
            "description": manifest.description,
            "author": manifest.author,
            "category": manifest.category,
            "status": skill.status.value,
            "enabled": skill.enabled,
            "tools": manifest.tools,
            "triggers": manifest.triggers,
            "dependencies": manifest.dependencies,
            "tags": manifest.tags,
            "config_schema": {k: v.model_dump() for k, v in manifest.config.items()},
            "current_config": skill.config,
            "health": skill.get_health().model_dump(),
        }

    def enable_skill(self, name: str) -> Dict[str, Any]:
        """Enable a skill, checking dependencies first.

        Returns dict with 'success' and optional 'error' keys.
        """
        skill = self._skills.get(name)
        if not skill:
            return {"success": False, "error": f"Skill '{name}' not found"}

        manifest = skill.get_manifest()
        available = set(self._skills.keys())
        missing = check_missing_dependencies(name, manifest.dependencies, available)
        if missing:
            skill._status = SkillStatus.MISSING_DEPS
            return {
                "success": False,
                "error": f"Missing dependencies: {missing}",
            }

        disabled_deps = _get_disabled_deps(self._skills, manifest)
        if disabled_deps:
            return {
                "success": False,
                "error": f"Dependencies not enabled: {disabled_deps}",
            }

        skill.enable()
        return {"success": True}

    def disable_skill(self, name: str) -> Dict[str, Any]:
        """Disable a skill, warning about dependents."""
        skill = self._skills.get(name)
        if not skill:
            return {"success": False, "error": f"Skill '{name}' not found"}

        dependents = _find_enabled_dependents(self._skills, name)
        skill.disable()
        result: Dict[str, Any] = {"success": True}
        if dependents:
            result["warning"] = f"These enabled skills depend on '{name}': {dependents}"
        return result

    def update_config(self, name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Update a skill's configuration."""
        skill = self._skills.get(name)
        if not skill:
            return {"success": False, "error": f"Skill '{name}' not found"}

        errors = skill.validate_config(config)
        if errors:
            return {"success": False, "errors": errors}

        skill.apply_config(config)
        return {"success": True, "config": skill.config}

    def get_health(self, name: str) -> SkillHealth | None:
        """Get health status for a specific skill."""
        skill = self._skills.get(name)
        if not skill:
            return None
        return skill.get_health()

    def get_all_health(self) -> List[Dict[str, Any]]:
        """Get health status for all registered skills."""
        return [skill.get_health().model_dump() for skill in self._skills.values()]

    def get_loading_order(self) -> List[str]:
        """Compute the correct loading order respecting dependencies.

        Raises DependencyCycleError if cycles are detected.
        """
        deps = {name: skill.get_manifest().dependencies for name, skill in self._skills.items()}
        return resolve_dependencies(deps)

    def discover_builtin_skills(self) -> int:
        """Auto-discover and register all skills in skills.builtin package.

        Returns the number of newly registered skills.
        """
        count = 0
        try:
            builtin_pkg = importlib.import_module("skills.builtin")
        except ImportError:
            logger.warning("skills.builtin package not found")
            return 0

        for importer, modname, _ispkg in pkgutil.iter_modules(builtin_pkg.__path__):
            try:
                module = importlib.import_module(f"skills.builtin.{modname}")
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and issubclass(attr, BaseSkill) and attr is not BaseSkill:
                        self.register(attr)
                        count += 1
            except Exception:
                logger.exception("Failed to load skill module: %s", modname)
        logger.info("Discovered %d builtin skills", count)
        return count

    @property
    def skill_count(self) -> int:
        """Number of registered skills."""
        return len(self._skills)

    @property
    def enabled_count(self) -> int:
        """Number of currently enabled skills."""
        return sum(1 for s in self._skills.values() if s.enabled)

    @property
    def categories(self) -> Set[str]:
        """Set of all skill categories."""
        return {s.get_manifest().category for s in self._skills.values()}


def _get_disabled_deps(skills: Dict[str, BaseSkill], manifest: SkillManifest) -> List[str]:
    """Find dependencies that exist but are not enabled.

    Helper for enable_skill (Issue #731).
    """
    disabled = []
    for dep_name in manifest.dependencies:
        dep = skills.get(dep_name)
        if dep and not dep.enabled:
            disabled.append(dep_name)
    return disabled


def _find_enabled_dependents(skills: Dict[str, BaseSkill], name: str) -> List[str]:
    """Find enabled skills that depend on the given skill name.

    Helper for disable_skill (Issue #731).
    """
    dependents = []
    for skill_name, skill in skills.items():
        if skill.enabled and name in skill.get_manifest().dependencies:
            dependents.append(skill_name)
    return dependents


get_skill_registry = lazy_singleton(SkillRegistry)
