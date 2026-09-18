# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Break-glass repair of a resource no live principal can reach (#15779, #16927).

An orphan -- no live owner, no grant, and a scope key nobody holds -- is denied to
every principal including an admin, and the in-app remedies are gated by the same
check that denies. This is the one audited way out. It is **not** "an admin may
take any resource": a repair is refused unless all three conditions hold, and every
attempt, refused or not, is audited with the conditions it was judged on (#16940).

Owner ruling (#16927): each resource type is repaired through its own service and
its own grant source, never through a generic grant table no access check reads
(the ``resource_grants`` table this replaced). The per-type logic lives in
``orphan_repair_types``; this module holds what they share.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from services.audit_logger import audit_log

logger = get_logger(__name__)

_OPERATION = "resource.repair_orphan"


class OrphanRepairError(Exception):
    """Base for a repair that did not happen. ``conditions`` is what it was judged on."""

    def __init__(self, message: str, conditions: Dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.conditions = conditions or {}


class UnknownResourceType(OrphanRepairError):
    """No repair is defined for this resource type: refused, never guessed."""


class ResourceNotFound(OrphanRepairError):
    """The named resource does not exist."""


class NotAnOrphan(OrphanRepairError):
    """The resource is reachable by some live principal, so a break-glass is not justified."""


class InvalidNewOwner(OrphanRepairError):
    """The owner to assign is not a live user."""


class RepairWriteFailed(Exception):
    """The type's own store did not take the write: a failure, audited ``error``, never a refusal."""


@dataclass(frozen=True)
class Assessment:
    """Whether a resource is an orphan, and the conditions that decided it.

    ``conditions`` names what held (``owner``, ``grant``, ``scope``, and per type
    e.g. ``dead_vaults``) whichever way the verdict went, so a refusal is as legible
    in the audit as a repair. It never carries secret material.
    """

    orphaned: bool
    conditions: Dict[str, Any] = field(default_factory=dict)


class OrphanRepairer(Protocol):
    """One resource type's repair, through that type's own service and grant source."""

    async def assess(self, session: AsyncSession, resource_id: str) -> Assessment:
        """Judge the resource for a repair. Raises ``ResourceNotFound``.

        Where the type's store can, this locks the resource until the transaction
        ends, so the judgment still holds when ``repair`` writes.
        """

    async def repair(
        self, session: AsyncSession, resource_id: str, new_owner_id: str, assessment: Assessment
    ) -> Dict[str, Any]:
        """Make *new_owner_id* the owner; return what changed. Never secret material."""

    async def find_orphans(self, session: AsyncSession, limit: int) -> List[Dict[str, Any]]:
        """The orphans among the first *limit* resources of this type (#15779 AC4)."""


async def find_orphans(
    session: AsyncSession, repairers: Dict[str, OrphanRepairer], resource_type: str, limit: int
) -> List[Dict[str, Any]]:
    """List the orphans of *resource_type*, so they surface before a confused user finds one."""
    repairer = repairers.get(resource_type)
    if repairer is None:
        raise UnknownResourceType(f"no orphan repair is defined for resource type {resource_type!r}")
    return await repairer.find_orphans(session, limit)


async def user_state(session: AsyncSession, user_id: str | None) -> str:
    """``"none"``, ``"live"``, ``"deleted"`` (no row, or ``deleted_at`` set) or ``"unresolvable"``.

    A deactivated user can be reactivated, so is ``"live"``. An id that is not a
    UUID cannot be looked up, so it is ``"unresolvable"``: neither proven dead nor
    proven alive, and the two callers below treat that in opposite directions.
    """
    if not user_id:
        return "none"
    try:
        uid = uuid.UUID(str(user_id))
    except ValueError:
        return "unresolvable"
    from user_management.models.user import User

    user = await session.get(User, uid)
    return "live" if user is not None and user.deleted_at is None else "deleted"


async def owner_blocks_repair(session: AsyncSession, owner_id: str | None) -> tuple[bool, str]:
    """Whether the current owner could still reach the resource, and its state.

    Only a *proven* dead or absent owner allows a repair: an unresolvable one counts
    as live, so a break-glass never fires on a guess.
    """
    state = await user_state(session, owner_id)
    return state in ("live", "unresolvable"), state


async def _audit(result: str, actor: str, resource: str, details: Dict[str, Any]) -> None:
    await audit_log(operation=_OPERATION, result=result, user_id=actor, resource=resource, details=details)


async def repair_orphan(
    session: AsyncSession,
    repairers: Dict[str, OrphanRepairer],
    resource_type: str,
    resource_id: str,
    new_owner_id: str,
    *,
    actor_user_id: str,
) -> Dict[str, Any]:
    """Repair an orphan, or refuse and say why. Every attempt is audited.

    Callers must already have authorized *actor_user_id* as an admin; this function
    decides only whether the *resource* justifies a break-glass.
    """
    resource = f"{resource_type}:{resource_id}"
    try:
        result = await _judge_and_repair(session, repairers, resource_type, resource_id, new_owner_id)
    except OrphanRepairError as exc:
        details = {"refused": type(exc).__name__, "reason": str(exc), **exc.conditions, "new_owner_id": new_owner_id}
        await _audit("denied", actor_user_id, resource, details)
        raise
    except Exception as exc:  # #16940: a break-glass that failed must leave a trace too, not only one refused
        await _audit("error", actor_user_id, resource, {"error": type(exc).__name__, "new_owner_id": new_owner_id})
        raise
    await _audit("success", actor_user_id, resource, result)
    logger.warning("Break-glass orphan repair by %s: %s -> owner %s", actor_user_id, resource, new_owner_id)
    return result


async def _judge_and_repair(
    session: AsyncSession, repairers: Dict[str, OrphanRepairer], resource_type: str, resource_id: str, new_owner: str
) -> Dict[str, Any]:
    repairer = repairers.get(resource_type)
    if repairer is None:
        raise UnknownResourceType(f"no orphan repair is defined for resource type {resource_type!r}")
    if await user_state(session, new_owner) != "live":  # the new owner must be *proven* live
        raise InvalidNewOwner(f"new owner {new_owner!r} is not a live user")
    assessment = await repairer.assess(session, resource_id)
    if not assessment.orphaned:
        raise NotAnOrphan("the resource is reachable by a live principal", assessment.conditions)
    changed = await repairer.repair(session, resource_id, new_owner, assessment)
    return {"conditions": assessment.conditions, **changed, "new_owner_id": new_owner}
