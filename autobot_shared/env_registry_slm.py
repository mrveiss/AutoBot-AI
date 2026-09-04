# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""SLM AUTOBOT_* environment variable registrations.

Split out of ``env_registry.py`` rather than added inline (#15620), for the
reason ``env_registry_terminal.py`` records: that file sits at its
grandfathered file-size ceiling (#14236) with no slack, and the ratchet
forbids raising a ceiling to make room. The one pre-existing ``slm`` entry
moved here with the new one so the component lives in a single place rather
than straddling two modules -- the same relocation ``env_registry_testing.py``
made for the same reason.

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
        name="AUTOBOT_NODE_PROXY_TIMEOUT_SECONDS",
        type=float,
        default=15.0,
        description=(
            "Ceiling on a proxied request from the SLM to a node's backend. "
            "The aggregator fans out across the fleet, so without a bound one "
            "unresponsive node would hold the whole lifecycle view open."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SLM_JOURNAL_SSH_TIMEOUT_SECONDS",
        type=float,
        default=30.0,
        description=(
            "Wall-clock ceiling on the journalctl-over-SSH fetch behind "
            "GET /nodes/{node_id}/services/{service_name}/logs "
            "(api/services.py, #15620). Fetching journal entries from a node "
            "under load is slower than restarting a unit on it, and the request "
            "is operator-facing, so the cost runs both ways: raise it and an API "
            "worker stays occupied that much longer per unresponsive node, which "
            "a fleet-wide log sweep multiplies; lower it and a busy node answers "
            "HTTP 504 instead of returning its logs, and the operator has to "
            "retry asking for fewer lines. Tune it to the slowest link in the "
            "fleet, not to the fastest."
        ),
        component="slm",
        range=(5.0, 600.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SLM_RESTART_FLUSH_DELAY_SECONDS",
        type=float,
        default=1.0,
        description=(
            "Seconds the deferred SLM service restart waits for the HTTP response to "
            "flush before it starts killing the services that carried it. Too short and "
            "the caller sees a dropped connection instead of its 202; too long and the "
            "restart is needlessly delayed, so the right value follows the deployment's "
            "network rather than anything fixed "
            "(services/service_restart.py, #15611)."
        ),
        component="slm",
        range=(0.0, 60.0),
    )
)
register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SLM_RESTART_SSH_TIMEOUT_SECONDS",
        type=float,
        default=30.0,
        description=(
            "Seconds a single `systemctl restart` over SSH may take before it is "
            "abandoned and reported as failed. A slow node restarting a heavy unit "
            "legitimately exceeds a value that is generous on a fast one, so this "
            "belongs to the deployment "
            "(services/service_restart.py, #15611)."
        ),
        component="slm",
        range=(1.0, 600.0),
    )
)
