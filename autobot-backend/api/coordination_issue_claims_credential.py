# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The issue-claims client credential: minted, verified and revoked through the secrets manager (#18811).

Owner decision 2026-10-18: the claims CLI authenticates with a scoped credential held in the
canonical secrets manager, never a token file.

* **Mint** (``POST /coordination/issue-claims/credentials``): a human, with a fresh login JWT,
  mints one for THEMSELVES -- any human user, admin not required, bound to their own username.
  The service principal, an auth-disabled caller, and any non-login token are refused. The
  verifier is created as a secret in the minter's own user vault (``SecretsCoordinator.create``)
  with a ``service:issue-claims-api`` dependency edge (``register_dependency``), and returned
  ONCE as ``<secret_id>.<verifier>``: a reference plus a proof, never the password or the JWT.
* **Use**: the credential travels in its own header, ``X-AutoBot-Claims-Credential``. The generic
  auth middleware reads only ``Authorization`` / session / dev headers, so it never sees this one:
  on any other route the request is anonymous (401), and presented as a ``Bearer`` it is not a JWT
  (401). Only :func:`claims_principal`, the issue-claims routes' dependency, reads it, and it
  refuses outside ``/api/coordination/issue-claims``. Each use is verified against the store
  (``SecretsCoordinator.verify_bearer``: constant-time, live, owner active, audited), with no
  cache, and a password change since minting voids it.
* **Revoke** (``DELETE /coordination/issue-claims/credentials``, presenting the credential): the
  secret is deleted (``SecretsCoordinator.delete``), so every session holding it is cut off on its
  next request. An admin revokes it the same way through ``DELETE /api/v2/secrets/{secret_id}``.
* **Expiry**: ``AUTOBOT_ISSUE_CLAIMS_CREDENTIAL_TTL_S`` (default 7 days) sets the secret's
  ``expires_at``. A reboot clears the keyring but not the vault, so a credential the CLI can no
  longer present stops verifying on its own instead of staying live until someone revokes it.
* **One per user**: minting deletes the user's previous live claims credentials in the same
  commit (each audited as a revoke, reason ``superseded``), so a user holds at most one. Mints for
  one user are serialised by a transaction-scoped Postgres advisory lock taken before that read,
  so two concurrent mints cannot both see "none live" and both commit (:func:`_lock_minting`).
* **Failed checks** are limited and audited per source by
  :mod:`api.coordination_issue_claims_throttle`: past the limit a presentation is refused (429)
  before any lookup, and the misses of a window are ONE audit event with their count.
"""

from __future__ import annotations

import secrets
import time
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

import auth_middleware
from api.coordination_issue_claims_throttle import FailureThrottle, client_source
from api.schemas_issue_claims import ClaimsCredentialResponse, ClaimsCredentialRevokedResponse
from auth_revocation import reject_if_revoked_by_password_change
from autobot_shared.auth.permissions import Role
from autobot_shared.coordination.issue_claims_api import API_PATH as CLAIMS_PATH_PREFIX
from autobot_shared.coordination.issue_claims_api import CREDENTIAL_HEADER
from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.secrets_envelope import DecryptionError
from autobot_shared.secrets_vault import VaultKind, VaultRef
from autobot_shared.time_utils import now_utc
from llc.deps import get_session
from models.secret import Secret
from security.human_admin import refuse_service_principal
from services.audit.audit import emit_security
from services.audit.taxonomy import AuditAction
from services.envelope_secrets_service import SecretAccessError, SecretNotFoundError

logger = get_logger(__name__)

router = APIRouter(prefix="/issue-claims", tags=["issue-claims"])

CLAIMS_SECRET_TYPE = "issue_claims_client"  # nosec B105  # pragma: allowlist secret -- a secret TYPE label
CLAIMS_AUTH_METHOD = "issue_claims_credential"
#: The consumer named in the secret's dependency edge and in every access record.
CLAIMS_DEPENDENT_ID = "issue-claims-api"
_VERIFIER_BYTES = 32
#: How long a minted credential verifies; bounds one orphaned by a reboot (the keyring is cleared).
CREDENTIAL_TTL_S = env_int_clamped("AUTOBOT_ISSUE_CLAIMS_CREDENTIAL_TTL_S", 604800, min_v=3600, max_v=7776000)
_STORE_DOWN = (SQLAlchemyError, OSError, DecryptionError)
#: Failed checks per source: limited, then refused before any lookup; audited as one event per window.
THROTTLE = FailureThrottle(accessor=CLAIMS_DEPENDENT_ID)


def _unauthorized(detail: str = "Invalid issue-claims credential") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail)


def compose_credential(secret_id: uuid.UUID, verifier: str) -> str:
    """The one string the CLI keeps: the secret reference, then the verifier."""
    return f"{secret_id}.{verifier}"


def parse_credential(presented: str) -> tuple[uuid.UUID, str] | None:
    """``(secret_id, verifier)``, or ``None`` for anything not shaped like a credential."""
    ref, sep, verifier = presented.strip().partition(".")
    if not sep or not 20 <= len(verifier) <= 128:
        return None
    try:
        return uuid.UUID(ref), verifier
    except ValueError:
        return None


def _coordinator():
    """The canonical secrets coordinator; 503 when the secrets store is not configured."""
    from api.envelope_secrets import get_coordinator

    return get_coordinator()


async def _check_presented(session: AsyncSession, parsed: tuple[uuid.UUID, str], request: Request) -> Secret | None:
    """The secret a well-formed credential proves, or ``None``; a miss is left to the throttle to audit."""
    accessor = f"{CLAIMS_DEPENDENT_ID}:{request.method} {request.url.path}"
    try:
        return await _coordinator().verify_bearer(
            session,
            secret_id=parsed[0],
            presented=parsed[1].encode("utf-8"),
            secret_type=CLAIMS_SECRET_TYPE,
            accessor=accessor,
            record_failure=False,
        )
    except SecretAccessError:
        return None
    except _STORE_DOWN as exc:
        logger.error("issue-claims credential check reached no verdict (%s); refusing", type(exc).__name__)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "credential store unavailable") from exc


async def _verified_secret(session: AsyncSession, presented: str, request: Request) -> Secret:
    """The claims-client secret *presented* proves possession of; 401 otherwise, 429 when throttled."""
    source = client_source(request)
    await THROTTLE.refuse_if_throttled(source)  # before parsing, so a refused source costs no lookup
    parsed = parse_credential(presented)
    secret = await _check_presented(session, parsed, request) if parsed is not None else None
    if secret is None:
        await THROTTLE.record_failure(source)
        raise _unauthorized()
    return secret


async def _credential_user(secret: Secret) -> dict:
    """The principal a verified credential acts as: the user who minted it."""
    meta = secret.extra_data or {}
    username = str(meta.get("username") or "")
    if not username:
        raise _unauthorized()
    # A password change since minting voids the credential, exactly as it voids a login JWT.
    await reject_if_revoked_by_password_change({"sub": meta.get("sub") or username, "iat": meta.get("minted_at")})
    return {
        "username": username,
        "user_id": str(secret.owner_id),
        "role": Role.USER.value,
        "auth_method": CLAIMS_AUTH_METHOD,
        "claims_credential_id": str(secret.id),
    }


async def canonical_caller(request: Request) -> dict:
    """The canonical gate, looked up at call time; it admits the internal key as a ``service`` principal."""
    return await auth_middleware.get_current_user(request)


async def claims_principal(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    """The issue-claims routes' caller: the claims credential if presented, else the canonical gate."""
    presented = request.headers.get(CREDENTIAL_HEADER)
    if presented is None:
        return await auth_middleware.get_current_user(request)
    if not request.url.path.startswith(CLAIMS_PATH_PREFIX):
        raise _unauthorized("The issue-claims credential is valid only on issue-claims routes")
    return await _credential_user(await _verified_secret(session, presented, request))


def _minting_human(request: Request, user: dict) -> uuid.UUID:
    """The user id of a human with a fresh login; 403 for anything else."""
    refuse_service_principal(request)
    if user.get("service") or user.get("auth_disabled"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "A claims credential is minted by a signed-in person")
    if user.get("auth_method") != "jwt" or not user.get("login_token") or not user.get("username"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Minting needs a login token")
    try:
        return uuid.UUID(str(user.get("user_id")))
    except ValueError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "A claims credential needs a user account") from exc


#: Namespace of the per-user advisory lock that serialises minting (one live credential per user).
MINT_LOCK_NAMESPACE = "issue-claims-mint"


async def _lock_minting(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Hold a per-user lock until this transaction ends, so read-revoke-create cannot interleave.

    Postgres, the backend's store, takes ``pg_advisory_xact_lock``. SQLite (the test store) has no
    advisory locks; its database-wide write lock is the serialisation there.
    """
    if session.get_bind().dialect.name != "postgresql":
        return
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"{MINT_LOCK_NAMESPACE}:{user_id}"},
    )


async def _revoke_previous(session: AsyncSession, coordinator, user_id: uuid.UUID) -> list[uuid.UUID]:
    """Delete the user's live claims-client secrets, so the one being minted is their only one."""
    own_vault = VaultRef(VaultKind.USER, str(user_id)).to_str()
    held = await coordinator.list(session, user_id=user_id, permissions=set())
    live = [
        s.id
        for s in held
        if s.type == CLAIMS_SECRET_TYPE and s.owner_vault == own_vault and s.is_active and not s.is_expired
    ]
    for secret_id in live:
        await coordinator.delete(session, user_id=user_id, permissions=set(), secret_id=secret_id)
    return live


async def _store_credential(
    session: AsyncSession, user_id: uuid.UUID, user: dict, verifier: str
) -> tuple[Secret, list[uuid.UUID]]:
    """Replace the minter's live credential with *verifier*, with its consumer edge; committed.

    Returns the new secret and the ids of the credentials it superseded, deleted in the same commit.
    """
    coordinator, username = _coordinator(), str(user["username"])
    await _lock_minting(session, user_id)
    superseded = await _revoke_previous(session, coordinator, user_id)
    meta = {"username": username, "sub": user.get("sub") or username, "minted_at": int(time.time())}
    secret = await coordinator.create(
        session,
        user_id=user_id,
        permissions=set(),
        owner_vault=VaultRef(VaultKind.USER, str(user_id)),
        name=f"issue-claims client for {username}",
        secret_type=CLAIMS_SECRET_TYPE,
        plaintext=verifier.encode("utf-8"),
        extra_data=meta,
        expires_at=now_utc() + timedelta(seconds=CREDENTIAL_TTL_S),
    )
    await coordinator.register_dependency(
        session,
        user_id=user_id,
        permissions=set(),
        secret_id=secret.id,
        dependent_kind="service",
        dependent_id=CLAIMS_DEPENDENT_ID,
    )
    await session.commit()
    return secret, superseded


def _audit_mint(username: str, secret_id: uuid.UUID, superseded: list[uuid.UUID]) -> None:
    """One revoke event per superseded credential, then the mint."""
    for old_id in superseded:
        emit_security(
            AuditAction.CLAIMS_CREDENTIAL_REVOKE,
            username,
            resource_type="secret",
            resource_id=str(old_id),
            metadata={"reason": "superseded", "superseded_by": str(secret_id)},
        )
    emit_security(AuditAction.CLAIMS_CREDENTIAL_MINT, username, resource_type="secret", resource_id=str(secret_id))


@router.post("/credentials", response_model=ClaimsCredentialResponse, status_code=status.HTTP_201_CREATED)
async def mint_credential(
    request: Request, user: dict = Depends(canonical_caller), session: AsyncSession = Depends(get_session)
) -> ClaimsCredentialResponse:
    """Mint the caller's own issue-claims credential; the value is returned this once."""
    user_id, username = _minting_human(request, user), str(user.get("username") or "")
    verifier = secrets.token_urlsafe(_VERIFIER_BYTES)
    try:
        secret, superseded = await _store_credential(session, user_id, user, verifier)
    except SecretAccessError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not authorized to write to your own vault") from exc
    _audit_mint(username, secret.id, superseded)
    credential = compose_credential(secret.id, verifier)
    return ClaimsCredentialResponse(credential=credential, secret_id=str(secret.id), username=username)


@router.delete("/credentials", response_model=ClaimsCredentialRevokedResponse)
async def revoke_credential(
    user: dict = Depends(claims_principal), session: AsyncSession = Depends(get_session)
) -> ClaimsCredentialRevokedResponse:
    """Revoke the presented credential in the secrets manager: every session holding it is cut off."""
    if user.get("auth_method") != CLAIMS_AUTH_METHOD:
        raise _unauthorized("Present the issue-claims credential to revoke it")
    owner_id, secret_id = uuid.UUID(user["user_id"]), uuid.UUID(user["claims_credential_id"])
    try:
        await _coordinator().delete(session, user_id=owner_id, permissions=set(), secret_id=secret_id)
        await session.commit()
    except (SecretAccessError, SecretNotFoundError) as exc:
        raise _unauthorized() from exc
    emit_security(
        AuditAction.CLAIMS_CREDENTIAL_REVOKE, str(owner_id), resource_type="secret", resource_id=str(secret_id)
    )
    return ClaimsCredentialRevokedResponse(revoked=True, secret_id=str(secret_id))
