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


#: Prefix for a work-claim identity derived from an A2A peer. Namespaced so a
#: peer cannot present an id that collides with an internal agent's.
CLAIM_PREFIX = "a2a"


def claim_identity(peer_id: str | None, task_id: str) -> str:
    """The work-claim holder for a task submitted by *peer_id* (#16950).

    Every A2A task used to claim its scopes as the literal ``"a2a-executor"``,
    so every admitted peer was ONE claimant. The ingress gate at ``api/a2a.py``
    identifies the peer correctly; the identity was dropped one layer in.

    What that cost, stated precisely because the obvious guess is wrong: it did
    NOT let one peer act on another's hold. ``work_claims``' Lua treats a holder
    as the same only when ``agent_id`` AND ``task_id`` both match, so two peers'
    tasks conflicted anyway — their task ids differ. What was lost is
    ATTRIBUTION: a refusal named ``a2a-executor`` rather than the peer actually
    holding the scope, so an operator could not tell which peer to talk to, and
    any policy keyed on ``agent_id`` — rate, budget, audit — saw every peer as
    one. #16950's first criterion is identity end to end; this is the A2A leg of
    it.

    An absent peer id does NOT fall back to a shared name. Anonymous callers are
    already refused at ingress, so this is defence in depth -- but a fallback
    constant would rebuild the exact aliasing this function exists to remove, so
    an unidentified caller gets an identity unique to its own task and can
    therefore alias nobody.

    Percent-encoded for the same reason as :func:`peer_trust_key`: a ``/`` or
    ``:`` inside a peer id must not let two different peers produce one key.
    """
    if not peer_id:
        return f"{CLAIM_PREFIX}:anonymous:{quote(task_id, safe='')}"
    return f"{CLAIM_PREFIX}:{quote(peer_id, safe='')}"


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
