# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The admin-maintenance principal of ``SecretsCoordinator`` (#17850, #17773, #17038).

Duplicate-secret resolution reads and removes copies in ANY vault, on behalf of an administrator, and only as part of
an approved (or being-proposed) maintenance action. That is neither a user acting on their own secrets nor the
system-vault service principal, so the coordinator gets a third, narrow principal instead of callers reaching the
envelope service themselves:

* **admin only** -- the actor must resolve to an active administrator (:func:`require_maintenance_admin`);
* **attributable** -- every call names the administrator and a reference (the approval id, or the request that
  raised the proposal), both written to the audit row;
* **audited first** -- a durable audit entry is committed BEFORE the read or the delete; when it cannot be written
  the operation does not run (:class:`MaintenanceAuditError`), so a credential is never opened or destroyed
  without its paper trail.

Approval stays mandatory for removal: this module authorizes a principal, the approval queue authorizes the action.
Ids only are recorded -- never a name or a value.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from autobot_shared.user_management.login_eligibility import login_refusal
from services.audit.taxonomy import AuditAction
from services.audit_logger import audit_log
from services.envelope_secrets_service import SecretAccessError
from services.secrets_principal_resolver import ADMIN_PERMISSION

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class MaintenanceAuditError(RuntimeError):
    """The durable audit entry could not be written, so the maintenance operation was not run."""


@dataclass(frozen=True)
class MaintenanceActor:
    """Who a maintenance operation is done for: the administrator and the reason it runs.

    Deliberately carries NO permissions: whether the account is an administrator is read from the stored RBAC
    tables (:func:`require_maintenance_admin`), never from anything a caller supplies.
    """

    admin_id: uuid.UUID
    reference: str  # the approval id, or the request that raised the proposal -- never a secret name


async def require_maintenance_admin(session: "AsyncSession", actor: MaintenanceActor) -> None:
    """Refuse unless *actor* is an existing, eligible user whose STORED roles grant the admin permission.

    Both facts come from the database: the account through the same eligibility rule the login uses
    (``login_refusal``: not deleted, not inactive), the admin permission through ``UserService.get_user_permissions``
    (the user's roles' platform grants). A user id that does not exist, an ineligible account, or a user without
    the admin role is refused -- whatever the caller claims.
    """
    from user_management.models import User
    from user_management.services.user_service import UserService

    user = await session.get(User, actor.admin_id)
    if user is None or login_refusal(user) is not None:
        raise SecretAccessError("secret maintenance is for an active administrator")
    if ADMIN_PERMISSION not in await UserService(session).get_user_permissions(actor.admin_id):
        raise SecretAccessError("secret maintenance is for an active administrator")


async def audit_maintenance(operation: str, secret_id: uuid.UUID, actor: MaintenanceActor) -> None:
    """Commit the audit entry for *operation* on *secret_id* before it runs; raises when it cannot be written."""
    written = await audit_log(
        AuditAction.SECRET_ACCESS.value,
        result="attempted",
        user_id=str(actor.admin_id),
        resource=f"secret:{secret_id}",
        details={"operation": f"maintenance_{operation}", "reference": actor.reference},
        durable=True,
    )
    if not written:
        raise MaintenanceAuditError(f"the audit entry for maintenance {operation} could not be written")
