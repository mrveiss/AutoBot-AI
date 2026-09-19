# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who an A2A peer is: the verified credential that presents a peer id, not the id alone (#16950).

``X-A2A-Agent-Id`` is a header the caller declares. Trust was keyed on it alone, so
one credential could claim whichever peer id held the highest trust and inherit it,
and trust levels narrowed nothing. The owner's decision (#16950): trust and
attribution are keyed on the pair ``(credential subject, peer id)``. Credential A
presenting peer Y is its own pair, with its own trust, and cannot borrow credential
B's.

The subject comes from the *verified* principal the auth middleware produced. It
never comes from the ``Authorization`` header's unverified claims (see
:func:`jwt_subject_for_audit`): a cookie-authenticated caller could attach any bearer
token it liked and pick someone else's pair.
"""

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import quote

from autobot_shared.logging_manager import get_logger
from autobot_shared.principal import resolve_principal_id

logger = get_logger(__name__)


def credential_subject(current_user: Dict[str, Any] | None) -> str:
    """The verified identity behind a request: its principal id, else its username.

    Every principal the auth middleware produces carries a ``username``: users,
    sessions, run and device JWTs, and internal service keys (``service:slm``). The
    fallback is therefore reached only for principals with no user id, never for an
    anonymous one. The A2A router is admin-gated, so this cannot run without a
    principal. An empty one is refused rather than keyed as nobody.
    """
    subject = resolve_principal_id(current_user) or (current_user or {}).get("username")
    if not subject:
        raise ValueError("A2A request has no verified principal to key trust on")
    return str(subject)


def peer_trust_key(subject: str, peer_id: str) -> str:
    """The trust key for *subject* presenting *peer_id*.

    Each part is percent-encoded, so a ``/`` inside either cannot make two different
    pairs produce the same key.
    """
    return f"{quote(subject, safe='')}/{quote(peer_id, safe='')}"


def jwt_subject_for_audit(authorization: str | None) -> str | None:
    """The ``sub`` claim of a bearer token, **unverified**: for audit and logging only.

    Moved from ``api/a2a.py`` (#16950). Its signature is not checked, which is why
    nothing may key trust or authority on it. Use :func:`credential_subject`.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return _decode_jwt_sub(authorization[7:])


def _decode_jwt_sub(token: str) -> str | None:
    """Decode a JWT's ``sub`` claim without verifying its signature. None on any decode error."""
    try:
        import base64
        import json as _json

        parts = token.split(".")
        if len(parts) != 3:
            return None
        claims = _json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
        return claims.get("sub")
    except Exception as exc:
        logger.debug("JWT sub decode failed: %s", exc)
        return None
