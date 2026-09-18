# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tell a person's interactive login apart from every other credential (#17042).

A human-in-the-loop approval is a paper trail only if a person decided it. The
backend resolves many credentials into the same user-dict shape, so the shape
alone proves nothing:

- the internal service key (``service: True``),
- run and device JWTs (``auth_method`` ``run_jwt`` / ``device_jwt``),
- the auth-disabled stand-in (``auth_disabled: True``) and the dev header,
- and any HS256 token signed with the platform key for another purpose — an
  SLM MFA-pending token, the backend's SLM service token, a device JWT on the
  fallback secret — which the JWT path resolves as ``auth_method="jwt"``.

This module admits only a session or a login JWT whose claims carry no purpose
marker, and denies everything else, including anything it does not recognise.
It is stdlib-only so any service can import it.
"""

from typing import Any, Mapping, Optional

#: Claims that appear only on tokens minted for something other than a finished
#: human login. Presence of any one of them, whatever its value, disqualifies.
NON_LOGIN_CLAIMS = frozenset(
    {
        "aud",  # run / device JWTs are audience-bound; login tokens are not
        "device_id",  # device JWTs
        "mfa_pending",  # SLM temp token issued before the second factor
        "run_id",  # run JWTs
        "scope",  # run / device JWTs carry a scoped grant
        "service",  # service-to-service tokens
        "token_type",  # device-token-service tokens
    }
)

#: Credential kinds a person produces by logging in.
_INTERACTIVE_AUTH_METHODS = frozenset({"jwt", "session"})

#: Username prefixes the backend gives its synthetic principals.
_NON_HUMAN_USERNAME_PREFIXES = ("service:", "run:", "device:")


def is_login_token(claims: Mapping[str, Any]) -> bool:
    """True when verified JWT *claims* carry none of :data:`NON_LOGIN_CLAIMS`."""
    return NON_LOGIN_CLAIMS.isdisjoint(claims)


def is_interactive_human(user: Optional[Mapping[str, Any]]) -> bool:
    """True only for a person's interactive login; deny-by-default otherwise.

    A JWT user must also carry ``login_token: True``, which the backend's JWT
    extraction sets from :func:`is_login_token` — a ``jwt`` user without that
    positive marker is refused, not assumed human.
    """
    if not user or user.get("service") or user.get("auth_disabled"):
        return False
    method = user.get("auth_method")
    if method not in _INTERACTIVE_AUTH_METHODS:
        return False
    if method == "jwt" and user.get("login_token") is not True:
        return False
    username = str(user.get("username") or "")
    return not username.startswith(_NON_HUMAN_USERNAME_PREFIXES)
