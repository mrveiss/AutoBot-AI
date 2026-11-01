# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SYSTEM-vault write paths of the Secrets Manager API (#17099, #17731).

`POST /api/secrets/` routes a SYSTEM-visibility secret to the envelope vault.
`PUT` and `DELETE /api/secrets/{id}` must reach the SAME destination, or the
vault copy serves a superseded value / outlives its own deletion. All three
operations live here so the destination is declared once, and every call goes
through `SecretsCoordinator`, whose `authorize()` grants SYSTEM-vault writes to
admins only -- there is no second credential path.

A refused write raises `SecretAccessError` (a `PermissionError`); the handlers
map it to 403 so the admin sees why, rather than a generic 500.
"""

import uuid
from typing import Dict

from fastapi import HTTPException
from sqlalchemy import select

from api.schemas_system import SecretCreateRequest
from autobot_shared.logging_manager import get_logger
from autobot_shared.secrets_vault import VaultKind, VaultRef
from models.secret import Secret

logger = get_logger(__name__)

_SYSTEM_VAULT = VaultRef(VaultKind.SYSTEM)


def _as_uuid(secret_id: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(secret_id)
    except ValueError:
        return None


async def _principal(owner_id: str) -> tuple[uuid.UUID, set[str]]:
    from user_management.middleware.rbac_middleware import rbac_middleware

    user_id = uuid.UUID(owner_id)
    return user_id, set(await rbac_middleware.get_user_permissions(user_id))


def _coordinator_or_none():
    """The shared coordinator, or None when the vault is not configured (503)."""
    from api.envelope_secrets import get_coordinator

    try:
        return get_coordinator()
    except HTTPException as exc:
        if exc.status_code == 503:
            return None
        raise


async def _is_system_secret(session, secret_id: uuid.UUID) -> bool:
    row = await session.execute(
        select(Secret.owner_vault).where(Secret.id == secret_id, Secret.sealed_value.isnot(None))
    )
    owner = row.scalar_one_or_none()
    return owner is not None and VaultRef.parse(owner) == _SYSTEM_VAULT


def _summary(secret: Secret) -> Dict:
    return {
        "id": str(secret.id),
        "name": secret.name,
        "type": secret.type,
        "owner_vault": secret.owner_vault,
        "version": secret.version,
    }


async def create_system_vault_secret(request: SecretCreateRequest, owner_id: str) -> Dict:
    """Route a SYSTEM-visibility secret to EnvelopeSecretsService (#17099).

    Raises ValueError (-> 400) when `value` is missing, and SecretAccessError
    (-> 403) when the caller isn't an admin.
    """
    from api.envelope_secrets import get_coordinator
    from llc.deps import get_session

    if not request.value:
        raise ValueError("value is required for a system-visibility secret")
    user_id, permissions = await _principal(owner_id)
    coordinator = get_coordinator()
    async for session in get_session():
        secret = await coordinator.create(
            session,
            user_id=user_id,
            permissions=permissions,
            owner_vault=_SYSTEM_VAULT,
            name=request.name,
            secret_type=request.type.value,
            plaintext=request.value.encode("utf-8"),
        )
        await session.commit()
        return _summary(secret)
    raise RuntimeError("get_session() yielded no session")  # pragma: no cover -- defensive, generator always yields


async def rotate_system_vault_secret(secret_id: str, value: str | None, owner_id: str) -> Dict | None:
    """Rotate a SYSTEM-vault secret's value; None when `secret_id` is not one.

    A SYSTEM secret has no metadata-only edit, so an update without `value`
    is refused (ValueError -> 400) rather than silently doing nothing.
    """
    from llc.deps import get_session

    vault_id, coordinator = _as_uuid(secret_id), _coordinator_or_none()
    if vault_id is None or coordinator is None:
        return None
    user_id, permissions = await _principal(owner_id)
    async for session in get_session():
        if not await _is_system_secret(session, vault_id):
            return None
        if not value:
            raise ValueError("value is required to update a system-vault secret")
        secret = await coordinator.rotate(
            session, user_id=user_id, permissions=permissions, secret_id=vault_id, new_plaintext=value.encode("utf-8")
        )
        await session.commit()
        return _summary(secret)
    return None  # pragma: no cover -- defensive, generator always yields


async def delete_system_vault_secret(secret_id: str, owner_id: str) -> bool:
    """Delete a SYSTEM-vault secret; False when `secret_id` is not one."""
    from llc.deps import get_session

    vault_id, coordinator = _as_uuid(secret_id), _coordinator_or_none()
    if vault_id is None or coordinator is None:
        return False
    user_id, permissions = await _principal(owner_id)
    async for session in get_session():
        if not await _is_system_secret(session, vault_id):
            return False
        await coordinator.delete(session, user_id=user_id, permissions=permissions, secret_id=vault_id)
        await session.commit()
        return True
    return False  # pragma: no cover -- defensive, generator always yields
