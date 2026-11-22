# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Backend-to-SLM client AUTOBOT_* environment variable registrations (#22030).

Sibling module chained from ``env_registry_slm_rollback`` because ``env_registry.py`` is closed to new entries.
Registration contract (import side effect, ordering): see ``env_registry`` (#16415).
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SLM_REQUEST_TIMEOUT",
        type=float,
        default=15.0,
        description=(
            "Seconds one backend request to the SLM's role-owner and node-service API may take in total "
            "(autobot-backend/services/slm_node_services.py, #22030)."
        ),
        component="backend",
        range=(1.0, 300.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_REDIS_NODE_CACHE_TTL",
        type=int,
        default=60,
        description=(
            "Seconds the backend's Redis service manager reuses the Redis node it resolved from the SLM's `redis` "
            "role owner before asking again (autobot-backend/services/redis_service_errors.py, #22030)."
        ),
        component="backend",
        range=(0, 3600),
    )
)
