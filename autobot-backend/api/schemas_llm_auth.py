# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request/response schemas for ``/api/llm-auth`` (#10551, #11297, #19241).

No request carries a provider URL or client id: both come from the server-side
registry (``llm_shared.llm_oauth_registry``). ``extra="forbid"`` makes a client
that still sends them fail loudly (422) instead of having them silently ignored.
"""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict

#: Where a connection is stored (#19241): the org-shared system credential
#: (admin only) or the calling user's own provider account.
AuthScope = Literal["system", "user"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OAuthInitiateRequest(_Strict):
    """Body for POST /oauth/initiate — starts a server-driven PKCE auth-code flow.

    ``scope`` is required: the caller always says whose connection this is (#19241).
    """

    provider_name: str
    redirect_uri: str
    scope: AuthScope


class OAuthAuthorizeResponse(BaseModel):
    """Return of /oauth/initiate — the provider URL to redirect to + the CSRF state."""

    authorize_url: str
    state: str


class OAuthCallbackRequest(_Strict):
    """Body for POST /oauth/callback — bound to a server-minted, single-use state.

    The verifier, provider, scope and subject are taken from the stored state,
    never from the client, so a lured user cannot inject an attacker's credentials.
    """

    state: str
    code: str
    redirect_uri: str


class OAuthInitiateResponse(BaseModel):
    provider_name: str
    stored: bool
    expires_at: float | None = None
    scope: AuthScope | None = None


class DeviceInitiateRequest(_Strict):
    provider_name: str
    scope: AuthScope


class DeviceInitiateResponse(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class DevicePollRequest(_Strict):
    provider_name: str
    device_code: str


class ProviderAuthStatus(BaseModel):
    provider_name: str
    connected: bool
    expires_at: float | None = None
    auth_kind: str | None = None
    scope: AuthScope | None = None
    #: The provider answered ``invalid_grant``: only a new sign-in restores it (#19241).
    needs_reauth: bool = False
    #: The system connection shown is the token shared by every org (the caller has no org):
    #: only a superadmin can disconnect it, via DELETE /{provider}/shared (#19241).
    shared: bool = False


class ProviderRevokeResult(BaseModel):
    """Return of DELETE /{provider}: the local delete always happens; the provider-side
    RFC 7009 revoke is reported separately (None when no revoke URL is configured)."""

    provider_name: str
    #: ``shared`` is the superadmin's revoke of the legacy token every org may share (#19241).
    scope: Literal["system", "user", "shared"]
    deleted: int
    provider_revoked: bool | None = None
    provider_error: str | None = None


class ProviderListing(BaseModel):
    """One row of GET /providers — setting NAMES only, never a value."""

    name: str
    label: str
    flows: List[Literal["redirect", "device"]]
    configured: bool
    missing_settings: List[str]
