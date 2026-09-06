# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backend AUTOBOT_* environment variables, split out of ``env_registry`` (#15624).

``env_registry.py`` sat at exactly its recorded size ceiling, so registering ANY
new environment variable — in any component — failed the file-size ratchet. The
ratchet is right that a grandfathered file should not grow; its premise simply
does not fit a registry, whose length measures how much configuration the system
has rather than how tangled the module is.

The split follows the data: every spec already carries a ``component``, so the
grouping is the one the registry itself declares. This module holds the
``backend`` component, the largest group at 35 of 208 entries.

Importing this module is what registers them, so ``env_registry`` imports it for
its side effect. Nothing here is re-exported and nothing imports it directly.
"""

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_BACKEND_HOST",
        type=str,
        default="10.0.0.1",
        description="Hostname or IP address of the AutoBot backend service.",
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_BACKEND_PORT",
        type=str,
        default="8001",
        description="TCP port of the AutoBot backend service.",
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_AUDIT_MAX_DEFERRED",
        type=int,
        default=10000,
        description=(
            "Ceiling on audit records held in the deferred queue when the sink "
            "is unavailable. Beyond it the oldest are dropped, bounding memory "
            "rather than letting an outage grow it without limit."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_AUDIT_FILING_STATUS_TTL_S",
        type=int,
        default=2592000,
        description=(
            "Seconds the audit worker's filing-health record survives in Redis. "
            "Refreshed on every run and at worker startup, so this only has to "
            "outlive the longest gap between runs (the claims audit is weekly); "
            "it exists so a record left by a worker that has since stopped does "
            "not keep answering for one that no longer exists (#13570)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CODE_ANALYSIS_POOL_WORKERS",
        type=int,
        default=2,
        description=(
            "Child processes used to offload code analysis. Deliberately small: "
            "each carries a full interpreter, and analysis is bursty rather than "
            "sustained."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CODE_ANALYSIS_POOL_MAX_TASKS",
        type=int,
        default=8,
        description=(
            "Tasks a code-analysis child handles before it is recycled. Recycling "
            "bounds memory growth in long-lived children."
        ),
        component="backend",
    )
)

# --- skill distillation (#14255) ---------------------------------------------
register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SKILL_DISTILLATION_MAX_FAILURES",
        type=int,
        default=3,
        description=(
            "Consecutive failures on the SAME conversation before the distillation "
            "pass stops waiting for it and moves on. Below this the pass halts and "
            "retries next run, so a transient fault costs nothing; at it, the "
            "conversation is quarantined with a warning and the cursor advances, so "
            "one unreadable conversation cannot starve every newer one behind it in "
            "an oldest-first queue (#14255). A success resets the count."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SKILL_DISTILLATION_FAILURE_TTL_S",
        type=int,
        default=86_400,
        description=(
            "How long a conversation's consecutive-failure count survives, in "
            "seconds. Derived as 24 distillation intervals, so failures accumulate "
            "across passes rather than expiring between them, while a counter for a "
            "conversation nobody retries eventually clears instead of accumulating "
            "forever (#14255)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_BROWSER_STATE_PROMPT_MAX_ELEMENTS",
        type=int,
        default=30,
        description=(
            "How many numbered elements the LLM-visible state block renders per browser "
            "tool result. The browser worker caps the raw list separately; this bounds only "
            "what reaches the prompt (#11537)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_COCHANGE_GIT_TIMEOUT_SECONDS",
        type=int,
        default=120,
        description=("Seconds the co-change history walk may run before it is abandoned."),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_COCHANGE_MAX_FILES_PER_COMMIT",
        type=int,
        default=50,
        description=(
            "Commits touching more files than this are ignored as coupling evidence: a bulk "
            "rename, a vendored-tree import or a reformat is not a signal (#13639)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_COCHANGE_MIN_CO_CHANGES",
        type=int,
        default=3,
        description=(
            "How many commits two files must share before the pair is reported at all. One "
            "shared commit is a coincidence."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_COCHANGE_STRENGTH_THRESHOLD",
        type=float,
        default=0.3,
        description=(
            "Minimum normalised coupling strength to report. Independent of the count "
            "threshold: a pair can clear the count and still be weak if either file changes "
            "constantly."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_COCHANGE_WINDOW_DAYS",
        type=int,
        default=180,
        description=(
            "Days of history the co-change analysis considers. Coupling decays — a pair "
            "that moved together two years ago is history, not structure."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_OWNERSHIP_BLAME_TIMEOUT_SECONDS",
        type=float,
        default=10.0,
        description=(
            "Seconds a single `git blame` may take during ownership analysis. Must stay "
            "below the whole-analysis budget, which a previous 30s value exceeded (#13602)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_OWNERSHIP_BUDGET_SECONDS",
        type=float,
        default=20.0,
        description=(
            "Total seconds ownership analysis may spend blaming files before it returns " "what it has (#13602)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_OWNERSHIP_MAX_FILES",
        type=int,
        default=2000,
        description=(
            "How many files ownership analysis will blame. Paired with the time budget "
            "because a file count alone is the wrong bound — file size dominates blame cost "
            "(#13602)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SKILL_DISTILLATION_ENABLED",
        type=bool,
        default=False,
        description=(
            "Master switch for skill distillation. Ships inert — enable once the LLM cost "
            "of a recurring pass is accepted."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SKILL_DISTILLATION_IDLE_FLUSH_S",
        type=int,
        default=900,
        description=(
            "Seconds of corpus idleness after which a distillation pass runs early. Without "
            "it the pass is purely clock-bound and a conversation ending at 09:00 waits for "
            "the small hours (#13695)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SKILL_DISTILLATION_INTERVAL_S",
        type=int,
        default=3600,
        description=("Seconds between skill distillation passes."),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SKILL_DISTILLATION_MAX_SESSIONS",
        type=int,
        default=10,
        description=(
            "Conversations distilled per pass. Bounds the LLM spend of any one run; the "
            "remainder is picked up next time because the cursor only advances over what "
            "was handled."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SKILL_DISTILLATION_MIN_MESSAGES",
        type=int,
        default=4,
        description=(
            "Minimum messages a conversation needs before distillation attempts it. Shorter "
            "ones cannot contain a reusable workflow and the extractor rejects them anyway."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_REMEDIATION_HEARTBEAT_WAIT_S",
        type=int,
        default=90,
        description=(
            "Seconds to wait for a heartbeat after the reconciler restarts a node's agent "
            "before recording the remediation as failed. Remediation exists to restore the "
            "heartbeat, so the heartbeat is what success means — the restart exiting 0 only "
            "says the command ran (services/reconciler.py, #14344)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_REMEDIATION_HEARTBEAT_POLL_S",
        type=int,
        default=5,
        description=(
            "How often to re-read the node row while waiting for a post-restart heartbeat "
            "(services/reconciler.py, #14344)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RESTART_CHURN_WINDOW_S",
        type=int,
        default=600,
        description=(
            "Seconds a managed autobot/slm-agent service is reported as CURRENTLY churning after "
            "its last observed n_restarts increase, for node-status degrade purposes. Must clear "
            "health_collector's own 300s discovery-cache TTL by a comfortable margin — a shorter "
            "window only fires on the beat that happens to land on a cache refresh "
            "(services/reconciler.py, #14465)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_REMEDIATION_TRACKER_EXPIRY_S",
        type=int,
        default=1800,
        description=(
            "Seconds a non-exhausted remediation attempt tracker may sit with no NEW attempt "
            "before its count is forgiven. Clamped strictly above REMEDIATION_COOLDOWN plus a "
            "reconcile-tick margin — a lower value forgives an attempt in the same instant one "
            "becomes due, so count could never exceed 1 (services/reconciler.py, #14465)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_REMEDIATION_PLAYBOOK_TIMEOUT_S",
        type=int,
        default=180,
        description=(
            "Wall-clock ceiling on the ansible-playbook subprocess _restart_service_via_ansible "
            "launches. Previously unbounded — a hung SSH connection or stuck remote task blocked "
            "remediation for a node indefinitely. manage-service.yml (the only playbook this call "
            "path runs) is a single-host, single-service restart that normally completes in "
            "seconds; 180s stays comfortably below REMEDIATION_COOLDOWN (300s) while giving "
            "generous headroom (services/reconciler.py, services/playbook_executor.py, #14524)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_UPDATE_CODE_SOURCE_GIT_TIMEOUT_S",
        type=int,
        default=30,
        description=(
            "Per-command timeout for the git checkout/fetch/reset subcommands "
            "PlaybookExecutor._update_code_source runs before every playbook. On expiry the "
            "WHOLE process group is killed (not just git's own pid), since git can leave an "
            "ssh/credential-helper child holding the output pipes open "
            "(services/playbook_executor.py, #14524)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_UPDATE_CODE_SOURCE_REV_PARSE_TIMEOUT_S",
        type=int,
        default=10,
        description=(
            "Timeout for the best-effort 'git rev-parse --short HEAD' traceability log "
            "PlaybookExecutor._update_code_source runs after a successful sync "
            "(services/playbook_executor.py, #14524)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SERVICE_RESTART_PLAYBOOK_TIMEOUT_S",
        type=int,
        default=2100,
        description=(
            "Wall-clock ceiling on _restart_service_via_ansible when it restarts an arbitrary "
            "ServiceCategory.AUTOBOT unit (_remediate_failed_service), as opposed to the "
            "lightweight slm-agent restart (AUTOBOT_REMEDIATION_PLAYBOOK_TIMEOUT_S). That "
            "category is populated by unit-name pattern match (postgresql*, redis*, docker*, "
            "...), an open-ended set that includes Type=oneshot units with a multi-minute "
            "TimeoutStartSec (autobot-pg-backup.service.j2 declares 1800s) -- reusing the "
            "slm-agent budget here would SIGKILL a legitimate long-running restart "
            "(services/reconciler.py, #14524)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PLAYBOOK_KILL_GRACE_S",
        type=float,
        default=5.0,
        description=(
            "Grace period between SIGTERM and SIGKILL when killing a timed-out playbook "
            "subprocess's whole process group. Long enough for ansible-playbook / a forked ssh "
            "child to unwind cleanly; short enough that a wedged process does not itself become "
            "an unbounded second wait (services/playbook_executor.py, #14524)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MAX_ATTEMPTS_REFUSAL_BROADCAST_INTERVAL_S",
        type=int,
        default=3600,
        description=(
            "How often to re-broadcast that a node is still at MAX_REMEDIATION_ATTEMPTS. "
            "Once exhausted, last_attempt freezes and this refusal is refused again on every "
            "reconcile pass forever — unthrottled, that is once per reconcile_interval "
            "(services/reconciler.py, #14465)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PLAYBOOK_FAILURE_TAIL_CHARS",
        type=int,
        default=500,
        description=(
            "How many characters of a failed playbook's output to fall back to when no "
            "failed task can be parsed out of it. Taken from the END of the run: ansible "
            "opens with its banner, so a head slice returns deprecation warnings and hides "
            "the failure (services/ansible_utils.py, #14298)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SYNC_POST_CMD_TIMEOUT_S",
        type=int,
        default=300,
        description=(
            "Seconds a code-sync post-sync command may run before it is abandoned. "
            "It covers a dependency install, so the ceiling depends on link speed "
            "and wheel availability rather than on anything fixed "
            "(services/sync_orchestrator.py, #14275)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_GIT_PROBE_TIMEOUT_SECONDS",
        type=int,
        default=30,
        description=(
            "Seconds a git subprocess started through autobot_shared.git_probe may run "
            "before it is abandoned, so a probe cannot hang on a lock or a prompt (#15783)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SANDBOX_GIT_STATUS_TIMEOUT_SECONDS",
        type=int,
        default=10,
        description=(
            "Seconds the sandbox delete guard waits for `git status --porcelain` "
            "before treating the work tree as unverifiable and refusing the "
            "recursive delete (api/sandbox_files.py, #15777)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_IDEMPOTENCY_TTL_SECONDS",
        type=int,
        default=86400,
        description=(
            "How long a completed creation stays replayable for its Idempotency-Key. Long enough to "
            "outlive any retry an agent or proxy makes, short enough that the keyspace stays bounded "
            "(autobot_shared/idempotency.py, #15778)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_IDEMPOTENCY_CLAIM_TTL_SECONDS",
        type=int,
        default=300,
        description=(
            "How long an in-flight idempotency claim is held before another caller may retry it. A "
            "request that dies between claiming and completing would otherwise wedge the key for the "
            "full replay TTL (autobot_shared/idempotency.py, #15778)."
        ),
        component="backend",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_IDEMPOTENCY_CLAIM_ATTEMPTS",
        type=int,
        default=3,
        description=(
            "How many times an idempotency claim re-runs its atomic SET NX after the record it lost "
            "to turns out to have expired. Reporting 'unseen' at that point would let every loser of "
            "the race create (autobot_shared/idempotency.py, #15778)."
        ),
        component="backend",
    )
)
