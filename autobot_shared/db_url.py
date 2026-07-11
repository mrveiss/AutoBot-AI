# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical Postgres URL assembly helper (#11466).

Extracts the AUTOBOT_POSTGRES_* component-var assembly that was duplicated
between autobot-backend/migrations/db_url.py and
autobot-slm-backend/api/code_sync.py into a single primitive.

Only the string-assembly step is shared; each caller retains its own
precedence logic (AUTOBOT_DATABASE_URL, deployment-config, etc.) and its
own default values, which legitimately differ.

Caller contract
---------------
*source* must contain only **non-empty** values for the AUTOBOT_POSTGRES_*
keys.  Pass ``{k: v for k, v in raw.items() if v}`` (or equivalent) before
calling when the raw mapping may contain empty strings — empty values are
treated as absent by this function (they do NOT override the parameter
defaults).
"""

from __future__ import annotations

from typing import Mapping


def assemble_postgres_url(
    source: Mapping[str, str],
    *,
    default_host: str = "",
    default_port: str = "5432",
    default_user: str = "autobot",
    default_db: str = "autobot",
    password_default: str = "",
) -> str:
    """Build a ``postgresql://`` URL from AUTOBOT_POSTGRES_* component vars.

    Args:
        source: Mapping with non-empty AUTOBOT_POSTGRES_* entries (empty
            strings are treated as absent — see module docstring).
        default_host: Fallback when ``AUTOBOT_POSTGRES_HOST`` is absent.
            ``""`` (the default) causes ``""`` to be returned (no host).
        default_port: Port fallback when ``AUTOBOT_POSTGRES_PORT`` is absent.
        default_user: User fallback when ``AUTOBOT_POSTGRES_USER`` is absent.
        default_db: DB name fallback when ``AUTOBOT_POSTGRES_DB`` is absent.
        password_default: Password fallback when ``AUTOBOT_POSTGRES_PASSWORD``
            is absent.  When the resolved password is ``""``, the auth segment
            is ``user@`` instead of ``user:@``.

    Returns:
        ``postgresql://{user[:pw]}@{host}:{port}/{db}`` when a host is
        present; ``""`` when ``host`` resolves to ``""`` and
        ``default_host`` is also ``""``.
    """
    host = source.get("AUTOBOT_POSTGRES_HOST", default_host)
    if not host:
        return ""
    port = source.get("AUTOBOT_POSTGRES_PORT", default_port)
    user = source.get("AUTOBOT_POSTGRES_USER", default_user)
    pw = source.get("AUTOBOT_POSTGRES_PASSWORD", password_default)
    db = source.get("AUTOBOT_POSTGRES_DB", default_db)
    auth = f"{user}:{pw}@" if pw else f"{user}@"
    return f"postgresql://{auth}{host}:{port}/{db}"
