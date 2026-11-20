# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Chat-share AUTOBOT_* environment variable registrations (#18890).

Split out of ``env_registry.py`` and ``env_registry_security.py``, both at their file-size ceilings.
Imported by ``env_registry`` itself, so registration happens whenever it loads.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SESSION_SHARE_ADOPT_LOCK_TTL_MS",
        type=int,
        default=60000,
        description=(
            "How long one worker may hold the lock while it copies pre-table Redis chat shares into the "
            "durable table (#18890). A crashed holder frees it after this long."
        ),
        component="security",
        range=(1000, 600000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SESSION_SHARE_ADOPT_WAIT_SECONDS",
        type=int,
        default=30,
        description=(
            "How long a worker that lost the adoption lock waits for the other to finish before an unshare "
            "fails closed (#18890)."
        ),
        component="security",
        range=(0, 600),
    )
)
