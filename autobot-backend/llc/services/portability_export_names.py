# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Which adapter_config entries the company-template export turns into ``{{NAME}}`` (#17336).

The canonical matcher decides by NAME; the export also has to round-trip, which a
``bool``/``None`` cannot do through a string placeholder. This module is the ONE
owner of the bool/None rule for the export.
"""

from typing import Any

from autobot_shared.secret_redaction import MatchPolicy, is_credential_entry

# The names the export masked before the canonical matcher (origin/main's exact
# match, case-insensitive). A ``True`` under one of them is still a placeholder:
# #18196 records ``api_key: True`` not round-tripping as an owner decision, and
# #17337 AC2 says no key leaves the masked set. ``False``/``None`` were never masked.
_MAIN_EXPORT_NAMES = frozenset(
    {
        "api_key",
        "api_secret",
        "token",
        "access_token",
        "secret",
        "password",
        "credentials",
        "private_key",
        "client_secret",
        "auth_token",
        "bearer_token",
        "key",
    }
)


def export_masks(name: str, value: Any) -> bool:
    """True when the export must replace ``value`` under ``name`` with a placeholder."""
    if value is None or isinstance(value, bool):
        return value is True and name.lower() in _MAIN_EXPORT_NAMES
    return bool(value) and is_credential_entry(name, value, MatchPolicy.PRECISE, exempt_counts=True)
