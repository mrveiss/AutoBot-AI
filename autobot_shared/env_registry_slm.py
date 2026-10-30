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

Registration contract (import side effect, ordering): see ``env_registry`` (#16415).

Closes GH#7081.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SLM_UPDATE_REPORT_DEPLOY_RUNS",
        type=int,
        default=50,
        description="Newest role deploys listed in the update report (api/update_report.py, #19962).",
        component="slm",
        range=(1, 500),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PLAYBOOK_PIPE_LINE_LIMIT",
        type=int,
        default=10 * 1024 * 1024,
        description=(
            "Bytes of one playbook output line the executor will read. asyncio's "
            "StreamReader defaults to 64 KiB, and a single ansible `fatal:` line "
            "carries the whole task result as JSON -- for a pip task that embeds "
            "pip's entire stderr and goes past 64 KiB routinely. Exceeding it used "
            "to kill the reader with a bare ValueError, which then stood in for the "
            "failure it had swallowed. Raise it only if a real line is larger; the "
            "reader truncates and says so rather than dying either way."
        ),
        component="slm",
    )
)

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

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SLM_FAILURE_DIAG_JOURNAL_LINES",
        type=int,
        default=30,
        description=(
            "Journal lines fetched from a node whose fleet start/stop/restart failed, "
            "returned in the response `diagnostics` (services/service_restart.py, #18714)."
        ),
        component="slm",
        range=(1, 500),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SLM_FAILURE_DIAG_MAX_CHARS",
        type=int,
        default=4000,
        description=(
            "Characters kept (the tail) of each failure-diagnostics section, `systemctl status` "
            "and journal, per failed node (services/service_restart.py, #18714)."
        ),
        component="slm",
        range=(200, 65536),
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

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_API_KEY_LEGACY_GRACE_DAYS",
        type=int,
        default=90,
        description=(
            "Days an API key created before scope enforcement keeps its owner's full "
            "authority, with a warning on every use, before it is refused until re-issued "
            "with explicit scopes (#16040 AC5; owner ruling: 90)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_API_KEY_SCOPES_ENFORCED_FROM",
        type=str,
        default="2026-09-11",
        description=(
            "ISO date from which API-key scopes are enforced; keys created before it get "
            "the legacy grace period. Set it to the day enforcement reached this "
            "deployment if that was later (#16040 AC5)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_GPU_PROBE_TIMEOUT_S",
        type=float,
        default=5.0,
        description=(
            "Seconds a GPU vendor tool (nvidia-smi, rocm-smi) may run before the probe gives up. "
            "Read by autobot_shared.gpu_telemetry for the SLM agent's heartbeat GPU telemetry (#16280)."
        ),
        component="slm",
        range=(0.5, 60.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PRICING_POST_SYNC_TIMEOUT_S",
        type=float,
        default=120.0,
        description=(
            "Timeout, in seconds, for the one-shot pricing refresh a code-sync "
            "of autobot-backend runs immediately after install/update. A "
            "refresh that does not finish within it is recorded as timed out "
            "and the sync proceeds regardless — prices stay unknown until the "
            "next refresh (autobot-slm-backend/api/_pricing_post_sync.py, #16231)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SYNC_GIT_TIMEOUT_S",
        type=float,
        default=30.0,
        description=(
            "Timeout, in seconds, for a single git subprocess (`rev-parse`, "
            "`diff --name-status`) during the builtin updater's git-aware "
            "deletion pass. Raising it tolerates a slower repository; lowering "
            "it fails a wedged git process sooner rather than stalling a sync "
            "(autobot-slm-backend/services/sync_deletions.py, #16310)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SYNC_UNSHALLOW_TIMEOUT_S",
        type=float,
        default=600.0,
        description=(
            "Timeout, in seconds, for `git fetch --unshallow` on the builtin "
            "updater's `code_source` checkout when it is still a shallow "
            "clone (from initial provisioning). Downloads the ENTIRE history "
            "the shallow fetch skipped, so it gets a much longer bound than "
            "AUTOBOT_SYNC_GIT_TIMEOUT_S -- minutes, not seconds, on a "
            "monorepo-sized checkout (autobot-slm-backend/services/"
            "git_subprocess.py:ensure_full_history, #16310)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SYNC_GIT_TRANSPORT_TIMEOUT_S",
        type=float,
        default=600.0,
        description=(
            "Timeout, in seconds, for the SLM git tracker's `git fetch --prune` and "
            "`git pull` against the code_source remote. Transport commands download "
            "history, so they get a far longer bound than AUTOBOT_SYNC_GIT_TIMEOUT_S "
            "(autobot-slm-backend/services/git_tracker.py, #17855)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CONSTRAINTS_RSYNC_TIMEOUT_S",
        type=float,
        default=30.0,
        description=(
            "Timeout, in seconds, for the top-level constraints/ rsync a "
            "backend component sync runs before pip so a requirements.txt "
            "`-c ../constraints/shared.txt` reference resolves "
            "(autobot-slm-backend/api/code_sync_paths.py, #16713)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ROOT_REQS_CP_TIMEOUT_S",
        type=float,
        default=10.0,
        description=(
            "Timeout, in seconds, for copying a single top-level repo-root "
            "file (e.g. requirements.txt) a backend component sync runs before "
            "pip so a `-r ../requirements.txt` reference resolves "
            "(autobot-slm-backend/api/code_sync_paths.py, #16713)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ALEMBIC_UPGRADE_TIMEOUT_S",
        type=float,
        default=300.0,
        description=(
            "Timeout, in seconds, for `alembic upgrade heads` during a "
            "component's post-sync migration step. Raising it tolerates a "
            "slower migration; lowering it fails a wedged migration sooner "
            "(autobot-slm-backend/api/code_sync_paths.py, #11255, #16713)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SYNC_RESTART_TIMEOUT_S",
        type=int,
        default=60,
        description=(
            "Seconds the code-sync orchestrator waits for one `sudo -n systemctl restart` "
            "over SSH before recording the restart as failed "
            "(autobot-slm-backend/services/post_sync_runner.py, #17455)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="SLM_COMPOSE_NODES",
        type=str,
        default="",
        description=(
            "Surface each compose container as an SLM fleet node (#9761). Unset follows the deployment "
            "mode: on for docker_local (the compose stack, or a dev checkout run inside a container), off "
            "on a bare-metal/VM fleet and a host dev checkout; true|false overrides, a blank or unrecognised "
            "value is warned about and treated as unset. The one default is autobot-slm-backend/config.py "
            "Settings.compose_nodes_enabled (#19323); docker-compose.yml passes the name through only."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_DOCKER_MGMT_PREFIX",
        type=str,
        default="",
        description=(
            "First three octets of the compose autobot-mgmt /24 (e.g. 10.77.3). No default: "
            "docker/generate-secrets.sh picks a free private range per host, docker-compose.yml "
            "refuses to start without it, and compose_fleet.py builds node IPs from it (#16833)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_DOCKER_SLM_NGINX_CONF",
        type=str,
        default="./docker/nginx/nginx-slm.conf",
        description=(
            "nginx config the SLM-only web GUI (compose profile slm) mounts. The default serves "
            "HTTP; ./docker/nginx/nginx-slm-ssl.conf serves HTTPS with ./docker/certs (#18593)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_DOCKER_SLM_HTTPS_PORT",
        type=int,
        default=443,
        description=(
            "Host port the SLM-only web GUI publishes for HTTPS (container port 443). Change it when "
            "host port 443 is already taken; the GUI's HTTP port stays 80 (#18593)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_DOCKER_MGMT_POOL",
        type=str,
        default="10.128.0.0/9",
        description=(
            "Private IPv4 block (/24 or larger) that docker/pick_mgmt_prefix.py draws the "
            "compose management /24 from, skipping any range a host route or Docker network uses (#16833)."
        ),
        component="slm",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_REVOCATION_RETRY_AFTER_SECONDS",
        type=int,
        default=5,
        description=(
            "Seconds in the Retry-After header of the 503 (detail "
            "revocation_check_unavailable) both backends answer when a token's revocation "
            "check cannot run (#18892). The token is still refused; the client keeps its "
            "session and retries. Raising it spaces retries out during a long store "
            "outage; lowering it recovers faster once the store is back "
            "(autobot_shared/auth/revocation_unavailable.py). Floor 1."
        ),
        component="auth",
        range=(1, 300),
    )
)

# Node-health vars live in a sibling for room (#19292); importing it here
# registers them whenever this module loads.
from autobot_shared import env_registry_slm_health  # noqa: E402,F401
