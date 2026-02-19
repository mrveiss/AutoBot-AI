# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Governance Engine (Phase 6)

Enforces FULL_AUTO / SEMI_AUTO / LOCKED modes for skill activation.
Creates approval records and notifies SLM admin via Redis pub/sub.
"""
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from skills.models import GovernanceMode, TrustLevel

logger = logging.getLogger(__name__)
REDIS_APPROVAL_CHANNEL = "skills:approvals:pending"


@dataclass
class ActivationResult:
    """Result of a governance activation request."""

    approved: bool
    requires_human_review: bool
    approval_id: Optional[str] = None
    reason: str = ""
    trust_level: TrustLevel = TrustLevel.MONITORED


class GovernanceEngine:
    """Enforces skill activation governance policy."""

    def __init__(
        self,
        mode: GovernanceMode = GovernanceMode.SEMI_AUTO,
        default_trust: TrustLevel = TrustLevel.MONITORED,
    ) -> None:
        """Initialize with governance mode and default trust level."""
        self.mode = mode
        self.default_trust = default_trust

    async def request_activation(
        self,
        skill_name: str,
        requested_by: str,
        reason: str,
        skill_id: Optional[str] = None,
    ) -> ActivationResult:
        """Process a skill activation request under the current governance mode."""
        if self.mode == GovernanceMode.LOCKED:
            return _locked_result()
        if self.mode == GovernanceMode.FULL_AUTO:
            return ActivationResult(
                approved=True,
                requires_human_review=False,
                reason="full_auto mode",
                trust_level=self.default_trust,
            )
        return await self._create_pending_approval(
            skill_name, requested_by, reason, skill_id=skill_id
        )

    async def approve(
        self,
        approval_id: str,
        admin_id: str,
        trust_level: TrustLevel = TrustLevel.MONITORED,
        notes: str = "",
    ) -> ActivationResult:
        """Admin approves a pending skill activation."""
        logger.info("Skill approved by %s: approval=%s", admin_id, approval_id)
        return ActivationResult(
            approved=True,
            requires_human_review=False,
            approval_id=approval_id,
            reason=f"approved by {admin_id}",
            trust_level=trust_level,
        )

    async def _create_pending_approval(
        self,
        skill_name: str,
        requested_by: str,
        reason: str,
        skill_id: Optional[str] = None,
    ) -> ActivationResult:
        """Create approval record in DB and notify admin (SEMI_AUTO mode).

        Persists a SkillApproval row so the SLM Approvals tab shows pending
        requests even after a page reload.  Redis pub/sub is still published
        for real-time notification.
        """
        approval_id = str(uuid.uuid4())
        resolved_skill_id = skill_id or skill_name
        await _persist_approval(approval_id, resolved_skill_id, requested_by, reason)
        await self._notify_admin(skill_name, approval_id, requested_by, reason)
        return ActivationResult(
            approved=False,
            requires_human_review=True,
            approval_id=approval_id,
            reason="pending admin approval",
        )

    @staticmethod
    async def _notify_admin(
        skill_name: str, approval_id: str, requested_by: str, reason: str
    ) -> None:
        """Publish pending approval to Redis for SLM dashboard notification."""
        try:
            from autobot_shared.redis_client import get_redis_client

            redis = get_redis_client(async_client=True, database="main")
            await redis.publish(
                REDIS_APPROVAL_CHANNEL,
                json.dumps(
                    {
                        "skill_name": skill_name,
                        "approval_id": approval_id,
                        "requested_by": requested_by,
                        "reason": reason,
                    }
                ),
            )
        except Exception as exc:
            logger.warning("Failed to notify admin of skill approval: %s", exc)


async def _persist_approval(
    approval_id: str, skill_id: str, requested_by: str, reason: str
) -> None:
    """Write a SkillApproval row to the skills DB (non-fatal on failure).

    Helper for GovernanceEngine._create_pending_approval (Issue #951).
    """
    try:
        from skills.db import get_skills_engine
        from skills.models import SkillApproval
        from sqlalchemy.ext.asyncio import AsyncSession

        engine = get_skills_engine()
        async with AsyncSession(engine) as session:
            session.add(
                SkillApproval(
                    id=approval_id,
                    skill_id=skill_id,
                    requested_by=requested_by,
                    reason=reason,
                )
            )
            await session.commit()
        logger.debug("SkillApproval %s persisted to DB", approval_id)
    except Exception as exc:
        logger.warning("Failed to persist SkillApproval to DB: %s", exc)


def _locked_result() -> ActivationResult:
    """Return a blocked ActivationResult for LOCKED governance mode."""
    return ActivationResult(
        approved=False,
        requires_human_review=False,
        reason="system is in locked mode — only admin can activate skills",
    )
