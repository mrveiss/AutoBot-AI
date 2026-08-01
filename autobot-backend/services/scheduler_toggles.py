# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Effective on/off state for every registered background scheduler (GH#12820).

One resolver, used by both the startup path and the running loops, so an operator
toggle and a startup gate can never disagree about whether a job should run.

Layering, highest priority first:

1. **Operator override** — a Redis-backed feature flag set through the admin API.
2. **Registry default** — ``ScheduledJob.default_enabled``, what the job does when
   nobody has expressed a preference.

Redis being unreachable resolves to the registry default rather than failing open
(silently running a job an operator disabled) or failing closed (silently stopping
every background job because the cache blipped). The default is the declared
intent, so it is the only safe thing to fall back to.
"""

from __future__ import annotations

from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from services.scheduler_registry import REGISTRY, ScheduledJob

logger = get_logger(__name__)

# Namespace inside the shared feature-flag keyspace, so scheduler toggles cannot
# collide with the access-control flags that already live there.
FLAG_PREFIX = "scheduler:"


def flag_name(job_name: str) -> str:
    """Feature-flag key for a scheduler, e.g. ``scheduler:SkillDistillationScheduler``."""
    return f"{FLAG_PREFIX}{job_name}"


def get_job(job_name: str) -> ScheduledJob | None:
    """Registry entry for ``job_name``, or ``None`` when it is not registered."""
    return next((job for job in REGISTRY if job.name == job_name), None)


async def is_scheduler_enabled(job_name: str) -> bool:
    """Should ``job_name`` be running right now?

    Callers use this both to gate startup and to re-check inside a loop, so a toggle
    takes effect without a restart.

    An unregistered name resolves to ``False``: the registry is the source of truth
    for what exists, and running something it does not describe is never correct.
    """
    job = get_job(job_name)
    if job is None:
        logger.warning("Scheduler %s is not in the registry; treating as disabled", job_name)
        return False

    try:
        from services.feature_flags import get_feature_flags

        flags = await get_feature_flags()
        return await flags.get_feature(flag_name(job_name), default=job.default_enabled)
    except Exception as exc:
        # get_feature already swallows Redis errors and returns the default; this
        # guards the import/singleton path so a toggle lookup can never take a
        # scheduler down.
        logger.warning(
            "Scheduler toggle lookup failed for %s (%s); using registry default %s",
            job_name,
            exc,
            job.default_enabled,
        )
        return job.default_enabled


async def set_scheduler_enabled(job_name: str, enabled: bool) -> bool:
    """Override ``job_name``'s state. Returns False when it is not registered."""
    if get_job(job_name) is None:
        logger.warning("Refusing to set a toggle for unregistered scheduler %s", job_name)
        return False

    from services.feature_flags import get_feature_flags

    flags = await get_feature_flags()
    return await flags.set_feature(flag_name(job_name), enabled)


async def clear_scheduler_override(job_name: str) -> bool:
    """Drop the override so ``job_name`` reverts to its registry default."""
    if get_job(job_name) is None:
        logger.warning("Refusing to clear a toggle for unregistered scheduler %s", job_name)
        return False

    from services.feature_flags import get_feature_flags

    flags = await get_feature_flags()
    return await flags.clear_feature(flag_name(job_name))


async def _describe(job: ScheduledJob) -> Dict[str, Any]:
    """One job's registry metadata plus its resolved state."""
    from services.feature_flags import get_feature_flags

    override: bool | None = None
    try:
        flags = await get_feature_flags()
        override = await flags.get_feature_override(flag_name(job.name))
    except Exception as exc:
        logger.warning("Could not read override for %s: %s", job.name, exc)

    return {
        "name": job.name,
        "enabled": job.default_enabled if override is None else override,
        "default_enabled": job.default_enabled,
        "override_active": override is not None,
        "interval_seconds": job.interval_seconds,
        "owner_file": job.owner_file,
        "runtime": job.runtime,
        "description": job.description,
        "inert_reason": job.inert_reason,
    }


async def list_scheduler_states() -> List[Dict[str, Any]]:
    """Every registered scheduler with its effective state and where that came from."""
    return [await _describe(job) for job in REGISTRY]
