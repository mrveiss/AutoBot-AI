# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which commit a running rollback deploys, and how every playbook run of it learns that (#20214).

``update-all-nodes.yml`` deploys ``deploy_ref`` (default ``main``). A rollback deploys an earlier
commit, through the same updater and the same playbook, by passing that ref as an extra var. The
playbook is run from several places (the SLM self-update, each fleet node, the co-located resync),
across a restart of this very service, so the ref cannot be a parameter threaded through each of
them. It is carried two ways, and neither outlives the rollback:

* a ``ContextVar`` set for the duration of the in-process orchestration (asyncio tasks inherit it,
  including the fire-and-forget self-update task);
* the resume plan the orchestration persists before the self-update restarts this service
  (``api/_resume_plan.py``). The restarted process has no context, so the fleet stage it resumes
  reads the ref from the plan. The plan is deleted when the job ends, and ignored once older than
  its TTL, so a crashed rollback cannot pin an unrelated later run to an old commit.

Nothing here is sticky: with no rollback in flight ``deploy_ref_vars`` is empty and the playbook
deploys ``main``, which is how the next ordinary update moves forward again.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Iterator

from autobot_shared.git_refs import is_safe_ref
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: The one playbook that takes ``deploy_ref``.
ROLLBACK_PLAYBOOK = "update-all-nodes.yml"

#: A rollback target is always the full 40-hex object name the commit list returned.
_FULL_SHA = re.compile(r"[0-9a-f]{40}")

_ROLLBACK_REF: ContextVar[str | None] = ContextVar("slm_rollback_ref", default=None)


def is_full_sha(value: object) -> bool:
    """True for a full lowercase 40-hex commit id that is also a safe git ref."""
    return isinstance(value, str) and bool(_FULL_SHA.fullmatch(value)) and is_safe_ref(value)


@contextmanager
def rollback_scope(commit: str) -> Iterator[None]:
    """Every playbook run started from inside this scope deploys ``commit``."""
    if not is_full_sha(commit):
        raise ValueError("a rollback target must be a full commit id")
    token = _ROLLBACK_REF.set(commit)
    try:
        yield
    finally:
        _ROLLBACK_REF.reset(token)


def current_rollback_ref() -> str | None:
    """The commit of the rollback this task belongs to, or None."""
    return _ROLLBACK_REF.get()


def _plan_is_fresh(plan: dict, ttl_seconds: int) -> bool:
    created = plan.get("created_at")
    try:
        when = datetime.fromisoformat(created)
    except (TypeError, ValueError):
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).total_seconds() <= ttl_seconds


async def _read_plan_ref() -> str | None:
    """The ``deploy_ref`` of the persisted resume plan, when there is a fresh one."""
    try:
        from sqlalchemy import select

        from api._resume_plan import _UPDATE_ALL_RESUME_KEY
        from api.code_sync import _RESUME_PLAN_TTL_SECONDS
        from models.database import Setting
        from services.database import db_service

        async with db_service.session() as db:
            result = await db.execute(select(Setting).where(Setting.key == _UPDATE_ALL_RESUME_KEY))
            setting = result.scalar_one_or_none()
        plan = json.loads(setting.value) if setting else {}
        ref = plan.get("deploy_ref")
        return ref if is_full_sha(ref) and _plan_is_fresh(plan, _RESUME_PLAN_TTL_SECONDS) else None
    except Exception as exc:  # a run that is not a rollback must never fail because this lookup did
        logger.warning("rollback: could not read the resume plan for a deploy ref: %s", type(exc).__name__)
        return None


async def deploy_ref_vars(playbook_name: str) -> dict[str, str]:
    """Extra vars that make ``playbook_name`` deploy the rollback commit; empty outside a rollback."""
    if playbook_name != ROLLBACK_PLAYBOOK:
        return {}
    ref = current_rollback_ref() or await _read_plan_ref()
    if ref is None:
        return {}
    return {"deploy_ref": ref, "deploy_is_rollback": "true"}
