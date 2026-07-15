# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Role-curated skill bundles for SkillHub (Issue #10540)

A bundle is a named, role-oriented group of existing builtin skill ids.
No new skill logic is introduced — bundles are pure DATA that reference the
skill ids registered by ``skills.registry.SkillRegistry``.  Installing a
bundle delegates one-by-one to the existing
``SkillRegistry.enable_skill`` / ``SkillManager.persist_skill_enabled``
pair, exactly as the per-skill ``POST /skills/{name}/enable`` endpoint does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SkillBundle:
    """Immutable description of a role-curated skill bundle."""

    id: str
    name: str
    description: str
    member_skill_ids: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Canonical bundle catalogue — DATA ONLY.
# Member ids must match the ``name`` field in each skill's SkillManifest.
# ---------------------------------------------------------------------------

_BUNDLES: List[SkillBundle] = [
    SkillBundle(
        id="research",
        name="Research",
        description=(
            "Skills for gathering information from the web, feeds, videos, "
            "code repositories, and discovering new capabilities."
        ),
        member_skill_ids=[
            "web-fetch",
            "rss-reader",
            "youtube-transcript",
            "github-search",
            "skill-researcher",
        ],
    ),
    SkillBundle(
        id="engineering",
        name="Engineering",
        description=(
            "Skills that support software development workflows: code review, "
            "autonomous skill generation, and intelligent skill routing."
        ),
        member_skill_ids=[
            "code-review",
            "autonomous-skill-development",
            "skill-router",
        ],
    ),
    SkillBundle(
        id="knowledge",
        name="Knowledge",
        description=(
            "Skills for capturing, analysing, and organising information: "
            "document analysis, note taking, and calendar integration."
        ),
        member_skill_ids=[
            "document-analysis",
            "note-taking",
            "calendar-integration",
        ],
    ),
]

# Fast lookup by bundle id
_BUNDLE_BY_ID: Dict[str, SkillBundle] = {b.id: b for b in _BUNDLES}


# ---------------------------------------------------------------------------
# Public API — data access
# ---------------------------------------------------------------------------


def list_bundles() -> List[SkillBundle]:
    """Return all curated skill bundles (ordered, immutable)."""
    return list(_BUNDLES)


def get_bundle(bundle_id: str) -> SkillBundle:
    """Return the bundle with the given id.

    Raises:
        ValueError: when *bundle_id* is not a known bundle.
    """
    try:
        return _BUNDLE_BY_ID[bundle_id]
    except KeyError:
        raise ValueError(f"Unknown bundle id '{bundle_id}'") from None


# ---------------------------------------------------------------------------
# Install helper — reuses existing enable API
# ---------------------------------------------------------------------------


async def enable_bundle(
    bundle_id: str,
    *,
    registry,
    manager,
) -> Dict[str, object]:
    """Enable every member skill of a bundle via the existing governance path.

    Delegates to ``registry.enable_skill`` (dependency-checked) and
    ``manager.persist_skill_enabled`` (Redis persistence) for each member,
    mirroring ``POST /skills/{name}/enable`` exactly.

    Args:
        bundle_id: Id of the bundle to install.
        registry: ``SkillRegistry`` instance (injected to allow testing).
        manager: ``SkillManager`` instance (injected to allow testing).

    Returns:
        A dict with keys:
        - ``bundle_id`` — the requested bundle id
        - ``enabled`` — skill ids that were successfully enabled
        - ``skipped`` — skill ids that were not in the registry
        - ``failed`` — mapping of skill id → error message

    Raises:
        ValueError: when *bundle_id* is not a known bundle.
    """
    bundle = get_bundle(bundle_id)  # raises ValueError on unknown id

    enabled: List[str] = []
    skipped: List[str] = []
    failed: Dict[str, str] = {}

    for skill_id in bundle.member_skill_ids:
        result = registry.enable_skill(skill_id)
        if not result["success"]:
            error_msg: str = result.get("error", "enable failed")
            # Skill not in registry vs other failure
            if "not found" in error_msg.lower():
                logger.debug("Bundle '%s': skill '%s' not registered, skipping", bundle_id, skill_id)
                skipped.append(skill_id)
            else:
                logger.warning("Bundle '%s': failed to enable '%s': %s", bundle_id, skill_id, error_msg)
                failed[skill_id] = error_msg
            continue

        await manager.persist_skill_enabled(skill_id, True)
        logger.info("Bundle '%s': enabled skill '%s'", bundle_id, skill_id)
        enabled.append(skill_id)

    return {
        "bundle_id": bundle_id,
        "enabled": enabled,
        "skipped": skipped,
        "failed": failed,
    }
