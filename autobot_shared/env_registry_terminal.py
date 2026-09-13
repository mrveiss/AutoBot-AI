# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Terminal AUTOBOT_* environment variable registrations.

Split out of ``env_registry.py`` rather than added inline (#14961) — that
file was already at its grandfathered file-size ceiling (#14236) with no
slack, so a same-file addition would have required raising the ceiling,
which the ratchet forbids. ``env_registry_testing.py`` was relocated out at
the same time to free the room this file's own import line needs; see that
module's docstring.

Importing this module registers every variable below into
``autobot_shared.env_registry.REGISTRY`` as a side effect, exactly like the
``register_env_var(...)`` calls in ``env_registry.py`` itself. It is imported
from there, after ``EnvVarSpec``/``register_env_var``/``REGISTRY`` are
defined, so nothing ever observes a partially-populated registry.

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
