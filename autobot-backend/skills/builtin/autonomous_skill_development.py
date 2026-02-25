# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Autonomous Skill Development Skill (Issue #951)

When enabled, AutoBot can detect its own capability gaps and autonomously
develop new skills to fill them, making the platform self-improving.

Governance modes:
  FULL_AUTO  — gap detected → generate → validate → promote → hot-reload
  SEMI_AUTO  — gap detected → generate → create pending approval → notify admin
  LOCKED     — gap is logged only, no generation
"""
import logging
from typing import Any, Dict

from skills.base_skill import BaseSkill, SkillManifest

logger = logging.getLogger(__name__)


class AutonomousSkillDevelopmentSkill(BaseSkill):
    """Self-improvement skill: detect gaps, generate, and activate new skills."""

    @staticmethod
    def get_manifest() -> SkillManifest:
        """Return autonomous skill development manifest."""
        return SkillManifest(
            name="autonomous-skill-development",
            version="1.0.0",
            description=(
                "Detects capability gaps from agent output and autonomously "
                "generates new skills to fill them.  Governance mode controls "
                "whether skills are activated immediately (FULL_AUTO) or queued "
                "for admin review (SEMI_AUTO)."
            ),
            author="mrveiss",
            category="self-improvement",
            dependencies=[],
            tools=["trigger_gap_development"],
            triggers=["agent_capability_gap", "explicit_gap_signal"],
            tags=["self-improvement", "meta", "governance", "gap-detection"],
        )

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Orchestrate the gap-to-skill pipeline.

        Args:
            params: dict with keys:
                - capability: str   description of the missing capability
                - requested_by: str  caller identity (default "autobot-self")
                - context: dict      original agent output / request context

        Returns:
            dict with keys: success, state, approval_id, skill_name, message
        """
        capability = params.get("capability", "")
        requested_by = params.get("requested_by", "autobot-self")
        if not capability:
            return {"success": False, "message": "capability description is required"}

        mode = await _get_governance_mode()
        if mode == "locked":
            logger.info(
                "Autonomous skill dev blocked by LOCKED governance: %s", capability
            )
            return {
                "success": False,
                "state": "locked",
                "message": "Governance is LOCKED — gap logged, no generation attempted.",
            }

        return await _run_development_pipeline(capability, requested_by, mode)


async def _get_governance_mode() -> str:
    """Read active governance mode from DB (or default to semi_auto).

    Helper for AutonomousSkillDevelopmentSkill.execute (Issue #951).
    """
    try:
        from skills.db import get_skills_engine
        from skills.models import GovernanceConfig
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession

        engine = get_skills_engine()
        async with AsyncSession(engine) as session:
            cfg = await session.scalar(select(GovernanceConfig))
            if cfg:
                return cfg.mode
    except Exception as exc:
        logger.warning("Could not read governance config: %s", exc)
    return "semi_auto"


async def _run_development_pipeline(
    capability: str, requested_by: str, mode: str
) -> Dict[str, Any]:
    """Execute the generate → persist → govern → (optionally) promote pipeline.

    Helper for AutonomousSkillDevelopmentSkill.execute (Issue #951).
    """
    from skills.generator import SkillGenerator

    try:
        pkg = await SkillGenerator().generate(capability)
    except Exception as exc:
        logger.error("Skill generation failed for '%s': %s", capability, exc)
        return {"success": False, "state": "generation_failed", "message": str(exc)}

    skill_id = await _save_draft(pkg, requested_by, capability)
    approval_id = await _request_governance(
        pkg, skill_id, requested_by, capability, mode
    )

    if mode == "full_auto":
        promoted = await _promote_and_reload(pkg, skill_id)
        return {
            "success": True,
            "state": "promoted" if promoted else "promotion_failed",
            "skill_name": pkg["name"],
            "skill_id": skill_id,
            "message": (
                f"Skill '{pkg['name']}' generated and activated automatically."
                if promoted
                else f"Skill '{pkg['name']}' generated but promotion failed."
            ),
        }

    return {
        "success": True,
        "state": "pending_approval",
        "skill_name": pkg["name"],
        "skill_id": skill_id,
        "approval_id": approval_id,
        "message": (f"Skill '{pkg['name']}' generated and queued for admin approval."),
    }


async def _save_draft(pkg: Dict[str, Any], requested_by: str, gap: str) -> str:
    """Persist the generated skill package as a DRAFT in the DB.

    Helper for _run_development_pipeline (Issue #951).
    Returns the new SkillPackage ID.
    """
    try:
        from skills.db import get_skills_engine
        from skills.models import SkillPackage, SkillState
        from sqlalchemy.ext.asyncio import AsyncSession

        engine = get_skills_engine()
        async with AsyncSession(engine) as session:
            sp = SkillPackage(
                name=pkg["name"],
                version=pkg["manifest"].get("version", "1.0.0"),
                state=SkillState.DRAFT,
                skill_md=pkg["skill_md"],
                skill_py=pkg.get("skill_py"),
                manifest=pkg["manifest"],
                gap_reason=gap,
                requested_by=requested_by,
            )
            session.add(sp)
            await session.commit()
            await session.refresh(sp)
            logger.info("Draft skill saved: %s (%s)", pkg["name"], sp.id)
            skill_id = sp.id
        await _publish_new_draft_event(pkg["name"], skill_id, gap)
        return skill_id
    except Exception as exc:
        logger.warning("Failed to persist draft skill: %s", exc)
        return pkg["name"]


async def _publish_new_draft_event(skill_name: str, skill_id: str, gap: str) -> None:
    """Publish a Redis event for real-time SLM notification.

    Helper for _save_draft (Issue #951).
    """
    try:
        import json

        from autobot_shared.redis_client import get_redis_client

        redis = get_redis_client(async_client=True, database="main")
        await redis.publish(
            "skills:new_draft",
            json.dumps(
                {
                    "skill_name": skill_name,
                    "skill_id": skill_id,
                    "gap_description": gap,
                }
            ),
        )
    except Exception as exc:
        logger.debug("Failed to publish new_draft event: %s", exc)


async def _request_governance(
    pkg: Dict[str, Any],
    skill_id: str,
    requested_by: str,
    capability: str,
    mode: str,
) -> str:
    """Ask the GovernanceEngine to approve/queue the activation.

    Helper for _run_development_pipeline (Issue #951).
    Returns the approval_id (empty string for FULL_AUTO).
    """
    try:
        from skills.governance import GovernanceEngine
        from skills.models import GovernanceMode

        gov = GovernanceEngine(mode=GovernanceMode(mode))
        result = await gov.request_activation(
            skill_name=pkg["name"],
            requested_by=requested_by,
            reason=f"Auto-generated to fill capability gap: {capability}",
            skill_id=skill_id,
        )
        return result.approval_id or ""
    except Exception as exc:
        logger.warning("Governance request failed: %s", exc)
        return ""


async def _promote_and_reload(pkg: Dict[str, Any], skill_id: str) -> bool:
    """Promote the skill to disk and hot-reload the registry.

    Helper for _run_development_pipeline (Issue #951).
    Returns True on success.
    """
    try:
        from skills.promoter import SkillPromoter
        from skills.registry import get_skill_registry

        await SkillPromoter().promote(
            name=pkg["name"],
            skill_md=pkg["skill_md"],
            skill_py=pkg.get("skill_py"),
            auto_commit=False,
        )
        get_skill_registry().reload()
        logger.info("Skill '%s' promoted and hot-reloaded", pkg["name"])
        return True
    except Exception as exc:
        logger.error("Promote/reload failed for '%s': %s", pkg["name"], exc)
        return False
