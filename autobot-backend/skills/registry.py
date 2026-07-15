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
import importlib.util
import os
import pkgutil
import threading
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Set, Type

import yaml

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from prepared_facts import SkillRoutingIndex
from skills.base_skill import BaseSkill, DeclarativeSkill, SkillHealth, SkillManifest, SkillStatus
from skills.dependency_resolver import check_missing_dependencies, resolve_dependencies

logger = get_logger(__name__)

# #11141: skills arrive from independent sources (builtin modules, SKILL.md
# declaratives, the community hub, external git/http imports, sync backends).
# On a name collision we must resolve DETERMINISTICALLY by source trust — never
# by discovery order — so a SANDBOXED external import can never silently mask a
# trusted builtin (nor vice-versa). Higher number = higher trust = wins.
_SOURCE_PRIORITY: Dict[str, int] = {
    "builtin": 100,
    "custom": 50,
    "hub": 30,
    "external": 20,
    "mcp": 20,
    "sync": 20,
}
_DEFAULT_SOURCE_PRIORITY = 10


def _source_priority(source: str) -> int:
    """Trust rank for a skill source; unknown sources rank below all known ones."""
    return _SOURCE_PRIORITY.get(source, _DEFAULT_SOURCE_PRIORITY)


@dataclass
class SkillConflict:
    """A recorded cross-source skill name collision (#11141)."""

    name: str
    incumbent_source: str
    incumbent_version: str
    incoming_source: str
    incoming_version: str
    resolution: str  # "kept_incumbent" | "replaced_with_incoming"


class SkillRegistry:
    """Central registry for skill discovery, registration, and lifecycle.

    Thread-safe singleton that manages all registered skills.
    """

    def __init__(self) -> None:
        self._skills: Dict[str, BaseSkill] = {}
        self._skill_classes: Dict[str, Type[BaseSkill]] = {}
        self._lock = threading.Lock()
        self._routing_index: SkillRoutingIndex | None = None
        # #11141: source of each registered skill + recorded cross-source conflicts.
        self._sources: Dict[str, str] = {}
        self._conflicts: List[SkillConflict] = []

    def _resolve_name_conflict(self, name: str, incoming_source: str, incoming_version: str) -> bool:
        """Record a name collision and decide the winner by source trust (#11141).

        MUST be called while holding ``self._lock``. Returns True when the
        incoming skill should REPLACE the incumbent (strictly higher-trust
        source), False when the incumbent is kept. Either way the conflict is
        recorded (visible via :meth:`get_conflicts`) instead of being silently
        dropped. Ties keep the incumbent — a same-trust source never displaces
        an already-registered skill.
        """
        incumbent_source = self._sources.get(name, "builtin")
        try:
            incumbent_version = self._skills[name].get_manifest().version
        except Exception:
            incumbent_version = "unknown"
        # A same-source, same-version re-registration is an idempotent reload,
        # not a cross-source conflict — keep the incumbent without recording.
        if incoming_source == incumbent_source and incoming_version == incumbent_version:
            return False
        incoming_wins = _source_priority(incoming_source) > _source_priority(incumbent_source)
        resolution = "replaced_with_incoming" if incoming_wins else "kept_incumbent"
        self._conflicts.append(
            SkillConflict(
                name=name,
                incumbent_source=incumbent_source,
                incumbent_version=incumbent_version,
                incoming_source=incoming_source,
                incoming_version=incoming_version,
                resolution=resolution,
            )
        )
        logger.warning(
            "Skill name conflict on '%s': incumbent %s v%s (%s) vs incoming %s v%s (%s) -> %s",
            name,
            incumbent_source,
            incumbent_version,
            incumbent_source,
            incoming_source,
            incoming_version,
            incoming_source,
            resolution,
        )
        return incoming_wins

    def get_conflicts(self) -> List[Dict[str, Any]]:
        """Structured cross-source skill name conflicts recorded so far (#11141)."""
        with self._lock:
            return [asdict(c) for c in self._conflicts]

    def register(self, skill_class: Type[BaseSkill], source: str = "builtin") -> None:
        """Register a skill class and create its instance.

        Args:
            skill_class: A class extending BaseSkill.
            source: Origin of the skill (``builtin``/``custom``/``hub``/``external``/
                ``mcp``/``sync``). On a name collision the higher-trust source wins
                deterministically and the conflict is recorded (#11141).
        """
        manifest = skill_class.get_manifest()
        name = manifest.name
        with self._lock:
            if name in self._skills and not self._resolve_name_conflict(name, source, manifest.version):
                return
            instance = skill_class()
            self._skills[name] = instance
            self._skill_classes[name] = skill_class
            self._sources[name] = source
            logger.info("Registered skill: %s v%s (source=%s)", name, manifest.version, source)
        # #7431 ADR-006: publish skill_promoted so blocked plans waiting on
        # a matching capability can be re-routed and resumed via the
        # BlockedPlanResumer subscriber. Fire-and-forget; never raises if
        # Redis is unavailable (logged at debug).
        self._publish_skill_promoted(name, manifest.tools)
        self._rebuild_routing_index()

    def register_declarative(self, manifest: "SkillManifest", source: str = "builtin") -> bool:
        """Register a SKILL.md-style manifest as a DeclarativeSkill.

        Returns True if newly registered or if it replaced a lower-trust
        incumbent, False if an equal/higher-trust skill of that name was kept.
        On a name collision the winner is chosen by source trust and the
        conflict is recorded (#11141). Used by builtin Pass-2 discovery and by
        boot-time custom/hub-skill reload.
        """
        with self._lock:
            if manifest.name in self._skills and not self._resolve_name_conflict(
                manifest.name, source, manifest.version
            ):
                return False
            self._skills[manifest.name] = DeclarativeSkill(manifest)
            self._sources[manifest.name] = source
        self._rebuild_routing_index()
        self._publish_skill_promoted(manifest.name, manifest.tools)
        logger.info("Registered declarative skill: %s v%s (source=%s)", manifest.name, manifest.version, source)
        return True

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

        Handles two kinds of builtin skills:

        1. Python modules — files ending in ``.py`` (or packages with
           ``__init__.py``) that contain a ``BaseSkill`` subclass.  Discovered
           via ``pkgutil.iter_modules`` as before.

        2. Declarative SKILL.md-only subdirectories — subdirectories that
           contain a ``SKILL.md`` but no Python entry-point.  The YAML
           front-matter is parsed into a ``SkillManifest`` and the subdir is
           registered as a ``DeclarativeSkill`` so it appears in the registry,
           the routing index, and can be enabled/disabled by bundles.

        Returns the number of newly registered skills.
        """
        count = 0
        try:
            builtin_pkg = importlib.import_module("skills.builtin")
        except ImportError:
            logger.warning("skills.builtin package not found")
            return 0

        # --- pass 1: Python BaseSkill subclasses ---
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

        # --- pass 2: SKILL.md-only declarative subdirectories ---
        for pkg_path in builtin_pkg.__path__:
            for entry in os.scandir(pkg_path):
                if not entry.is_dir():
                    continue
                skill_md = os.path.join(entry.path, "SKILL.md")
                py_init = os.path.join(entry.path, "__init__.py")
                # Only handle dirs that have SKILL.md but no Python package
                # entry-point (those are already covered by pass 1 above).
                if not os.path.isfile(skill_md) or os.path.isfile(py_init):
                    continue
                # Also skip if any .py file exists — pass 1 handles those.
                has_py = any(f.endswith(".py") for f in os.listdir(entry.path))
                if has_py:
                    continue
                manifest = _parse_skill_md(skill_md)
                if manifest is None:
                    continue
                if self.register_declarative(manifest):
                    count += 1

        self._rebuild_routing_index()
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


def _parse_skill_md(skill_md_path: str) -> SkillManifest | None:
    """Parse the YAML front-matter of a SKILL.md file into a SkillManifest.

    Returns None and logs a warning on any parse/validation error so that a
    single malformed SKILL.md cannot abort the entire discovery pass.
    """
    try:
        with open(skill_md_path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        logger.warning("Cannot read %s: %s", skill_md_path, exc)
        return None

    # Extract the YAML front-matter block delimited by --- lines.
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        logger.warning("SKILL.md has no front-matter block: %s", skill_md_path)
        return None
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        logger.warning("SKILL.md front-matter not closed: %s", skill_md_path)
        return None

    raw_yaml = "\n".join(lines[1:end])
    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        logger.warning("Invalid YAML in %s: %s", skill_md_path, exc)
        return None

    if not isinstance(data, dict):
        logger.warning("SKILL.md front-matter is not a mapping: %s", skill_md_path)
        return None

    name = data.get("name")
    if not name:
        logger.warning("SKILL.md missing 'name' field: %s", skill_md_path)
        return None

    try:
        return SkillManifest(
            name=str(name),
            version=str(data.get("version", "1.0.0")),
            description=str(data.get("description", "")),
            author=str(data.get("author", "mrveiss")),
            category=str(data.get("category", "general")),
            dependencies=[str(d) for d in (data.get("dependencies") or [])],
            tools=[str(t) for t in (data.get("tools") or [])],
            triggers=[str(tr) for tr in (data.get("triggers") or [])],
            tags=[str(tg) for tg in (data.get("tags") or [])],
        )
    except Exception as exc:
        logger.warning("Cannot build SkillManifest from %s: %s", skill_md_path, exc)
        return None


get_skill_registry = lazy_singleton(SkillRegistry)
