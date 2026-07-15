# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Login-time soft password weakness detector (#10199).

Checks a plaintext password (available only at login time) for clear weakness
signals and returns a human-readable reason string, or ``None`` when the
password is acceptable.  Results are advisory only — callers MUST NOT block
authentication based on this check.

Design constraints:
- No external dependencies (pure stdlib).
- O(1) — set membership and length checks only.
- Plaintext MUST NOT be logged or stored by any caller.
- The seeded-default sentinel is obtained from the live SSOT config so it
  matches exactly what the installer/wizard actually wrote.
"""

from __future__ import annotations

__all__ = ["check_password_weakness"]

# Minimum character count before a password is considered too short.
_MIN_LENGTH = 12

# Small, curated set of universally weak passwords.  Kept intentionally short
# to stay dependency-free and maintain O(1) lookup.
_COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "password",
        "password1",
        "password123",
        "admin",
        "admin123",
        "changeme",
        "changeme1",
        "123456",
        "12345678",
        "123456789",
        "1234567890",
        "qwerty",
        "qwerty123",
        "letmein",
        "welcome",
        "welcome1",
        "iloveyou",
        "sunshine",
        "abc123",
        "pass",
        "pass123",
        "test",
        "test123",
        "root",
        "toor",
        "secret",
        "passw0rd",
        "p@ssword",
        "p@ssw0rd",
        "autobot",
        "autobot123",
    }
)


def _get_seeded_default() -> str:
    """Return the configured admin seed password (or empty string).

    Deferred import keeps this module importable before the SSOT config is
    populated (unit tests that stub the config).  Empty string is returned on
    any error so the check degrades gracefully.
    """
    try:
        from autobot_shared.ssot_config import get_config  # noqa: PLC0415

        cfg = get_config()
        return cfg.auth.admin_password or ""
    except Exception:
        return ""


def check_password_weakness(password: str) -> str | None:
    """Return a weakness reason string, or ``None`` if the password is acceptable.

    Args:
        password: The plaintext password submitted at login.  Do NOT log it.

    Returns:
        A short, user-readable reason string when the password is weak, or
        ``None`` when no weakness is detected.

    Criteria (checked in priority order):
    1. Equals the operator-configured seeded default password (highest risk).
    2. Length below ``_MIN_LENGTH`` characters.
    3. Membership in ``_COMMON_PASSWORDS`` (case-insensitive).
    """
    if not password:
        return None

    # 1. Seeded default: plaintext match against the configured seed password.
    #    Only meaningful when AUTOBOT_ADMIN_PASSWORD is set; otherwise the
    #    seeded default is empty and this branch is skipped.
    seeded = _get_seeded_default()
    if seeded and password == seeded:
        return "Password matches the operator-configured default — please change it immediately."

    # 2. Length gate.
    if len(password) < _MIN_LENGTH:
        return f"Password is too short (minimum {_MIN_LENGTH} characters recommended)."

    # 3. Common-password list (case-insensitive).
    if password.lower() in _COMMON_PASSWORDS:
        return "Password is in the list of commonly used passwords — choose a unique password."

    return None
