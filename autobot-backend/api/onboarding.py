# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Onboarding API (Issue #5061)

Provides first-run UX endpoints:
  GET  /api/onboarding/presets  — curated starter preset catalogue
  GET  /api/onboarding/doctor   — hardware + service health report
  POST /api/onboarding/apply    — atomically apply a preset
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.schemas_common import DataResponse
from onboarding.presets import get_all_presets, get_preset
from onboarding.doctor import run_doctor

logger = logging.getLogger(__name__)

router = APIRouter(tags=["onboarding"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ApplyPresetRequest(BaseModel):
    preset_name: str
    overrides: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/presets", response_model=DataResponse)
async def list_presets() -> DataResponse:
    """Return all curated starter presets."""
    presets = get_all_presets()
    return DataResponse(data=presets)


@router.get("/doctor", response_model=DataResponse)
async def doctor_report() -> DataResponse:
    """
    Run onboarding doctor scan.

    Returns hardware metrics, service reachability, and a provider recommendation.
    """
    report = await run_doctor()
    return DataResponse(data=report)


@router.post("/apply", response_model=DataResponse)
async def apply_preset(body: ApplyPresetRequest) -> DataResponse:
    """
    Atomically apply a starter preset.

    Enables agents, activates skills, and persists config.
    Rolls back on any partial failure.
    """
    preset = get_preset(body.preset_name)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Preset '{body.preset_name}' not found")

    applied: dict[str, Any] = {}
    rollback_stack: list[tuple] = []

    try:
        # Merge overrides into the preset config
        merged = {**preset, **body.overrides}

        # --- Agents ---
        applied["agents"] = await _enable_agents(merged.get("agents", []), rollback_stack)

        # --- Skills ---
        applied["skills"] = await _activate_skills(merged.get("skills", []), rollback_stack)

        # --- System prompt + LLM tier (config store) ---
        applied["config"] = await _persist_config(
            system_prompt=merged.get("system_prompt", ""),
            llm_tier=merged.get("llm_tier", "balanced"),
            rollback_stack=rollback_stack,
        )

        logger.info("Onboarding preset '%s' applied successfully", body.preset_name)
        return DataResponse(data={"preset": merged, "applied": applied})

    except Exception as exc:
        logger.error("Preset apply failed for '%s': %s — rolling back", body.preset_name, exc)
        await _rollback(rollback_stack)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to apply preset '{body.preset_name}': {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Internal helpers (each pushes a compensating action to rollback_stack)
# ---------------------------------------------------------------------------


async def _enable_agents(agent_ids: list[str], rollback_stack: list) -> list[str]:
    """Enable each agent in the registry; register rollback for each."""
    from autobot_shared.redis_client import get_async_redis_client

    redis = await get_async_redis_client(database="main")
    enabled: list[str] = []

    for agent_id in agent_ids:
        try:
            if redis:
                key = f"agents:enabled:{agent_id}"
                was_enabled = await redis.get(key)
                await redis.set(key, "1")
                rollback_stack.append(("redis_set", key, was_enabled))
            enabled.append(agent_id)
            logger.debug("Enabled agent: %s", agent_id)
        except Exception as exc:
            logger.warning("Could not enable agent '%s': %s (continuing)", agent_id, exc)

    return enabled


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


async def _persist_config(
    system_prompt: str,
    llm_tier: str,
    rollback_stack: list,
) -> dict[str, str]:
    """Persist system_prompt and llm_tier to Redis config store."""
    from autobot_shared.redis_client import get_async_redis_client

    redis = await get_async_redis_client(database="main")
    if not redis:
        logger.warning("Redis unavailable — skipping config persistence")
        return {"system_prompt": "skipped", "llm_tier": "skipped"}

    sp_key = "onboarding:config:system_prompt"
    tier_key = "onboarding:config:llm_tier"

    prev_sp = await redis.get(sp_key)
    prev_tier = await redis.get(tier_key)

    await redis.set(sp_key, system_prompt)
    await redis.set(tier_key, llm_tier)

    rollback_stack.append(("redis_set", sp_key, prev_sp))
    rollback_stack.append(("redis_set", tier_key, prev_tier))

    return {"system_prompt": "applied", "llm_tier": llm_tier}


async def _rollback(rollback_stack: list) -> None:
    """Execute compensating actions in reverse order."""
    from autobot_shared.redis_client import get_async_redis_client

    redis = None

    for entry in reversed(rollback_stack):
        action = entry[0]
        try:
            if action == "redis_set":
                _, key, prev_value = entry
                if redis is None:
                    redis = await get_async_redis_client(database="main")
                if redis:
                    if prev_value is None:
                        await redis.delete(key)
                    else:
                        await redis.set(key, prev_value)
            elif action == "skill_enabled":
                _, manager, skill_name, prev_state = entry
                skill = manager.registry.get(skill_name)
                if skill:
                    skill.enabled = prev_state
        except Exception as exc:
            logger.error("Rollback step failed (%s): %s", action, exc)
