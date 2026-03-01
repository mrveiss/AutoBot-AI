# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Setup Wizard API (Issue #1294)

Guided first-run setup wizard for configuring fleet nodes after SLM install.
Tracks wizard progress via the Settings key-value store and orchestrates
node addition, enrollment, role assignment, and fleet provisioning.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.database import db_service
from services.playbook_executor import get_playbook_executor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/setup", tags=["setup-wizard"])

# ── Wizard Steps ────────────────────────────────────────────────────────────

WIZARD_STEPS = [
    "welcome",
    "add_nodes",
    "test_connections",
    "enroll_agents",
    "assign_roles",
    "provision_fleet",
    "verify_health",
    "complete",
]


# ── Schemas ─────────────────────────────────────────────────────────────────


class WizardStatus(BaseModel):
    """Current state of the setup wizard."""

    completed: bool
    current_step: str
    current_step_index: int
    total_steps: int
    steps: list[dict]


class StepCompleteRequest(BaseModel):
    """Request to mark a wizard step as completed."""

    step: str


class ProvisionRequest(BaseModel):
    """Request to provision fleet nodes."""

    node_ids: Optional[list[str]] = None


# ── Settings Helpers ────────────────────────────────────────────────────────


async def _get_setting(key: str, default: str = "") -> str:
    """Read a setting value from the database."""
    from models.database import Setting
    from sqlalchemy import select

    async with db_service.session() as session:
        result = await session.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        return setting.value if setting else default


async def _set_setting(key: str, value: str) -> None:
    """Write a setting value to the database."""
    from models.database import Setting
    from sqlalchemy import select

    async with db_service.session() as session:
        result = await session.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value
        else:
            session.add(Setting(key=key, value=value, value_type="string"))
        await session.commit()


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/status", response_model=WizardStatus)
async def get_wizard_status():
    """Get the current setup wizard status."""
    is_completed = (await _get_setting("setup_wizard_completed")) == "true"
    current_step = await _get_setting("setup_wizard_current_step", "welcome")

    if current_step not in WIZARD_STEPS:
        current_step = "welcome"

    current_index = WIZARD_STEPS.index(current_step)
    completed_steps_raw = await _get_setting("setup_wizard_completed_steps", "")
    completed_steps = (
        set(completed_steps_raw.split(",")) if completed_steps_raw else set()
    )

    steps = []
    for i, step_name in enumerate(WIZARD_STEPS):
        steps.append(
            {
                "name": step_name,
                "index": i,
                "completed": step_name in completed_steps,
                "current": step_name == current_step,
            }
        )

    return WizardStatus(
        completed=is_completed,
        current_step=current_step,
        current_step_index=current_index,
        total_steps=len(WIZARD_STEPS),
        steps=steps,
    )


@router.post("/complete-step")
async def complete_step(request: StepCompleteRequest):
    """Mark a wizard step as completed and advance to the next."""
    step = request.step
    if step not in WIZARD_STEPS:
        raise HTTPException(status_code=400, detail=f"Unknown step: {step}")

    # Add to completed steps
    completed_raw = await _get_setting("setup_wizard_completed_steps", "")
    completed = set(completed_raw.split(",")) if completed_raw else set()
    completed.discard("")
    completed.add(step)
    await _set_setting("setup_wizard_completed_steps", ",".join(sorted(completed)))

    # Advance to next step
    current_index = WIZARD_STEPS.index(step)
    if current_index + 1 < len(WIZARD_STEPS):
        next_step = WIZARD_STEPS[current_index + 1]
        await _set_setting("setup_wizard_current_step", next_step)
    else:
        # Final step — mark wizard as completed
        await _set_setting("setup_wizard_completed", "true")
        await _set_setting("setup_wizard_current_step", "complete")

    logger.info("Setup wizard step completed: %s", step)
    return {"status": "ok", "completed_step": step}


@router.post("/skip")
async def skip_wizard():
    """Skip the setup wizard entirely (mark as completed)."""
    await _set_setting("setup_wizard_completed", "true")
    await _set_setting("setup_wizard_current_step", "complete")
    logger.info("Setup wizard skipped")
    return {"status": "ok", "message": "Setup wizard skipped"}


@router.post("/reset")
async def reset_wizard():
    """Reset the setup wizard to run again."""
    await _set_setting("setup_wizard_completed", "false")
    await _set_setting("setup_wizard_current_step", "welcome")
    await _set_setting("setup_wizard_completed_steps", "")
    logger.info("Setup wizard reset")
    return {"status": "ok", "message": "Setup wizard reset"}


@router.post("/provision-fleet")
async def provision_fleet(request: ProvisionRequest):
    """Trigger fleet provisioning via Ansible.

    Runs the provision-fleet-roles.yml playbook, optionally limited to
    specific node IDs.
    """
    executor = get_playbook_executor()

    extra_vars = {}
    limit = request.node_ids if request.node_ids else None

    logger.info(
        "Starting fleet provisioning (nodes: %s)",
        limit or "all",
    )

    result = await executor.execute_playbook(
        playbook_name="playbooks/provision-fleet-roles.yml",
        limit=limit,
        extra_vars=extra_vars,
    )

    if result.get("success"):
        logger.info("Fleet provisioning completed successfully")
        return {
            "status": "ok",
            "message": "Fleet provisioning completed",
            "output": result.get("output", ""),
        }
    else:
        logger.error("Fleet provisioning failed: %s", result.get("output", ""))
        raise HTTPException(
            status_code=500,
            detail=f"Provisioning failed: {result.get('output', 'unknown error')}",
        )


@router.get("/validate")
async def validate_fleet():
    """Validate that all fleet nodes are healthy.

    Checks the roles/fleet-health endpoint logic to determine if the fleet
    is ready for production use.
    """
    from models.database import Node, NodeRole
    from services.role_registry import DEFAULT_ROLES
    from sqlalchemy import func, select

    async with db_service.session() as session:
        # Count total nodes
        node_count_result = await session.execute(select(func.count(Node.id)))
        total_nodes = node_count_result.scalar() or 0

        # Count online nodes
        online_result = await session.execute(
            select(func.count(Node.id)).where(Node.status == "online")
        )
        online_nodes = online_result.scalar() or 0

        # Check required roles have active assignments
        required_roles = [r["name"] for r in DEFAULT_ROLES if r.get("required")]
        missing_roles = []
        for role_name in required_roles:
            active = await session.execute(
                select(func.count(NodeRole.id)).where(
                    NodeRole.role_name == role_name,
                    NodeRole.status == "active",
                )
            )
            if (active.scalar() or 0) == 0:
                missing_roles.append(role_name)

    health = "healthy"
    if missing_roles:
        health = "critical"
    elif online_nodes < total_nodes:
        health = "degraded"

    return {
        "health": health,
        "total_nodes": total_nodes,
        "online_nodes": online_nodes,
        "missing_required_roles": missing_roles,
        "ready": health in ("healthy", "degraded") and total_nodes > 0,
    }
