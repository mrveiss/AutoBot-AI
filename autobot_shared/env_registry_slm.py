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

# --- #15710: os.environ.get-wrapped code-sync/venv-reconcile timeouts, sized
# but never registered because the registry checker only ever saw os.getenv
# and the env_utils helpers, not os.environ.get. -----------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_NPM_INSTALL_TIMEOUT",
        type=float,
        default=300.0,
        description=(
            "Timeout, in seconds, for `npm ci` (dependency install) during a "
            "frontend component sync. A Windows-generated package-lock.json "
            "read over WSL can be slow, which is why the default matches pip's. "
            "Raising it tolerates a slower install; lowering it fails a stuck "
            "install sooner (autobot-slm-backend/api/code_sync.py, #11351)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_NPM_BUILD_TIMEOUT",
        type=float,
        default=300.0,
        description=(
            "Timeout, in seconds, for `npm run <build>` (the vite build step) "
            "during a frontend component sync. Raising it tolerates a slower "
            "build; lowering it fails a stuck build sooner (autobot-slm-backend/api/code_sync.py, "
            "#11351)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_DB_BACKUP_KEEP",
        type=int,
        default=5,
        description=(
            "Number of pg_dump backups retained per component before the oldest "
            "are pruned. Raising it keeps a longer rollback history at the cost "
            "of more disk in the backup directory; lowering it frees disk sooner "
            "but shortens how far back a restore can reach (autobot-slm-backend/api/code_sync.py, "
            "#11376)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_HEALTH_POLL_TIMEOUT",
        type=float,
        default=180.0,
        description=(
            "Total seconds to wait for a component to report healthy after a "
            "restart that recreated its venv, covering first-run py3.14 "
            "bytecode compilation of the whole dependency tree (#11413). "
            "Lowering it risks a false #11377 rollback of a slow-but-healthy "
            "cold start; raising it waits longer before giving up on a "
            "genuinely stuck restart (autobot-slm-backend/api/code_sync.py, #11378)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_HEALTH_POLL_TIMEOUT_FAST",
        type=float,
        default=60.0,
        description=(
            "Total seconds to wait for a component to report healthy after a "
            "restart that reused its existing venv (warm interpreter, no "
            "cold-start compilation). Lowering it detects a stuck restart "
            "sooner; raising it tolerates a slower warm restart before the "
            "wait ends (autobot-slm-backend/api/code_sync.py, #11458)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_HEALTH_POLL_CONNECT_TIMEOUT",
        type=float,
        default=3.0,
        description=(
            "Per-attempt connect timeout, in seconds, when probing a "
            "just-restarted component's health endpoint. Raising it tolerates "
            "a service that is slower to accept connections; lowering it fails "
            "an unreachable endpoint faster (autobot-slm-backend/api/code_sync.py, #11378)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_HEALTH_POLL_INTERVAL",
        type=float,
        default=2.0,
        description=(
            "Delay, in seconds, between health-probe attempts after a "
            "component restart. Raising it polls less often (lower overhead, "
            "slower detection); lowering it detects a healthy service sooner "
            "at the cost of more probe traffic (autobot-slm-backend/api/code_sync.py, #11378)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SNAPSHOT_KEEP",
        type=int,
        default=3,
        description=(
            "Number of component snapshots retained for rollback before the "
            "oldest are pruned. Raising it keeps a longer rollback history at "
            "the cost of more snapshot-directory disk usage; lowering it frees "
            "disk sooner but shortens how far back a rollback can reach "
            "(autobot-slm-backend/api/code_sync.py, #11377)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PIP_INSTALL_TIMEOUT",
        type=float,
        default=300.0,
        description=(
            "Timeout, in seconds, for a `pip install` during venv "
            "reconciliation. Raising it tolerates a slower package install; "
            "lowering it fails a stuck install sooner (autobot-slm-backend/api/venv_reconcile.py)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_VENV_INSPECT_TIMEOUT",
        type=float,
        default=60.0,
        description=(
            "Timeout, in seconds, for inspecting an existing venv's installed "
            "packages during reconciliation. Raising it tolerates a slower "
            "inspection; lowering it fails a stuck inspection sooner "
            "(autobot-slm-backend/api/venv_reconcile.py)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PIP_UNINSTALL_TIMEOUT",
        type=float,
        default=120.0,
        description=(
            "Timeout, in seconds, for a `pip uninstall` during venv "
            "reconciliation. Raising it tolerates a slower removal; lowering "
            "it fails a stuck uninstall sooner (autobot-slm-backend/api/venv_reconcile.py)."
        ),
        component="slm",
    )
)
