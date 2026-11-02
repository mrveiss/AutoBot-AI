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
        name="AUTOBOT_WORKFLOW_COMMAND_TIMEOUT_S",
        type=int,
        default=300,
        description=(
            "Seconds a workflow command step may run before its whole process group is killed "
            "and the step fails with exit code 124 (#19807). Raising it lets long builds finish; "
            "lowering it kills stuck commands sooner (services/workflow_automation/command_step.py)."
        ),
        component="terminal",
        range=(1, 3600),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_WORKFLOW_COMMAND_MAX_OUTPUT_BYTES",
        type=int,
        default=1048576,
        description=(
            "Bytes of stdout, and separately of stderr, a workflow command step keeps; the rest is "
            "read and discarded and the step result is marked truncated (#19807). Raising it keeps "
            "more of a chatty command's output in memory and in the step result "
            "(services/workflow_automation/command_step.py)."
        ),
        component="terminal",
        range=(1024, 104857600),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_WORKFLOW_COMMAND_CWD",
        type=str,
        default="",
        description=(
            "Directory workflow command steps run in (#19807). Empty means a dedicated "
            "'autobot-workflow-commands' directory under the system temp directory, created on "
            "first use, so a step does not start inside the application tree "
            "(services/workflow_automation/command_step.py)."
        ),
        component="terminal",
    )
)
