# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pending-skill tracking for async Phase 3 gap-fill (#7431, ADR-006).

When StrategyPlanner.bind_skills (Phase 1, #7432) finds no skill for a
task's intent, this module's ``trigger_gap_fill`` records a pending
binding and fires Phase 3 of skill_router (research → autonomous-skill-
development → governance → register) as a background task.

The mapping ``pending_skill_id → (intent, plan_id, task_id)`` lives here
so:

1. The autonomous-skill-development pipeline can correlate generated
   skills back to the requests that triggered them.
2. The blocked-plan resumer can find every plan/task waiting on a given
   intent when a ``skill_promoted`` event fires.

Storage: in-memory dict, no persistence. Pending bindings that survive a
restart are lost; the plan stays BLOCKED until manual try_resume_blocked_plan
or restart-time discovery picks it up.
"""

import asyncio
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


@dataclass
class PendingSkillBinding:
    """One in-flight Phase 3 gap-fill request."""

    pending_skill_id: str
    intent: str
    plan_id: str
    task_id: str
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class PendingSkillsRegistry:
    """Process-local registry of in-flight Phase 3 gap-fill requests.

    Thread-safe. Used by bind_skills (writes) and the resume path (reads,
    deletes). Singleton via ``get_pending_skills_registry()``.
    """

    def __init__(self) -> None:
        self._bindings: Dict[str, PendingSkillBinding] = {}
        self._lock = threading.Lock()

    def register(self, intent: str, plan_id: str, task_id: str, **metadata: Any) -> PendingSkillBinding:
        """Generate a pending_skill_id and record the binding.

        Returns the constructed ``PendingSkillBinding`` so callers can
        attach ``pending_skill_id`` to the task immediately."""
        pid = str(uuid.uuid4())
        binding = PendingSkillBinding(
            pending_skill_id=pid,
            intent=intent,
            plan_id=plan_id,
            task_id=task_id,
            metadata=metadata,
        )
        with self._lock:
            self._bindings[pid] = binding
        logger.debug(
            "registered pending skill binding %s for plan %s task %s intent %r",
            pid,
            plan_id,
            task_id,
            intent[:80],
        )
        return binding

    def get(self, pending_skill_id: str) -> PendingSkillBinding | None:
        """Look up a pending binding by id. Returns None if unknown or cleared."""
        with self._lock:
            return self._bindings.get(pending_skill_id)

    def clear(self, pending_skill_id: str) -> bool:
        """Remove a binding once the corresponding skill has been generated
        and the waiting task resumed. Returns True if a binding was removed."""
        with self._lock:
            existed = pending_skill_id in self._bindings
            self._bindings.pop(pending_skill_id, None)
        return existed

    def find_by_intent(self, intent: str) -> List[PendingSkillBinding]:
        """Return all bindings whose intent matches exactly. Used by the
        resume path to find every plan/task waiting for a freshly generated
        skill that addresses this intent."""
        with self._lock:
            return [b for b in self._bindings.values() if b.intent == intent]

    def size(self) -> int:
        """Current count of in-flight bindings (diagnostics)."""
        with self._lock:
            return len(self._bindings)

    def all_bindings(self) -> List[PendingSkillBinding]:
        """Snapshot of all current bindings (diagnostics / dashboards)."""
        with self._lock:
            return list(self._bindings.values())


_singleton: PendingSkillsRegistry | None = None
_singleton_lock = threading.Lock()


def get_pending_skills_registry() -> PendingSkillsRegistry:
    """Process-wide singleton accessor."""
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = PendingSkillsRegistry()
    return _singleton


def reset_pending_skills_registry_for_tests() -> None:
    """Test-only: drop the singleton so each test starts clean."""
    global _singleton
    with _singleton_lock:
        _singleton = None


async def trigger_gap_fill(
    intent: str,
    plan_id: str,
    task_id: str,
    *,
    router_call: Callable[[str], Awaitable[Dict[str, Any]]] | None = None,
) -> PendingSkillBinding:
    """Fire-and-forget Phase 3 trigger.

    Records a pending binding, schedules an async background task that
    invokes ``router_call(intent)`` (typically ``skill_router.execute(
    "find_skill", {"task": intent})`` with NO ``dry_run`` so Phase 3 runs
    skill-researcher → autonomous-skill-development → governance →
    register), and returns immediately.

    The background task's completion does NOT clear the pending binding —
    that's the resume path's job. Failures in the background gap-fill
    are logged; the binding remains so observability surfaces stuck IDs.

    Returns the ``PendingSkillBinding`` so the caller can attach
    ``pending_skill_id`` to the task and BLOCK the plan synchronously.
    """
    registry = get_pending_skills_registry()
    binding = registry.register(intent, plan_id, task_id)

    if router_call is None:
        logger.warning(
            "trigger_gap_fill called without router_call; binding %s recorded but no Phase 3 invoked",
            binding.pending_skill_id,
        )
        return binding

    async def _background_phase3() -> None:
        try:
            result = await router_call(intent)
            logger.info(
                "Phase 3 background gap-fill completed for pending %s: success=%s build_triggered=%s",
                binding.pending_skill_id,
                result.get("success"),
                result.get("build_triggered"),
            )
        except Exception as exc:
            logger.warning(
                "Phase 3 background gap-fill failed for pending %s: %s",
                binding.pending_skill_id,
                exc,
            )

    asyncio.create_task(_background_phase3())
    return binding
