# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""HTTP surface for the unified envelope secrets store (#10088 / Task 2.4 part 2).

A thin FastAPI shell over :class:`SecretsCoordinator` (which does the real
resolve→authorize→service work). Mounted at ``/api/v2/secrets`` on a new prefix,
so the legacy ``/secrets`` (file-store) router is untouched until Task 3 migrates
it. Three injectable dependencies keep handlers trivial and the router
unit-testable in isolation:

- ``principal`` — the caller's ``(user_id, permissions)`` from the auth
  middleware + RBAC; 401 when unauthenticated.
- ``get_session`` — the Postgres ``AsyncSession`` (gated by ``postgres_required``).
- ``get_coordinator`` — the ``SecretsCoordinator``; 503 when the root key is unset.

Coordinator exceptions map to HTTP: ``SecretNotFoundError``→404,
``SecretAccessError``→403, ``ValueError`` (bad vault ref / owner-grant revoke)→400.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from auth_middleware import get_auth_middleware
from autobot_shared.secrets_vault import VaultRef
from llc.deps import get_session
from models.secret import Secret
from services.secrets_coordinator import SecretsCoordinator
from services.unified_secrets_service import SecretAccessError, SecretNotFoundError

router = APIRouter()

_coordinator: SecretsCoordinator | None = None


def get_coordinator() -> SecretsCoordinator:
    """The shared coordinator; 503 if ``AUTOBOT_SECRETS_ROOT_KEY`` is not configured."""
    global _coordinator
    if _coordinator is None:
        try:
            _coordinator = SecretsCoordinator()
        except RuntimeError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "unified secrets store not configured") from exc
    return _coordinator


async def principal(request: Request) -> tuple[uuid.UUID, set[str]]:
    """Resolve the caller to ``(user_id, permission_names)``; 401 when unauthenticated."""
    user = get_auth_middleware().get_user_from_request(request)
    if not user or not user.get("user_id"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    user_id = uuid.UUID(str(user["user_id"]))
    from user_management.middleware.rbac_middleware import rbac_middleware

    permissions = await rbac_middleware.get_user_permissions(user_id)
    return user_id, set(permissions)


def _vault(value: str) -> VaultRef:
    try:
        return VaultRef.parse(value)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid vault reference: {value!r}") from exc


def _mapped(exc: Exception) -> HTTPException:
    if isinstance(exc, SecretNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, SecretAccessError):
        return HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    raise exc


class CreateSecretBody(BaseModel):
    owner_vault: str
    name: str
    secret_type: str
    value: str


class ShareBody(BaseModel):
    grantee: str


class RotateBody(BaseModel):
    value: str


class SecretMetadata(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    owner_vault: str | None
    version: int

    @classmethod
    def of(cls, secret: Secret) -> "SecretMetadata":
        return cls(
            id=secret.id, name=secret.name, type=secret.type, owner_vault=secret.owner_vault, version=secret.version
        )


class SecretValue(BaseModel):
    value: str


class VaultAccessOut(BaseModel):
    vault: str
    kind: str
    id: str | None
    members: list[str]


class SecretAccessOut(BaseModel):
    secret_id: str
    owner_vault: str
    grants: list[VaultAccessOut]
    effective_users: list[str]

    @classmethod
    def of(cls, report) -> "SecretAccessOut":
        return cls(
            secret_id=report.secret_id,
            owner_vault=report.owner_vault,
            grants=[VaultAccessOut(vault=g.vault, kind=g.kind, id=g.id, members=g.members) for g in report.grants],
            effective_users=report.effective_users,
        )


class DependentOut(BaseModel):
    dependent_kind: str
    dependent_id: str
    company_id: str | None


class SecretDependenciesOut(BaseModel):
    secret_id: str
    dependents: list[DependentOut]

    @classmethod
    def of(cls, secret_id: uuid.UUID, deps) -> "SecretDependenciesOut":
        return cls(
            secret_id=str(secret_id),
            dependents=[
                DependentOut(
                    dependent_kind=d.dependent_kind,
                    dependent_id=d.dependent_id,
                    company_id=str(d.company_id) if d.company_id else None,
                )
                for d in deps
            ],
        )


@router.post("", response_model=SecretMetadata, status_code=status.HTTP_201_CREATED)
async def create_secret(
    body: CreateSecretBody,
    who: tuple[uuid.UUID, set[str]] = Depends(principal),
    session: AsyncSession = Depends(get_session),
    coordinator: SecretsCoordinator = Depends(get_coordinator),
) -> SecretMetadata:
    user_id, perms = who
    try:
        secret = await coordinator.create(
            session,
            user_id=user_id,
            permissions=perms,
            owner_vault=_vault(body.owner_vault),
            name=body.name,
            secret_type=body.secret_type,
            plaintext=body.value.encode("utf-8"),
        )
        await session.commit()
    except (SecretAccessError, SecretNotFoundError, ValueError) as exc:
        raise _mapped(exc)
    return SecretMetadata.of(secret)


@router.get("", response_model=list[SecretMetadata])
async def list_secrets(
    who: tuple[uuid.UUID, set[str]] = Depends(principal),
    session: AsyncSession = Depends(get_session),
    coordinator: SecretsCoordinator = Depends(get_coordinator),
) -> list[SecretMetadata]:
    user_id, perms = who
    secrets = await coordinator.list(session, user_id=user_id, permissions=perms)
    return [SecretMetadata.of(s) for s in secrets]


@router.get("/{secret_id}", response_model=SecretValue)
async def read_secret(
    secret_id: uuid.UUID,
    who: tuple[uuid.UUID, set[str]] = Depends(principal),
    session: AsyncSession = Depends(get_session),
    coordinator: SecretsCoordinator = Depends(get_coordinator),
) -> SecretValue:
    user_id, perms = who
    try:
        value = await coordinator.read(session, user_id=user_id, permissions=perms, secret_id=secret_id)
    except (SecretAccessError, SecretNotFoundError) as exc:
        raise _mapped(exc)
    return SecretValue(value=value.decode("utf-8"))


@router.get("/{secret_id}/access", response_model=SecretAccessOut)
async def secret_access(
    secret_id: uuid.UUID,
    who: tuple[uuid.UUID, set[str]] = Depends(principal),
    session: AsyncSession = Depends(get_session),
    coordinator: SecretsCoordinator = Depends(get_coordinator),
) -> SecretAccessOut:
    """Who can access this secret: owner + every grantee vault, resolved to member users."""
    user_id, perms = who
    try:
        report = await coordinator.describe_access(session, user_id=user_id, permissions=perms, secret_id=secret_id)
    except (SecretAccessError, SecretNotFoundError, ValueError) as exc:
        raise _mapped(exc)
    return SecretAccessOut.of(report)


@router.get("/{secret_id}/dependencies", response_model=SecretDependenciesOut)
async def secret_dependencies(
    secret_id: uuid.UUID,
    who: tuple[uuid.UUID, set[str]] = Depends(principal),
    session: AsyncSession = Depends(get_session),
    coordinator: SecretsCoordinator = Depends(get_coordinator),
) -> SecretDependenciesOut:
    """What depends on this secret: every service/agent/workflow consumer (rotation-impact list)."""
    user_id, perms = who
    try:
        deps = await coordinator.describe_dependencies(session, user_id=user_id, permissions=perms, secret_id=secret_id)
    except (SecretAccessError, SecretNotFoundError, ValueError) as exc:
        raise _mapped(exc)
    return SecretDependenciesOut.of(secret_id, deps)


@router.put("/{secret_id}", response_model=SecretMetadata)
async def rotate_secret(
    secret_id: uuid.UUID,
    body: RotateBody,
    who: tuple[uuid.UUID, set[str]] = Depends(principal),
    session: AsyncSession = Depends(get_session),
    coordinator: SecretsCoordinator = Depends(get_coordinator),
) -> SecretMetadata:
    user_id, perms = who
    try:
        secret = await coordinator.rotate(
            session, user_id=user_id, permissions=perms, secret_id=secret_id, new_plaintext=body.value.encode("utf-8")
        )
        await session.commit()
    except (SecretAccessError, SecretNotFoundError) as exc:
        raise _mapped(exc)
    return SecretMetadata.of(secret)


@router.delete("/{secret_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_secret(
    secret_id: uuid.UUID,
    who: tuple[uuid.UUID, set[str]] = Depends(principal),
    session: AsyncSession = Depends(get_session),
    coordinator: SecretsCoordinator = Depends(get_coordinator),
) -> None:
    user_id, perms = who
    try:
        await coordinator.delete(session, user_id=user_id, permissions=perms, secret_id=secret_id)
        await session.commit()
    except (SecretAccessError, SecretNotFoundError) as exc:
        raise _mapped(exc)


@router.post("/{secret_id}/share", status_code=status.HTTP_201_CREATED)
async def share_secret(
    secret_id: uuid.UUID,
    body: ShareBody,
    who: tuple[uuid.UUID, set[str]] = Depends(principal),
    session: AsyncSession = Depends(get_session),
    coordinator: SecretsCoordinator = Depends(get_coordinator),
) -> dict[str, str]:
    user_id, perms = who
    try:
        await coordinator.share(
            session, user_id=user_id, permissions=perms, secret_id=secret_id, grantee=_vault(body.grantee)
        )
        await session.commit()
    except (SecretAccessError, SecretNotFoundError) as exc:
        raise _mapped(exc)
    return {"status": "shared", "grantee": body.grantee}


@router.delete("/{secret_id}/share/{grantee}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share(
    secret_id: uuid.UUID,
    grantee: str,
    who: tuple[uuid.UUID, set[str]] = Depends(principal),
    session: AsyncSession = Depends(get_session),
    coordinator: SecretsCoordinator = Depends(get_coordinator),
) -> None:
    user_id, perms = who
    try:
        await coordinator.revoke(
            session, user_id=user_id, permissions=perms, secret_id=secret_id, grantee=_vault(grantee)
        )
        await session.commit()
    except (SecretAccessError, SecretNotFoundError, ValueError) as exc:
        raise _mapped(exc)
