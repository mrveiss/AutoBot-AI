# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Onboarding API (Issue #5061)

Provides first-run UX endpoints:
  GET  /api/onboarding/presets  — curated starter preset catalogue (auth required)
  GET  /api/onboarding/doctor   — hardware + service health report  (auth required)
  POST /api/onboarding/apply    — atomically apply a preset         (admin required)
  GET  /api/onboarding/status   — bootstrap probe — INTENTIONALLY unauthenticated
                                  (frontend router guard calls before login; see #6568)
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from api.schemas_common import DataResponse
from api.schemas_system import ApplyPresetRequest, OnboardingStatus
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.logging_manager import get_logger
from onboarding.doctor import run_doctor
from onboarding.presets import get_all_presets, get_preset

logger = get_logger(__name__)

router = APIRouter(tags=["onboarding"])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/presets", response_model=DataResponse[List[Dict[str, Any]]], dependencies=[Depends(get_current_user)])
async def list_presets() -> DataResponse:
    """Return all curated starter presets.

    Auth-gated (#6568): the preset catalogue exposes platform capability
    info and should not be enumerable pre-login. ``single_user`` deployments
    still pass through via the synthetic admin in ``get_current_user``.
    """
    presets = get_all_presets()
    return DataResponse(data=presets)


@router.get("/doctor", response_model=DataResponse[Dict[str, Any]], dependencies=[Depends(get_current_user)])
async def doctor_report() -> DataResponse:
    """
    Run onboarding doctor scan.

    Returns hardware metrics, service reachability, and a provider recommendation.
    Auth-gated (#6568) — hardware/service info must not leak pre-login.
    """
    report = await run_doctor()
    return DataResponse(data=report)


@router.post(
    "/apply",
    response_model=DataResponse[Dict[str, Any]],
    dependencies=[Depends(check_admin_permission)],
)
async def apply_preset(body: ApplyPresetRequest) -> DataResponse:
    """
    Atomically apply a starter preset.

    All Redis key writes are issued inside a single MULTI/EXEC pipeline
    (``transaction=True``), so a partial failure leaves no half-written
    state in Redis (#6577). In-memory skill state is rolled back via
    compensating actions if the Redis transaction fails.
    """
    preset = get_preset(body.preset_name)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Preset '{body.preset_name}' not found")

    merged = {**preset, **body.overrides}
    agent_ids: list[str] = merged.get("agents", [])
    skill_names: list[str] = merged.get("skills", [])
    system_prompt: str = merged.get("system_prompt", "")
    llm_tier: str = merged.get("llm_tier", "balanced")

    # --- Skills first (in-memory state; compensating rollback needed on failure) ---
    skill_rollback: list[tuple[Any, ...]] = []
    try:
        activated_skills = await _activate_skills(skill_names, skill_rollback)
    except Exception as exc:
        logger.error("Skill activation failed for '%s': %s", body.preset_name, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to activate skills for preset '{body.preset_name}': {exc}",
        ) from exc

    # --- Collect every Redis write in one dict (nothing written yet) ---
    redis_writes: dict[str, str] = {
        **{f"agents:enabled:{a}": "1" for a in agent_ids},
        "onboarding:config:system_prompt": system_prompt,
        "onboarding:config:llm_tier": llm_tier,
        "onboarding:preset_applied": "1",
        "onboarding:preset_name": body.preset_name,
    }

    # --- Execute all writes atomically in a single MULTI/EXEC transaction ---
    try:
        from autobot_shared.redis_client import get_async_redis_client

        redis = await get_async_redis_client(database="main")
        if redis:
            pipe = redis.pipeline(transaction=True)
            for key, value in redis_writes.items():
                pipe.set(key, value)
            await pipe.execute()
        else:
            logger.warning(
                "Redis unavailable — skipping config persistence for preset '%s'",
                body.preset_name,
            )
    except Exception as exc:
        logger.error(
            "Redis transaction failed for preset '%s': %s — rolling back skills",
            body.preset_name,
            exc,
        )
        await _rollback_skills(skill_rollback)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to apply preset '{body.preset_name}': {exc}",
        ) from exc

    logger.info("Onboarding preset '%s' applied successfully", body.preset_name)
    return DataResponse(
        data={
            "preset": merged,
            "applied": {
                "agents": agent_ids,
                "skills": activated_skills,
                "config": {"system_prompt": "applied", "llm_tier": llm_tier},
            },
        }
    )


@router.get("/status", response_model=OnboardingStatus)
async def onboarding_status() -> OnboardingStatus:
    """Return whether a preset has been applied (#6452).

    Used by the frontend router guard to decide whether to redirect new
    users to /onboarding on first login. No auth required — called before
    the main app loads.

    Fail-open: if Redis is unreachable or read fails, return
    ``preset_applied=True`` so users are never trapped in onboarding by
    infrastructure issues.
    """
    from autobot_shared.redis_client import get_async_redis_client

    try:
        redis = await get_async_redis_client(database="main")
        if not redis:
            return OnboardingStatus(preset_applied=True)
        flag = await redis.get("onboarding:preset_applied")
        applied = flag == "1" or flag == b"1"
        name_value = await redis.get("onboarding:preset_name") if applied else None
        if isinstance(name_value, (bytes, bytearray)):
            name_value = name_value.decode("utf-8")
        return OnboardingStatus(preset_applied=applied, preset_name=name_value)
    except Exception as exc:
        logger.warning("Could not read preset_applied flag: %s — failing open", exc)
        return OnboardingStatus(preset_applied=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _activate_skills(skill_names: list[str], rollback_stack: list) -> list[str]:
    """Activate each skill via SkillManager; register rollback for each."""
    try:
        from skills.manager import SkillManager

        manager = SkillManager()
        await manager.initialize()
    except Exception as exc:
        logger.warning("SkillManager unavailable (%s) — skipping skill activation", exc)
        return []

    activated: list[str] = []
    for skill_name in skill_names:
        try:
            skill = manager.registry.get(skill_name)
            if skill:
                prev_state = skill.enabled
                skill.enabled = True
                rollback_stack.append(("skill_enabled", manager, skill_name, prev_state))
                activated.append(skill_name)
                logger.debug("Activated skill: %s", skill_name)
            else:
                logger.debug("Skill '%s' not found in registry — skipping", skill_name)
        except Exception as exc:
            logger.warning("Could not activate skill '%s': %s (continuing)", skill_name, exc)

    return activated


async def _rollback_skills(rollback_stack: list) -> None:
    """Restore in-memory skill state via compensating actions."""
    for entry in reversed(rollback_stack):
        action = entry[0]
        try:
            if action == "skill_enabled":
                _, manager, skill_name, prev_state = entry
                skill = manager.registry.get(skill_name)
                if skill:
                    skill.enabled = prev_state
        except Exception as exc:
            logger.error("Skill rollback step failed (%s): %s", action, exc)
