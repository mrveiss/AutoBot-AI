# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Terminal AUTOBOT_* environment variable registrations.

Split out of ``env_registry.py`` rather than added inline (#14961) — that
file was already at its grandfathered file-size ceiling (#14236) with no
slack, so a same-file addition would have required raising the ceiling,
which the ratchet forbids. ``env_registry_testing.py`` was relocated out at
the same time to free the room this file's own import line needs; see that
module's docstring.

Registration contract (import side effect, ordering): see ``env_registry`` (#16415).

Closes GH#7081.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TERMINAL_SESSION_TTL_SECONDS",
        type=int,
        default=86400,
        description=(
            "TTL for terminal:session_config:* Redis keys — the cross-worker terminal "
            "session registry (services/terminal_session_store.py, #14961). A session "
            "config outlives the connection it was created for (the WebSocket may attach "
            "on a different uvicorn worker, or reconnect after one), so this is deliberately "
            "generous: 24h matches the sibling chat:session:* cache TTL "
            "(chat_history/cache.py) rather than the lifetime of any single PTY process."
        ),
        component="terminal",
        range=(60, 604800),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SLM_KEY_PROBE_TIMEOUT_SECONDS",
        type=float,
        default=10.0,
        description=(
            "Wall-clock ceiling on the SSH key-access probe that runs before a stored SSH password's deletion is "
            "proposed (inline in enrollment) and again before it is deleted (#20046). The probe is killed at the "
            "ceiling and counts as failed, so a hung node delays enrollment by at most this long and the proposal "
            "waits for a later enrollment."
        ),
        component="slm",
        range=(2.0, 60.0),
    )
)
