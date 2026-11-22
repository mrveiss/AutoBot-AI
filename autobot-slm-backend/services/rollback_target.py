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
  (``api/_resume_plan.py``). The restarted process has no context, so the resume hook reads the ref
  ONCE from the plan it has already validated (``resume_ref``) and runs the resumed fleet stage inside
  ``rollback_scope`` (``resumed_scope``). A rollback plan without a valid ref fails the job; it never
  deploys ``main``. Playbook runs read only the context, never the stored plan, so an independent
  node sync that happens while a plan exists cannot inherit the rollback's commit.

Nothing here is sticky: with no rollback in flight ``deploy_ref_vars`` is empty and the playbook
deploys ``main``, which is how the next ordinary update moves forward again.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from autobot_shared.git_refs import is_safe_ref

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


class ResumeRefInvalid(Exception):
    """A resumed rollback's plan carries no usable ref; the fleet stage must not run (it would deploy ``main``)."""


def resume_ref(plan: dict) -> str | None:
    """The rollback ref of an already-validated resume plan, or None for an ordinary update.

    Read once, from the plan the resume hook has version- and TTL-checked. A plan that says it is a rollback
    (``is_rollback``, or any ``deploy_ref``) must carry a full commit id; otherwise ``ResumeRefInvalid``.
    """
    ref = plan.get("deploy_ref")
    if not (plan.get("is_rollback") or ref is not None):
        return None
    if not is_full_sha(ref):
        raise ResumeRefInvalid("The resumed rollback has no valid target commit, so the fleet was not updated.")
    return ref


@contextmanager
def resumed_scope(ref: str | None) -> Iterator[None]:
    """The resumed fleet stage: inside ``rollback_scope(ref)`` for a rollback, a pass-through otherwise."""
    if ref is None:
        yield
        return
    with rollback_scope(ref):
        yield


async def deploy_ref_vars(playbook_name: str) -> dict[str, str]:
    """Extra vars that make ``playbook_name`` deploy the rollback commit; empty outside a rollback scope."""
    ref = current_rollback_ref() if playbook_name == ROLLBACK_PLAYBOOK else None
    if ref is None:
        return {}
    return {"deploy_ref": ref, "deploy_is_rollback": "true"}
