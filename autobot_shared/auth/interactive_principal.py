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

This module admits only a session or a login JWT, and denies everything else,
including anything it does not recognise. A login JWT is known by *positive*
evidence — the ``token_type`` its mint sets — not by the absence of other
claims, which would fail open for any future token type carrying none of them.
It is stdlib-only so any service can import it.
"""

from typing import Any, Mapping, Optional

#: ``token_type`` every login mint sets (backend ``create_jwt_token``). A token
#: issued before 2026-09-18 lacks it and is not a login here until re-issued.
LOGIN_TOKEN_TYPE = "login"  # nosec B105  # a JWT token_type label, not a credential (#17042)

#: Claims that appear only on tokens minted for something other than a finished
#: human login. Presence of any one of them, whatever its value, disqualifies
#: even a token that also says ``token_type: login``.
NON_LOGIN_CLAIMS = frozenset(
    {
        "aud",  # run / device JWTs are audience-bound; login tokens are not
        "device_id",  # device JWTs
        "mfa_pending",  # SLM temp token issued before the second factor
        "run_id",  # run JWTs
        "scope",  # run / device JWTs carry a scoped grant
        "service",  # service-to-service tokens
    }
)

#: Credential kinds a person produces by logging in.
_INTERACTIVE_AUTH_METHODS = frozenset({"jwt", "jwt_websocket", "session"})

#: Of those, the ones carried by a token, which must be a login token.
_TOKEN_AUTH_METHODS = frozenset({"jwt", "jwt_websocket"})

#: Username prefixes the backend gives its synthetic principals.
_NON_HUMAN_USERNAME_PREFIXES = ("service:", "run:", "device:")


def is_login_token(claims: Mapping[str, Any]) -> bool:
    """True when verified JWT *claims* say ``token_type: login`` and carry no other purpose claim."""
    return claims.get("token_type") == LOGIN_TOKEN_TYPE and NON_LOGIN_CLAIMS.isdisjoint(claims)


def is_purpose_bound(claims: Mapping[str, Any]) -> bool:
    """True when *claims* say the token was minted for something other than a login.

    #17049: the backend accepted ANY token signed with the platform key as a
    full user login, whatever it was minted for — a device JWT, an SLM
    MFA-pending temp token issued *before* the second factor, or a
    service-to-service token all resolved to their subject's ordinary login on
    every endpoint.

    Stated as a NEGATIVE check on purpose, and this is the part worth reading
    before "improving" it into ``not is_login_token(...)``. That positive form
    requires ``token_type: login``, which **only the backend mints**
    (``auth_middleware.py``). Tokens minted by ``autobot-slm-backend`` carry
    identity in ``sub`` and no ``token_type`` at all, and #12135 established
    that those must keep working. Requiring the positive claim would refuse
    every SLM-issued login — a fix that logs out the users it protects.

    The positive form is the better end state; getting there means the SLM
    minting ``token_type: login`` first, which is a cross-service migration and
    not this function's decision to make.

    Two ways a token is purpose-bound:

    - it carries any :data:`NON_LOGIN_CLAIMS` member — ``aud``, ``device_id``,
      ``mfa_pending``, ``run_id``, ``scope``, ``service``;
    - it carries a ``token_type`` that is not ``login`` — e.g. the
      ``token_type: device`` that ``services/device_token_service.py`` mints,
      which none of the claims above would catch.
    """
    if not NON_LOGIN_CLAIMS.isdisjoint(claims):
        return True
    token_type = claims.get("token_type")
    return token_type is not None and token_type != LOGIN_TOKEN_TYPE


def is_interactive_human(user: Optional[Mapping[str, Any]]) -> bool:
    """True only for a person's interactive login; deny-by-default otherwise.

    A JWT user (HTTP or WebSocket) must also carry ``login_token: True``, which
    the backend's JWT extraction sets from :func:`is_login_token` — a token user
    without that positive marker is refused, not assumed human.
    """
    if not user or user.get("service") or user.get("auth_disabled"):
        return False
    method = user.get("auth_method")
    if method not in _INTERACTIVE_AUTH_METHODS:
        return False
    if method in _TOKEN_AUTH_METHODS and user.get("login_token") is not True:
        return False
    username = str(user.get("username") or "")
    return not username.startswith(_NON_HUMAN_USERNAME_PREFIXES)
