# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-use access audit for envelope secrets (#18811, umbrella #10088).

``secrets_access_audit`` answers *who can* open a secret; nothing recorded *who did*. The
legacy SQLite store had ``secrets_audit``, the envelope store had no counterpart, so a secret
used as a bearer credential left no trail of its uses. Every use now lands in the canonical
audit trail (``services.audit``: the ``audit_logs`` row is the system of record) as one
SECURITY event, ``secret.access``, carrying the accessor.

**Never a value.** The record takes ids and labels only -- the secret id, the owner, the
accessor, the outcome -- so there is no parameter through which a plaintext, or anything
derived from one, can reach a row (the same structural rule as ``secrets_audit_store``).

The audit bus is imported at call time: the coordinator runs in the minimal migration-gate
environment, where the bus's Redis projection need not import.
"""

from __future__ import annotations

import uuid

#: The resource type every access record names.
SECRET_RESOURCE = "secret"  # nosec B105  # pragma: allowlist secret -- a resource-type label


def record_secret_access(secret_id: uuid.UUID, *, accessor: str, actor_id: str | None, granted: bool) -> bool:
    """Record one use of *secret_id* by *accessor*; ``False`` only if nothing could be scheduled.

    *actor_id* is the secret's owner when the secret exists (the principal the use acts as),
    else ``"unknown"`` -- a presented reference to no secret is still an attempt worth a row.
    """
    from services.audit.audit import emit_security
    from services.audit.taxonomy import AuditAction

    return emit_security(
        AuditAction.SECRET_ACCESS,
        actor_id or "unknown",
        resource_type=SECRET_RESOURCE,
        resource_id=str(secret_id),
        metadata={"accessor": accessor},
        outcome="success" if granted else "failure",
    )
