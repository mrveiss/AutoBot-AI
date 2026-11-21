# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The admin-maintenance principal of ``SecretsCoordinator`` (#17850, #17773, #17038).

Duplicate-secret resolution reads and removes copies in ANY vault, on behalf of an administrator, and only as part of
an approved (or being-proposed) maintenance action. That is neither a user acting on their own secrets nor the
system-vault service principal, so the coordinator gets a third, narrow principal instead of callers reaching the
envelope service themselves:

* **admin only** -- the actor must resolve to an active administrator (``SecretsCoordinator._load_maintenance_actor``);
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

from services.audit.taxonomy import AuditAction
from services.audit_logger import audit_log

if TYPE_CHECKING:
    pass


class MaintenanceAuditError(RuntimeError):
    """The durable audit entry could not be written, so the maintenance operation was not run."""


@dataclass(frozen=True)
class MaintenanceActor:
    """Who a maintenance operation is done for: the administrator and the reason it runs.

    Deliberately carries NO permissions: whether the account is an administrator is read from the stored user
    row (``SecretsCoordinator._load_maintenance_actor``), never from anything a caller supplies.
    """

    admin_id: uuid.UUID
    reference: str  # the approval id, or the request that raised the proposal -- never a secret name


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
