# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Single verifier for ``security_config.allowed_users`` entries (#21088).

Both ``AuthMiddleware.authenticate_user`` and ``SecurityLayer.authenticate_user``
verify through :func:`verify_configured_user`. An entry is a mapping holding a
bcrypt ``password_hash``; anything else is rejected (fail closed) and reported
by username only. Stored values are never rewritten.

Operators produce a hash for an entry with
``autobot-infrastructure/shared/scripts/utilities/generate-password-hashes.py``.
"""

import functools
import logging
from typing import Any, Dict, Optional

from autobot_shared.auth.jwt_core import hash_password, verify_password
from autobot_shared.logging_manager import get_logger
from autobot_shared.logging_once import log_once

logger = get_logger(__name__)

_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")
_PLACEHOLDER_SECRET = "placeholder-for-unknown-user"  # pragma: allowlist secret  # nosec B105


def _stored_hash(entry: Any) -> Optional[str]:
    """Return the entry's bcrypt hash, or None when it is not a hashed entry."""
    stored = entry.get("password_hash") if isinstance(entry, dict) else None
    if isinstance(stored, str) and stored.startswith(_BCRYPT_PREFIXES):
        return stored
    return None


def _report_rejected(username: Any) -> None:
    """Log once per process and user that *username*'s entry is rejected."""
    log_once(
        logger,
        logging.ERROR,
        repr(username),
        "allowed_users entry for %r has no password hash and is rejected; "
        "generate one with generate-password-hashes.py",
        username,
    )


def is_configured_user(allowed_users: Any, username: str) -> bool:
    """True when *allowed_users* is a mapping that lists *username*."""
    return isinstance(allowed_users, dict) and username in allowed_users


def failure_reason(allowed_users: Any, username: str) -> str:
    """Audit reason for a failed verification of *username*."""
    if not is_configured_user(allowed_users, username):
        return "user_not_found"
    if _stored_hash(allowed_users[username]) is None:
        return "credential_not_hashed"
    return "invalid_password"


def load_hashed_users(configured: Any) -> Dict[str, dict]:
    """Return only the hashed entries of *configured*, reporting the rest."""
    if not isinstance(configured, dict):
        if configured:
            logger.error("allowed_users must be a mapping of username to entry; ignoring it")
        return {}
    accepted = {}
    for username, entry in configured.items():
        if _stored_hash(entry) is None:
            _report_rejected(username)
            continue
        accepted[username] = entry
    return accepted


@functools.lru_cache(maxsize=1)
def _placeholder_hash() -> str:
    return hash_password(_PLACEHOLDER_SECRET)


def verify_configured_user(allowed_users: Any, username: str, password: str) -> Optional[dict]:
    """Return the user's entry when *password* verifies, else None.

    An unknown user or a non-hash entry still costs one hash verification,
    so the outcome does not depend on whether the username exists.
    """
    entry = allowed_users.get(username) if isinstance(allowed_users, dict) else None
    stored = _stored_hash(entry)
    if stored is None:
        verify_password(password, _placeholder_hash())
        if entry is not None:
            _report_rejected(username)
        return None
    return entry if verify_password(password, stored) else None
