# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Which adapter_config entries the company-template export turns into ``{{NAME}}`` (#17336).

The canonical matcher decides by NAME; the export also has to round-trip, which a
``bool``/``None`` cannot do through a string placeholder. This module is the ONE
owner of the bool/None rule for the export. It declares no vocabulary of its own:
both the matcher and the legacy export names come from ``autobot_shared.secret_redaction``.
"""

from typing import Any

from autobot_shared.secret_redaction import LEGACY_EXPORT_KEY_NAMES, MatchPolicy, is_credential_entry


def export_masks(name: str, value: Any) -> bool:
    """True when the export must replace ``value`` under ``name`` with a placeholder.

    A ``True`` under one of the pre-#17336 export names stays a placeholder (#18196,
    #17337 AC2: no key leaves the masked set); ``False``/``None`` never were masked.
    """
    if value is None or isinstance(value, bool):
        return value is True and name.lower() in LEGACY_EXPORT_KEY_NAMES
    return bool(value) and is_credential_entry(name, value, MatchPolicy.PRECISE, exempt_counts=True)
