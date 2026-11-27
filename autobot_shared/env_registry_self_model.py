# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Self-model AUTOBOT_* environment variable registrations (#22277).

Imported from the end of ``env_registry_slm_health`` (``env_registry.py`` is at its size ceiling, #22280).
Registration contract (import side effect, ordering): see ``env_registry`` (#16415).
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SELF_MODEL_INVENTORY_RESCAN_MINUTES",
        type=int,
        default=30,
        description=(
            "Minutes after which a node rescans its package and command lists even when the mtime signature "
            "is unchanged: a permission change moves a file's ctime, not its directory's mtime "
            "(autobot_shared/self_model_constants.py, #22280)."
        ),
        component="slm",
        range=(1, 1440),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SELF_MODEL_INVENTORY_RESEND_HOURS",
        type=int,
        default=6,
        description=(
            "Hours between full resends of a node's package and command inventory when its hash is unchanged: "
            "the backstop for a lost report (autobot_shared/self_model_constants.py, #22277)."
        ),
        component="slm",
        range=(1, 168),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SELF_MODEL_STALE_HEARTBEATS",
        type=int,
        default=3,
        description=(
            "Heartbeat intervals of silence after which a node's probed self-model entities become stale "
            "(autobot_shared/self_model_constants.py, #22277)."
        ),
        component="slm",
        range=(1, 1000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SELF_MODEL_PUSH_INTERVAL_S",
        type=int,
        default=60,
        description=(
            "Seconds between the backend's pushes of its route, tool, agent and service-health records to the "
            "SLM self-model (autobot-backend/services/self_model_producer.py, #22277)."
        ),
        component="backend",
        range=(10, 3600),
    )
)
