# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Disconnecting a provider sign-in: who loses what, the provider-side revoke, the audit row (#19241).

Owner decision (2026-10-23, recorded on #19241):

- a **user** disconnect deletes the caller's own token;
- an **org admin's system** disconnect deletes the org's token and leaves a
  per-org stop marker, so that org stops falling back to the shared legacy
  ``"global"`` token while other orgs keep it;
- an **org-less admin's system** disconnect (its subject IS ``"global"``) is
  refused with 403 and audited as ``denied``: that is the shared token;
- a **superadmin's shared** revoke deletes the ``"global"`` token itself.

Each one revokes at the provider (RFC 7009) only the grant it actually deletes,
reports a provider-side failure without skipping the local change, and writes
one SECURITY event to the canonical audit trail. The event carries the
principal, provider, scope, the kind of subject (never its id or any token) and
the result.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from api.provider_auth_scope import SCOPE_SYSTEM, current_user_id, subject_for
from api.schemas_llm_auth import ProviderRevokeResult
from autobot_shared.logging_manager import get_logger
from llm_shared.llm_oauth_registry import build_provider
from llm_shared.provider_auth import (
    LEGACY_FALLBACK_STOP_KEY,
    LEGACY_SUBJECT,
    USER_SUBJECT_PREFIX,
    _vault_read,
    _vault_secret_name,
    _vault_write,
)
from services.audit.audit import emit_security
from services.audit.taxonomy import AuditAction

logger = get_logger(__name__)

_SYSTEM_VAULT = "system"
SCOPE_SHARED = "shared"
#: What a revoke did to the stored copy (``none`` for a refused attempt).
LOCAL_DELETED, LOCAL_MARKED, LOCAL_NONE = "deleted", "marked", "none"
#: What the provider said: revoked, failed, no revoke URL, or not attempted (refused).
PROVIDER_REVOKED, PROVIDER_FAILED, PROVIDER_NOT_CONFIGURED = "revoked", "failed", "not_configured"
PROVIDER_NOT_ATTEMPTED = "not_attempted"


def stops_legacy_fallback(scope: str) -> bool:
    """A system disconnect replaces the org's token with a stop marker; a user or shared one deletes.

    The legacy ``"global"`` token is shared by every org still falling back to it
    (#11497), so an org's disconnect must not delete it. Deleting it is the
    superadmin's shared revoke alone (owner decision on #19241).
    """
    return scope == SCOPE_SYSTEM


def refuses_shared_subject(scope: str, subject: str) -> bool:
    """An org-less admin's system subject IS ``"global"``: only the superadmin shared revoke may touch it."""
    return scope == SCOPE_SYSTEM and subject == LEGACY_SUBJECT


def subject_kind(subject: str) -> str:
    """``user`` / ``org`` / ``legacy`` -- what the audit row records instead of the subject id."""
    if subject.startswith(USER_SUBJECT_PREFIX):
        return "user"
    return "legacy" if subject == LEGACY_SUBJECT else "org"


async def revoke_one(url: str, client: Any, token_data: dict) -> None:
    """RFC 7009 revoke of one stored grant (the refresh token when there is one)."""
    from api import provider_auth as pa  # noqa: PLC0415  # the guarded POST lives with the endpoints

    hint = "refresh_token" if token_data.get("refresh_token") else "access_token"
    payload = {**pa._client_auth(client), "token": token_data.get(hint, ""), "token_type_hint": hint}

    async def _check(r) -> None:
        if r.status >= 400:
            raise await pa._error_detail(r, "Revocation endpoint")

    await pa._post_form(url, payload, "Revocation endpoint", _check)


async def revoke_at_provider(provider_name: str, grants: list[dict]) -> tuple[bool | None, str | None]:
    """``(revoked, error)`` for the provider-side revoke; ``(None, None)`` when no revoke URL is set."""
    from api import provider_auth as pa  # noqa: PLC0415

    url = build_provider(provider_name).revocation_url
    if not url or not grants:
        return None, None
    try:
        pa._validate_outbound_url(url)
        client = pa._resolve_client(provider_name, None)
        for token_data in grants:
            await revoke_one(url, client, token_data)
    except HTTPException as exc:
        logger.warning("Provider-side revoke failed for %s: %s", provider_name, exc.detail)
        return False, str(exc.detail)
    return True, None


def _provider_outcome(revoked: bool | None) -> str:
    if revoked is None:
        return PROVIDER_NOT_CONFIGURED
    return PROVIDER_REVOKED if revoked else PROVIDER_FAILED


def audit_disconnect(user: Any, provider_name: str, scope: str, subject: str, result: dict[str, str]) -> None:
    """One SECURITY audit event per disconnect/revoke attempt -- never a token, never a subject id.

    *result* carries ``local``, ``provider_revoke`` and ``outcome`` (success / partial / denied).
    """
    metadata = {"provider": provider_name, "scope": scope, "subject_kind": subject_kind(subject)}
    metadata.update(local=result["local"], provider_revoke=result["provider_revoke"])
    written = emit_security(
        AuditAction.PROVIDER_SIGNIN_REVOKE,
        current_user_id(user),
        resource_type="llm_provider_signin",
        resource_id=provider_name,
        metadata=metadata,
        outcome=result["outcome"],
    )
    if not written:
        # emit() schedules the write onto the canonical trail; False means nothing could be scheduled.
        logger.warning("Audit event for the %s %s disconnect could not be written", provider_name, scope)


def _refuse_shared_subject(user: Any, provider_name: str) -> None:
    """403 for an org-less admin's system disconnect, audited as ``denied`` with no side effect."""
    refused = {"local": LOCAL_NONE, "provider_revoke": PROVIDER_NOT_ATTEMPTED, "outcome": "denied"}
    audit_disconnect(user, provider_name, SCOPE_SYSTEM, LEGACY_SUBJECT, refused)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "This account has no organisation, so its system sign-in is the token shared by every "
            f"organisation. Only a superadmin can revoke it: DELETE /api/llm-auth/{provider_name}/shared"
        ),
    )


async def _read_grant(session: Any, provider_name: str, subject: str) -> list[dict]:
    grant = await _vault_read(session, provider_name=provider_name, subject=subject, owner_vault_str=_SYSTEM_VAULT)
    return [grant] if grant and grant.get("access_token") else []  # a stop marker is not a grant


async def _delete(session: Any, provider_name: str, subject: str) -> None:
    from sqlalchemy import delete  # noqa: PLC0415

    from models.secret import Secret  # noqa: PLC0415

    name = _vault_secret_name(provider_name, subject)
    await session.execute(delete(Secret).where(Secret.name == name, Secret.owner_vault == _SYSTEM_VAULT))


async def _mark(session: Any, provider_name: str, subject: str, user: Any) -> None:
    marker = {LEGACY_FALLBACK_STOP_KEY: True, "created_by": current_user_id(user)}
    await _vault_write(
        session,
        provider_name=provider_name,
        subject=subject,
        owner_vault_str=_SYSTEM_VAULT,
        token_data=marker,
        created_by_id=current_user_id(user),
    )


async def _finish(session: Any, user: Any, provider_name: str, scope: str, subject: str, grants: list[dict]):
    """Provider revoke (only for *grants*), then mark or delete, commit and audit."""
    revoked, error = await revoke_at_provider(provider_name, grants)
    marked = stops_legacy_fallback(scope)
    await (_mark(session, provider_name, subject, user) if marked else _delete(session, provider_name, subject))
    await session.commit()
    outcome = "success" if revoked is not False else "partial"
    result = {"local": LOCAL_MARKED if marked else LOCAL_DELETED, "provider_revoke": _provider_outcome(revoked)}
    audit_disconnect(user, provider_name, scope, subject, {**result, "outcome": outcome})
    logger.info("Revoked provider auth for %s (scope=%s, provider_revoked=%s)", provider_name, scope, revoked)
    return ProviderRevokeResult(
        provider_name=provider_name, scope=scope, deleted=len(grants), provider_revoked=revoked, provider_error=error
    )


async def disconnect(session: Any, user: Any, provider_name: str, scope: str) -> ProviderRevokeResult:
    """The caller's own (user) or their org's (system) disconnect; never the shared token (403)."""
    subject = subject_for(scope, user)
    if refuses_shared_subject(scope, subject):
        _refuse_shared_subject(user, provider_name)
    return await _finish(
        session, user, provider_name, scope, subject, await _read_grant(session, provider_name, subject)
    )


async def revoke_shared(session: Any, user: Any, provider_name: str) -> ProviderRevokeResult:
    """Superadmin: delete the shared legacy ``"global"`` token and revoke it at the provider."""
    grants = await _read_grant(session, provider_name, LEGACY_SUBJECT)
    return await _finish(session, user, provider_name, SCOPE_SHARED, LEGACY_SUBJECT, grants)


__all__ = [
    "SCOPE_SHARED",
    "audit_disconnect",
    "disconnect",
    "revoke_at_provider",
    "revoke_one",
    "revoke_shared",
    "refuses_shared_subject",
    "stops_legacy_fallback",
    "subject_kind",
]
