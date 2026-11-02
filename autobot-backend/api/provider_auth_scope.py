# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who a provider connection belongs to, for ``/api/llm-auth`` (#11497, #19241).

Two scopes:

- ``system`` — the org-shared credential (``org_vault_subject``), admin only.
- ``user`` — the caller's own provider account (``user_vault_subject``); any
  authenticated user, and only ever their own.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException, Request, status

from auth_middleware import check_admin_permission
from autobot_shared.deployment_profile import try_frontend_url
from autobot_shared.principal import resolve_principal_id
from autobot_shared.ssot_config import config
from llm_shared.provider_auth import org_vault_subject, user_vault_subject

SCOPE_SYSTEM = "system"
SCOPE_USER = "user"
_ZERO_UUID = "00000000-0000-0000-0000-000000000000"
_DEFAULT_PORTS = {"http": 80, "https": 443}  # URL-scheme defaults, not service ports
#: The SPA route a provider redirects back to. Mirrored by ``PROVIDER_OAUTH_CALLBACK_PATH``
#: in autobot-frontend/src/utils/providerOAuth.ts -- change both together.
PROVIDER_OAUTH_CALLBACK_PATH = "/preferences/oauth/callback"


def principal_id(user: Any) -> str | None:
    """The caller's id via the canonical claim order (``resolve_principal_id``: id → user_id → sub).

    Object principals (tests / non-dict callers) are read in the same order.
    """
    if isinstance(user, dict):
        return resolve_principal_id(user)
    for claim in ("id", "user_id", "sub"):
        value = getattr(user, claim, None)
        if value:
            return str(value)
    return None


def current_user_id(user: Any) -> str:
    """Return the calling principal's id as a string, or the zero-UUID when absent.

    Uses :func:`principal_id` (the canonical claim order, #13688/#19241). The
    zero-UUID is returned only for a genuinely id-less principal — otherwise the
    #11297 binding would collapse every real caller to the same id.
    """
    return principal_id(user) or _ZERO_UUID


def current_org_id(user: Any) -> str | None:
    """Return the caller's org/tenant id, or None when not multi-tenant (#11497 finding #1)."""
    if isinstance(user, dict):
        org = user.get("org_id")
    else:
        org = getattr(user, "org_id", None) or getattr(user, "organization_id", None)
    return str(org) if org is not None else None


async def provider_caller_is_admin(request: Request) -> bool:
    """FastAPI dependency: True for an admin, False for an authenticated non-admin.

    Delegates to the canonical ``check_admin_permission``; only its 403 becomes
    False — a 401 (unauthenticated / revoked token) still propagates.
    """
    try:
        return await check_admin_permission(request)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            return False
        raise


def resolve_provider_auth_scope(requested: str | None, is_admin: bool) -> str:
    """The effective scope: *requested*, else system for an admin and user otherwise. 403 on a non-admin system."""
    scope = requested or (SCOPE_SYSTEM if is_admin else SCOPE_USER)
    if scope == SCOPE_SYSTEM and not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="system-level sign-in requires admin")
    return scope


def subject_for(scope: str, user: Any) -> str:
    """Vault subject for *scope*. A user scope needs a real user id (401 otherwise)."""
    if scope == SCOPE_SYSTEM:
        return org_vault_subject(current_org_id(user))
    uid = principal_id(user)
    if not uid or uid == _ZERO_UUID:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="caller has no user id")
    return user_vault_subject(uid)


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    return (scheme, (parsed.hostname or "").lower(), parsed.port or _DEFAULT_PORTS.get(scheme))


def validate_redirect_uri(redirect_uri: str) -> None:
    """Require *redirect_uri* to be exactly the SPA callback on the SSOT frontend origin (#19241); 400 otherwise."""
    parsed = urlparse(redirect_uri)
    exact = parsed.path == PROVIDER_OAUTH_CALLBACK_PATH and not (parsed.query or parsed.fragment or parsed.params)
    frontend = try_frontend_url(config)
    if frontend is None:  # AUTOBOT_FRONTEND_SERVED_BY unset or unknown: no origin to compare against (#19326)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="the frontend origin is not configured"
        )
    if not parsed.hostname or not exact or _origin(redirect_uri) != _origin(frontend):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="redirect_uri must be the frontend's provider sign-in callback",
        )
