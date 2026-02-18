# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Skills Governance API — gap detection, draft management, approvals, and governance config."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from auth_middleware import check_admin_permission
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from skills.db import get_skills_engine
from skills.generator import SkillGenerator
from skills.models import (
    GovernanceConfig,
    GovernanceMode,
    SkillApproval,
    SkillPackage,
    SkillState,
    TrustLevel,
)
from skills.promoter import SkillPromoter
from skills.validator import SkillValidator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter()

_GOVERNANCE_SINGLETON_ID = 1
_STATUS_PENDING = "pending"
_STATUS_APPROVED = "approved"
_STATUS_REJECTED = "rejected"


class GapRequest(BaseModel):
    """Request body for generating a skill to fill a capability gap."""

    task: str = Field(...)
    agent_output: str = Field("")


class ApprovalDecision(BaseModel):
    """Request body for approving or rejecting a skill approval record."""

    approved: bool
    trust_level: TrustLevel = TrustLevel.MONITORED
    notes: str = ""


class GovernanceModeUpdate(BaseModel):
    """Request body for updating the active governance mode."""

    mode: GovernanceMode


async def _get_skill_draft(session: AsyncSession, skill_id: str) -> SkillPackage:
    """Look up a DRAFT SkillPackage by id; raise 404 if not found."""
    result = await session.execute(
        select(SkillPackage).where(SkillPackage.id == skill_id)
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill draft {skill_id} not found")
    return skill


async def _get_approval(session: AsyncSession, approval_id: str) -> SkillApproval:
    """Look up a SkillApproval by id; raise 404 if not found."""
    result = await session.execute(
        select(SkillApproval).where(SkillApproval.id == approval_id)
    )
    approval = result.scalar_one_or_none()
    if approval is None:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found")
    return approval


def _governance_default() -> Dict[str, Any]:
    """Return the default governance configuration dict."""
    return {"mode": "semi_auto", "gap_detection_enabled": True}


@router.post("/gaps", summary="Generate a skill to fill a capability gap")
async def detect_gap(
    req: GapRequest,
    _: None = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Use the SkillGenerator to produce a draft skill for the described task."""
    gen = SkillGenerator()
    try:
        pkg = await gen.generate(req.task)
    except Exception as exc:  # intentionally broad: LLM call can fail in many ways
        logger.warning("Skill generation failed: %s", exc)
        return {"success": False, "errors": [str(exc)], "draft": None}

    validator = SkillValidator()
    result = await validator.validate(pkg["skill_md"], pkg.get("skill_py"))

    if not result.valid:
        return {
            "success": False,
            "errors": result.errors,
            "draft": pkg,
        }

    engine = get_skills_engine()
    skill = SkillPackage(
        name=pkg["name"],
        skill_md=pkg["skill_md"],
        skill_py=pkg.get("skill_py"),
        manifest=pkg.get("manifest", {}),
        state=SkillState.DRAFT,
        gap_reason=req.task,
    )
    async with AsyncSession(engine) as session:
        session.add(skill)
        await session.commit()
        await session.refresh(skill)

    logger.info("Created skill draft: %s (gap: %s)", skill.name, req.task)
    return {
        "success": True,
        "draft_id": skill.id,
        "name": skill.name,
        "tools_found": result.tools_found,
    }


@router.get("/drafts", summary="List all skill drafts")
async def list_drafts() -> List[Dict[str, Any]]:
    """Return all SkillPackage records in DRAFT state."""
    engine = get_skills_engine()
    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(SkillPackage).where(SkillPackage.state == SkillState.DRAFT)
        )
        drafts = result.scalars().all()
    return [
        {
            "id": d.id,
            "name": d.name,
            "version": d.version,
            "gap_reason": d.gap_reason,
            "created_at": d.created_at,
            "trust_level": d.trust_level,
        }
        for d in drafts
    ]


@router.post("/drafts/{skill_id}/test", summary="Validate a skill draft")
async def test_draft(
    skill_id: str,
    _: None = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Run the SkillValidator against an existing draft and return results."""
    engine = get_skills_engine()
    async with AsyncSession(engine) as session:
        skill = await _get_skill_draft(session, skill_id)
        skill_md = skill.skill_md
        skill_py: Optional[str] = skill.skill_py

    result = await SkillValidator().validate(skill_md, skill_py)
    return {
        "valid": result.valid,
        "errors": result.errors,
        "tools_found": result.tools_found,
    }


@router.post("/drafts/{skill_id}/promote", summary="Promote a draft skill to builtin")
async def promote_draft(
    skill_id: str,
    _: None = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Promote an approved draft skill to the builtin skills directory."""
    engine = get_skills_engine()
    async with AsyncSession(engine) as session:
        skill = await _get_skill_draft(session, skill_id)
        if skill.state != SkillState.DRAFT:
            raise HTTPException(
                status_code=409,
                detail=f"Skill '{skill.name}' is already in state '{skill.state}', not DRAFT",
            )

    async with AsyncSession(engine) as gs:
        cfg_row = await gs.scalar(select(GovernanceConfig))
        mode = cfg_row.mode if cfg_row else GovernanceMode.SEMI_AUTO

    if mode == GovernanceMode.SEMI_AUTO:
        async with AsyncSession(engine) as as_:
            approval = await as_.scalar(
                select(SkillApproval)
                .where(SkillApproval.skill_id == skill_id)
                .where(SkillApproval.status == _STATUS_APPROVED)
            )
        if approval is None:
            raise HTTPException(
                status_code=403,
                detail="Governance is SEMI_AUTO: skill must be approved before promotion",
            )

    async with AsyncSession(engine) as session:
        skill = await _get_skill_draft(session, skill_id)
        try:
            promoted_path = await SkillPromoter().promote(
                name=skill.name,
                skill_md=skill.skill_md,
                skill_py=skill.skill_py,
            )
        except (
            Exception
        ) as exc:  # intentionally broad: promoter can fail due to FS/git/IO errors
            logger.error("Skill promotion failed for '%s': %s", skill.name, exc)
            raise HTTPException(
                status_code=500, detail=f"Promotion failed: {exc}"
            ) from exc
        skill.state = SkillState.BUILTIN
        skill.promoted_at = datetime.now(timezone.utc)
        await session.commit()

    logger.info("Promoted skill %s to builtin: %s", skill.name, promoted_path)
    return {"promoted": True, "path": promoted_path, "name": skill.name}


@router.get("/approvals", summary="List pending skill approvals")
async def list_approvals() -> List[Dict[str, Any]]:
    """Return all SkillApproval records with status 'pending'."""
    engine = get_skills_engine()
    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(SkillApproval).where(SkillApproval.status == _STATUS_PENDING)
        )
        approvals = result.scalars().all()
    return [
        {
            "id": a.id,
            "skill_id": a.skill_id,
            "requested_by": a.requested_by,
            "requested_at": a.requested_at,
            "reason": a.reason,
            "status": a.status,
        }
        for a in approvals
    ]


@router.post("/approvals/{approval_id}", summary="Approve or reject a skill approval")
async def decide_approval(
    approval_id: str,
    body: ApprovalDecision,
    _: None = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Update an approval record with an approve or reject decision."""
    engine = get_skills_engine()
    async with AsyncSession(engine) as session:
        approval = await _get_approval(session, approval_id)
        approval.status = _STATUS_APPROVED if body.approved else _STATUS_REJECTED
        approval.notes = body.notes
        approval.reviewed_at = datetime.now(timezone.utc)
        await session.commit()

    logger.info("Approval %s set to: %s", approval_id, approval.status)
    return {"approval_id": approval_id, "status": approval.status}


@router.get("/governance", summary="Get current governance configuration")
async def get_governance() -> Dict[str, Any]:
    """Return the active GovernanceConfig, or the default if none exists."""
    engine = get_skills_engine()
    async with AsyncSession(engine) as session:
        result = await session.execute(select(GovernanceConfig))
        config = result.scalar_one_or_none()
    if config is None:
        return _governance_default()
    return {
        "mode": config.mode,
        "default_trust_level": config.default_trust_level,
        "gap_detection_enabled": config.gap_detection_enabled,
        "self_generation_enabled": config.self_generation_enabled,
        "updated_at": config.updated_at,
    }


@router.put("/governance", summary="Update the governance mode")
async def update_governance(
    body: GovernanceModeUpdate,
    _: None = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """Update the governance mode in GovernanceConfig (upsert singleton row)."""
    engine = get_skills_engine()
    async with AsyncSession(engine) as session:
        result = await session.execute(select(GovernanceConfig))
        config = result.scalar_one_or_none()
        if config is None:
            config = GovernanceConfig(id=_GOVERNANCE_SINGLETON_ID, mode=body.mode)
            session.add(config)
        else:
            config.mode = body.mode
            config.updated_at = datetime.now(timezone.utc)
        await session.commit()

    logger.info("Governance mode updated to: %s", body.mode)
    return {"mode": body.mode}
