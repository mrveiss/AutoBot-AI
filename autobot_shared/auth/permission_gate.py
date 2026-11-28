# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ONE ``require_permission`` / ``require_any_permission`` (#18263).

Both services build one ``PermissionGate`` around the FastAPI dependency that
authenticates their caller, and re-export its two factories under the names
their routes already import. The decision is ``permission_evaluator``; this
module only turns it into HTTP:

- no caller: **401**;
- denied: a deny record through the shared RBAC audit writer (the
  ``audit_logs`` table both services already wire, #12925), then **403**.

The factories take ``Permission`` members only. A string raises ``TypeError``
when the dependency is built, which is import time for a route module, and an
unknown member name fails as an ``AttributeError`` before that.
"""

import logging
import uuid
from typing import Any, Callable, Iterable, NoReturn

from fastapi import Depends, HTTPException, Request, status

from autobot_shared.auth.permission_evaluator import (
    DbGrantLoader,
    caller_user_id,
    default_db_loader,
    evaluate_any,
    require_permission_member,
)
from autobot_shared.auth.permissions import Permission

# stdlib logging, not get_logger: the SLM's hermetic auth harnesses stub autobot_shared
# submodules, and this module must import and deny cleanly under them.
logger = logging.getLogger(__name__)


def _subject(caller: dict) -> str | None:
    """The caller's name for the audit record, from whichever claim carries it."""
    for claim in ("username", "sub"):
        if isinstance(caller.get(claim), str):
            return caller[claim]
    return None


async def audit_permission_denied(request: Request, caller: dict, permissions: tuple[Permission, ...]) -> None:
    """Write the deny record. A failing write is logged and counted, never raised."""
    from autobot_shared.user_management.middleware.rbac_middleware import (  # noqa: PLC0415
        _emit_permission_denied_audit,
        _request_audit_context,
    )

    path, ip_address, user_agent = _request_audit_context(request)
    await _emit_permission_denied_audit(
        caller_user_id(caller),
        " | ".join(permission.value for permission in permissions),
        path,
        ip_address=ip_address,
        user_agent=user_agent,
        subject=_subject(caller),
    )


def _count_lost_denial(error_type: str) -> None:
    """Count a lost deny record on the shared audit-loss counter, when the metrics layer is importable."""
    try:
        from autobot_shared.monitoring.metrics.audit import record_audit_write_failure_safely  # noqa: PLC0415
    except Exception as exc:  # the metrics layer can fail to import, not only be absent
        logger.error(
            "permission gate: audit-loss counter unavailable (%s); the loss is only logged", type(exc).__name__
        )
        return
    record_audit_write_failure_safely("permission_denied", error_type)


class PermissionGate:
    """The shared decision bound to one service's caller dependency."""

    def __init__(
        self,
        caller_dependency: Callable[..., Any],
        *,
        wire_rbac: Callable[[], None] = lambda: None,
        load_db_names: DbGrantLoader | None = None,
    ) -> None:
        """*wire_rbac* imports the service's RBAC shim (which calls ``configure_rbac``).

        It runs on first need, not at construction, so importing a service's auth
        module does not drag in its database layer.
        """
        self._caller_dependency = caller_dependency
        self._wire_rbac = wire_rbac
        self._load_db_names = load_db_names or default_db_loader

    async def _wired_db_names(self, user_id: uuid.UUID, org_id: uuid.UUID | None) -> Iterable[str]:
        """The caller's DB grants; an unavailable RBAC wiring grants nothing (fail closed)."""
        try:
            self._wire_rbac()
        except Exception as exc:
            logger.error("permission gate: RBAC wiring unavailable, no DB grants (%s)", type(exc).__name__)
            return ()
        return await self._load_db_names(user_id, org_id)

    def require_permission(self, permission: Permission) -> Callable:
        """Dependency factory: the caller must hold *permission*. Returns the caller."""
        return self.require_any_permission(permission)

    def require_any_permission(self, *permissions: Permission) -> Callable:
        """Dependency factory: the caller must hold at least one of *permissions*."""
        if not permissions:
            raise ValueError("require_any_permission needs at least one Permission")
        for permission in permissions:
            require_permission_member(permission)

        async def _check(request: Request, caller: Any = Depends(self._caller_dependency)) -> dict:
            return await self.enforce(request, caller, permissions)

        return _check

    async def enforce(self, request: Request, caller: Any, permissions: tuple[Permission, ...]) -> dict:
        """Return the caller when allowed; 401 without a caller; audit and 403 when denied."""
        if not caller or not isinstance(caller, dict):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if await evaluate_any(caller, permissions, self._wired_db_names):
            return caller
        await self.deny(request, caller, permissions)

    async def deny(self, request: Request, caller: dict, permissions: tuple[Permission, ...]) -> NoReturn:
        """Audit the denial, then raise 403 -- the 403 whatever happens to the audit record."""
        await self._audit_denial(request, caller, permissions)
        raise self.forbidden(permissions)

    async def _audit_denial(self, request: Request, caller: dict, permissions: tuple[Permission, ...]) -> None:
        """Write the deny record; a record that cannot be written is logged and counted, never raised.

        Same contract as ``_emit_permission_denied_audit`` (#14750): a failing audit must not
        turn a clean 403 into a 500. That covers the wiring import too, which runs on first
        need and can fail where the service's database layer is absent (#18338 train 12b).
        """
        try:
            self._wire_rbac()
            await audit_permission_denied(request, caller, permissions)
        except Exception as exc:
            logger.error("permission gate: deny audit not written (%s)", type(exc).__name__)
            _count_lost_denial(type(exc).__name__)

    @staticmethod
    def forbidden(permissions: tuple[Permission, ...]) -> HTTPException:
        """The 403 for *permissions*, for a caller that has audited the denial its own way."""
        required = " or ".join(permission.value for permission in permissions)
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission denied: {required} required")
