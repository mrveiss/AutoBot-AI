# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Configured-user credential handling for ``SecurityLayer`` (#21088).

``allowed_users`` maps a username to a stored password hash. Hashing and
verification use the canonical helpers in ``autobot_shared.auth.jwt_core``;
this module adds no crypto of its own. Entries that are not hashes are
rejected at load (fail closed) and the stored values are never rewritten.

Operator helper, to produce a hash for a config entry::

    python autobot-backend/security_layer_credentials.py <username>
"""

import functools
import getpass
import sys
from typing import Any, Dict, Optional

from autobot_shared.auth.jwt_core import hash_password, verify_password
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")
_PLACEHOLDER_SECRET = "placeholder-for-unknown-user"  # pragma: allowlist secret  # nosec B105


def _entry_hash(entry: Any) -> Optional[str]:
    """Return the stored hash from a string entry or a ``password_hash`` dict."""
    if isinstance(entry, dict):
        entry = entry.get("password_hash")
    if isinstance(entry, str) and entry.startswith(_BCRYPT_PREFIXES):
        return entry
    return None


def load_hashed_users(configured: Any) -> Dict[str, str]:
    """Return ``{username: hash}`` for hashed entries only.

    Entries that are not hashes are rejected and reported by username; the
    value is never logged. Nothing is rewritten.
    """
    if not isinstance(configured, dict):
        if configured:
            logger.error("allowed_users must be a mapping of username to password hash; ignoring it")
        return {}
    accepted: Dict[str, str] = {}
    for username, entry in configured.items():
        stored = _entry_hash(entry)
        if stored is None:
            logger.error(
                "allowed_users entry for %r is not a password hash and is rejected; "
                "generate one with security_layer_credentials.py",
                username,
            )
            continue
        accepted[username] = stored
    return accepted


@functools.lru_cache(maxsize=1)
def _placeholder_hash() -> str:
    return hash_password(_PLACEHOLDER_SECRET)


def verify_user_password(configured: Any, username: str, password: str) -> bool:
    """Verify *password* for *username* through the canonical hasher.

    An unknown or non-hash entry still costs one hash verification so the
    outcome does not depend on whether the username exists.
    """
    stored = _entry_hash(configured.get(username)) if isinstance(configured, dict) else None
    if stored is None:
        verify_password(password, _placeholder_hash())
        if isinstance(configured, dict) and username in configured:
            logger.error("allowed_users entry for %r is not a password hash; authentication refused", username)
        return False
    return verify_password(password, stored)


def main(argv: Optional[list] = None) -> int:
    """Operator CLI: prompt for a password and print its hash."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: security_layer_credentials.py <username>", file=sys.stderr)  # noqa: print
        return 2
    first = getpass.getpass(f"Password for {args[0]}: ")
    if first != getpass.getpass("Repeat password: "):
        print("passwords differ", file=sys.stderr)  # noqa: print
        return 1
    print(hash_password(first))  # noqa: print
    return 0


if __name__ == "__main__":
    sys.exit(main())
