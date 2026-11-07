# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Worker-loop AUTOBOT_* environment variable registrations (#20887).

Sibling module chained from ``env_registry_backend_services`` because
``env_registry.py`` is closed to new entries. Registration contract (import
side effect, ordering): see ``env_registry`` (#16415).
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_WORKER_LOOP_START_TIMEOUT",
        type=float,
        default=10.0,
        description="Seconds to wait for a Celery worker's persistent event loop thread to report running.",
        component="celery",
        range=(0.1, 120.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_WORKER_LOOP_SHUTDOWN_TIMEOUT",
        type=float,
        default=15.0,
        description="Seconds the worker shutdown hook gives engine/Redis disposal before stopping the loop anyway.",
        component="celery",
        range=(0.1, 300.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_WORKER_LOOP_RUN_TIMEOUT",
        type=float,
        default=3600.0,
        description="Seconds run_on_loop waits for a coroutine on the worker loop before cancelling it and raising.",
        component="celery",
        range=(0.1, 86400.0),
    )
)
