# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One home for "may this caller steer this workflow?" (#17014).

``ActiveWorkflow.owner_id`` and the WebSocket's ``may_control`` both existed before
this module, and both were inert: no creation path recorded an owner, so every
workflow answered ``owner_id is None``. An owner check against ``None`` admits
nobody, which made the WebSocket admin-only, and the REST control route had no
check at all -- any signed-in user could pause, cancel or approve any workflow.

The identity a workflow records must be the same string the checks compare against,
or the check silently never matches. That is why ``caller_id`` lives here and is
used by both the recording paths and the checking paths, rather than each site
picking its own claim out of the user dict.
"""

from fastapi import HTTPException

from autobot_shared.auth.permissions import is_admin_role
from autobot_shared.logging_manager import get_logger
from constants.error_constants import ERR_WORKFLOW_NOT_FOUND

logger = get_logger(__name__)

# The claims a user dict may carry, in the order a workflow owner is taken from it.
# `get_current_user` returns `user_id` for a session login and for the synthetic
# admin it mints for an internal API-key call; `sub` comes from a run-scoped JWT
# (#6473). `username` is last because it is the only one a caller can change.
_ID_CLAIMS = ("user_id", "sub", "username")


def caller_id(user: dict | None) -> str | None:
    """The identity to record as a workflow's owner, or to compare one against.

    Returns ``None`` when no claim is present, which every check below treats as
    "not the owner" rather than as a wildcard.
    """
    if not user:
        return None
    for claim in _ID_CLAIMS:
        value = user.get(claim)
        if value:
            return str(value)
    return None


def is_owner_or_admin(workflow, user: dict | None) -> bool:
    """Whether *user* may read or steer *workflow*.

    An admin always may. Otherwise the workflow must record an owner **and** that
    owner must match one of the caller's claims. A workflow with no recorded owner
    is steerable only by an admin -- fail closed, because the alternative reading
    ("nobody owns it, so anybody may") is the hole #17014 is about.
    """
    if user and is_admin_role(user.get("role")):
        return True
    owner = getattr(workflow, "owner_id", None)
    if not owner:
        return False
    return owner in {value for claim in _ID_CLAIMS if (value := _claim(user, claim))}


def _claim(user: dict | None, claim: str) -> str | None:
    """One claim off *user* as a string, or None."""
    if not user:
        return None
    value = user.get(claim)
    return str(value) if value else None


def require_owner_or_admin(workflow, user: dict | None) -> None:
    """Raise 403 unless *user* may steer *workflow*."""
    if is_owner_or_admin(workflow, user):
        return
    logger.warning(
        "Refused workflow access: caller %s is not the owner of %s",
        caller_id(user) or "<unidentified>",
        getattr(workflow, "workflow_id", "<unknown>"),
    )
    raise HTTPException(status_code=403, detail="Not authorized for this workflow")


def find_workflow(manager, workflow_id: str, user: dict | None = None):
    """Look up a workflow in the active or completed store, ownership-checked.

    Returns the ``ActiveWorkflow`` or raises 404 when it does not exist, 403 when
    *user* is given and may not access it. Moved here from ``routes.py`` so the
    ownership rule has one implementation (#17014); passing ``user=None`` keeps the
    lookup-only behaviour for internal callers that have already authorised.
    """
    workflow = manager.active_workflows.get(workflow_id) or manager.completed_workflows.get(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=ERR_WORKFLOW_NOT_FOUND)
    if user is not None:
        require_owner_or_admin(workflow, user)
    return workflow
