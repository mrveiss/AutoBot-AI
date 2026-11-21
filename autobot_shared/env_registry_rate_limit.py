# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Rate-limit AUTOBOT_* environment variable registrations (#18087).

Sibling module imported by ``env_registry`` and also chained from
``env_registry_backend_services``, because ``env_registry.py`` is closed to new
entries. Registration contract (import side effect, ordering): see
``env_registry`` (#16415).
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RATE_LIMIT_LOCAL_MAX_KEYS",
        type=int,
        default=10_000,
        description=(
            "Cap on distinct keys the per-process rate-limit fallback tracks before it evicts keys "
            "whose every hit has aged out of the window (#18087). Only used while Redis is "
            "unavailable and a limiter's window_failure_policy is LOCAL; bounds memory when an "
            "outage outlasts the window."
        ),
        component="rate_limit",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RATE_LIMIT_LOCAL_SWEEP_INTERVAL",
        type=float,
        default=1.0,
        description=(
            "Minimum seconds between full-table eviction sweeps of the per-process rate-limit "
            "fallback while its key table is full (#21907). A new key arriving between sweeps is "
            "refused without scanning, so a flood of distinct keys during a Redis outage cannot "
            "cost a table scan per request."
        ),
        component="rate_limit",
    )
)
