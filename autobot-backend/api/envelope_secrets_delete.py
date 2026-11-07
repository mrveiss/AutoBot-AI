# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Envelope-store credential deletes: dependents refused, intent and outcome recorded (#20640).

``DELETE /api/secrets/{id}`` refuses a SYSTEM-vault secret that still has dependents
and records the intent before the write and the outcome after it (#20557). The two
envelope deletes (``DELETE /api/v2/secrets/{id}`` and the service-identity
``DELETE /api/v2/secrets/system/{id}``) reached the same store with neither. Both now
go through :func:`audited_delete`, which reuses the main route's 409
(``secrets_system_vault.refuse_dependents``) and audit adapter (``secrets_audit``),
so one operation behaves the same on every route.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request

from api.secrets_audit import audit_secret_op
from api.secrets_system_vault import refuse_dependents
from autobot_shared.logging_manager import get_logger
from services.envelope_secrets_service import SecretAccessError, SecretNotFoundError

logger = get_logger(__name__)


async def audited_delete(
    request: Request,
    secret_id: uuid.UUID,
    *,
    dependents: Callable[[], Awaitable[list]] | None,
    delete: Callable[[], Awaitable[None]],
    **who: str,
) -> None:
    """Record the intent, refuse while ``dependents()`` lists any, delete, record the outcome.

    ``dependents=None`` skips the check (a human has seen the list and confirmed). The
    first record says ``attempted`` and, when it cannot be written, nothing is deleted
    (503): the credential is never destroyed without its paper trail (#17038). A refusal
    or failure is recorded as ``denied`` / ``failed`` and re-raised for the route to map.
    ``who`` are identifiers only (e.g. ``service``), never a value.
    """
    ref = str(secret_id)
    await audit_secret_op("DELETE", ref, request, "attempted", required=True, phase="before_write", **who)
    try:
        if dependents is not None:
            refuse_dependents(await dependents())
        await delete()
    except HTTPException as exc:
        reason = "has_dependents" if exc.status_code == 409 else "http_%d" % exc.status_code
        await audit_secret_op("DELETE", ref, request, "denied", reason=reason, **who)
        raise
    except SecretAccessError:
        await audit_secret_op("DELETE", ref, request, "denied", reason="permission_denied", **who)
        raise
    except SecretNotFoundError:
        await audit_secret_op("DELETE", ref, request, "failed", reason="not_found", **who)
        raise
    except Exception as exc:
        await audit_secret_op("DELETE", ref, request, "failed", reason=type(exc).__name__, **who)
        raise
    await audit_secret_op("DELETE", ref, request, phase="completed", **who)


async def delete_as_user(request, session, coordinator, secret_id, user_id, permissions, confirm, mapped) -> None:
    """The user route: dependents are refused (409) unless a human ``confirm``-ed the listing.

    ``mapped`` turns a coordinator exception into the route's HTTP error (``_mapped``).
    """

    async def delete() -> None:
        await coordinator.delete(session, user_id=user_id, permissions=permissions, secret_id=secret_id)
        await session.commit()

    async def dependents() -> list:
        return await coordinator.describe_dependencies(
            session, user_id=user_id, permissions=permissions, secret_id=secret_id
        )

    try:
        await audited_delete(request, secret_id, dependents=None if confirm else dependents, delete=delete)
    except (SecretAccessError, SecretNotFoundError) as exc:
        raise mapped(exc)


async def delete_as_service(request, session, coordinator, secret_id, service_id: str, vault, mapped) -> None:
    """The service route: an automatic actor cannot confirm past dependents (#17038)."""
    logger.info("service CRUD: delete system secret", extra={"service_id": service_id})

    async def delete() -> None:
        await coordinator.service_delete(session, secret_id=secret_id, vault=vault)
        await session.commit()

    async def dependents() -> list:
        return await coordinator.service_describe_dependencies(session, secret_id=secret_id, vault=vault)

    try:
        await audited_delete(request, secret_id, dependents=dependents, delete=delete, service=service_id)
    except (SecretAccessError, SecretNotFoundError) as exc:
        raise mapped(exc)
