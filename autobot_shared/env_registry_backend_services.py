# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Backend-services AUTOBOT_* environment variable registrations.

New sibling module (#15710), following the pattern ``env_registry_slm.py``'s
docstring records: ``env_registry.py`` is closed to new entries -- it sits at
its grandfathered file-size ceiling (#14236) with no slack, so a variable
that needs registering goes in its own per-component module instead of
raising that ceiling. ``env_registry_agent_runtime.py`` holds the sibling
population sized in the same sweep for the agent-loop/orchestration side;
this one holds the rest -- chat, sessions, workspaces, memory, notifications,
auth, tooling, and knowledge indexing.

These were read through a bare ``int(os.environ.get(...))`` /
``float(os.environ.get(...))`` cast until #15710 converted each to
``autobot_shared.env_utils``'s ``env_int``/``env_float`` -- crash-safe, but
still unregistered, because ``check_env_var_registry.py`` derives its reader
set from ``os.getenv`` and the ``env_utils`` helper names, and had never
seen ``os.environ.get`` either. Converting made them visible to that
checker for the first time; this module is what answers it.

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
        name="AUTOBOT_DESKTOP_CONTROL_LOCK_TTL_SECONDS",
        type=int,
        default=120,
        description=(
            "Idle-TTL for a desktop-control lock: if not refreshed within "
            "this window, it auto-expires and control returns to the agent. "
            "Raising it tolerates a longer human takeover before "
            "auto-release; lowering it returns control to the agent sooner "
            "after the human goes idle (api/desktop_control_lock.py)."
        ),
        component="desktop",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SESSION_ROLE_TTL_SECONDS",
        type=int,
        default=86400,
        description=(
            "TTL, in seconds, for a chat session's role binding in Redis. "
            "Raising it keeps a session's assigned role valid longer between "
            "activity; lowering it expires it sooner, requiring the role to "
            "be re-resolved (chat_workflow/session_role.py)."
        ),
        component="chat_workflow",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SESSION_WORK_ITEM_TTL_SECONDS",
        type=int,
        default=86400,
        description=(
            "TTL, in seconds, for a chat session's work-item binding in "
            "Redis. Raising it keeps the session-to-work-item link valid "
            "longer between activity; lowering it expires it sooner "
            "(chat_workflow/session_work_item.py)."
        ),
        component="chat_workflow",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SHARED_LINK_DEFAULT_TTL",
        type=int,
        default=0,
        description=(
            "Default TTL, in seconds, applied to a newly created chat shared "
            "link when the caller does not specify one (0 means the link "
            "never expires unless a TTL is explicitly requested). Raising it "
            "shortens how long a share defaults to being valid before "
            "expiring (api/chat_shared_links.py)."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SHARED_LINK_ACCESS_RPM",
        type=int,
        default=10,
        description=(
            "Per-client-IP requests-per-minute ceiling on the unauthenticated "
            "shared-link /access endpoint (GH#9127). Raising it tolerates a "
            "faster burst of password attempts before rate-limiting; "
            "lowering it rate-limits sooner (api/chat_shared_links.py)."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SHARED_LINK_ACCESS_RPH",
        type=int,
        default=100,
        description=(
            "Per-client-IP requests-per-hour ceiling on the unauthenticated "
            "shared-link /access endpoint (GH#9127). Raising it tolerates "
            "more password attempts per hour before rate-limiting; lowering "
            "it hardens against brute force sooner, at the risk of blocking "
            "a legitimate slow guesser (api/chat_shared_links.py)."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CODE_INDEX_GIT_TIMEOUT_SECONDS",
        type=int,
        default=10,
        description=(
            "Ceiling on each read-only git call the code indexer's "
            "provenance lookups make. Raising it tolerates a slower git "
            "history walk on a large repo; lowering it fails a stalled git "
            "call faster, at the risk of a false timeout on a legitimately "
            "slow repo (services/knowledge/code_indexer.py)."
        ),
        component="knowledge",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_COGNIFIER_BATCH_MAX_TOKENS_PER_CHUNK",
        type=int,
        default=1024,
        description=(
            "Per-chunk token budget used to scale max_tokens with the number "
            "of chunks packed into one batched cognifier extraction call "
            "(#11012). Raising it reduces truncation risk for large chunks; "
            "lowering it caps per-chunk cost, at the risk of truncating "
            "longer chunks (knowledge/pipeline/cognifiers/llm_utils.py)."
        ),
        component="knowledge",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_COGNIFIER_BATCH_MAX_TOKENS_CAP",
        type=int,
        default=8192,
        description=(
            "Absolute ceiling on the max_tokens sent for a batched cognifier "
            "extraction call, regardless of batch size (#11012). Raising it "
            "allows a larger batched response before truncation; lowering it "
            "protects against an oversized request to the LLM provider "
            "(knowledge/pipeline/cognifiers/llm_utils.py)."
        ),
        component="knowledge",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_VERBATIM_RECENCY_WEIGHT",
        type=float,
        default=0.2,
        description=(
            "Weight blending recency decay into verbatim recall's similarity "
            "ranking (GH#11163); 0.0 disables the blend (pure semantic "
            "order). Raising it favors recent turns more over "
            "equally-similar older ones; lowering it toward 0 reverts closer "
            "to pure semantic ranking (memory/verbatim_store.py)."
        ),
        component="memory",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_VERBATIM_RECENCY_HALFLIFE_SECONDS",
        type=float,
        default=7 * 24 * 3600,
        description=(
            "Half-life, in seconds, of the exponential recency decay applied "
            "when re-ranking verbatim recall results (GH#11163). Raising it "
            "makes recency matter over a longer window (older turns stay "
            "competitive longer); lowering it decays older turns faster, "
            "favoring very recent ones more strongly (memory/verbatim_store.py)."
        ),
        component="memory",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_WORKSPACE_MAX_COUNT",
        type=int,
        default=20,
        description=(
            "Maximum number of concurrent task workspace containers allowed "
            "(GH#10544). Raising it allows more concurrent workspaces at the "
            "cost of more host resource usage; lowering it caps concurrent "
            "workspace count more tightly (services/docker_task_workspace.py)."
        ),
        component="workspace",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_WORKSPACE_DISK_MB",
        type=int,
        default=2048,
        description=(
            "Disk quota, in MB, applied to a task workspace's storage_opt "
            "size where the storage driver honours it (GH#10544, GH#11694). "
            "Raising it allows a workspace to use more disk; lowering it "
            "caps it more tightly (services/docker_task_workspace.py)."
        ),
        component="workspace",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_WORKSPACE_IDLE_SECONDS",
        type=int,
        default=4 * 3600,
        description=(
            "Idle-expiry window, in seconds, after which an unused task "
            "workspace container is torn down (GH#10544). Raising it keeps "
            "an idle workspace around longer for reuse; lowering it "
            "reclaims idle workspace resources sooner "
            "(services/docker_task_workspace.py)."
        ),
        component="workspace",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_WORKSPACE_CPU_QUOTA",
        type=int,
        default=100000,
        description=(
            "CPU quota (Docker cpu-quota microseconds per 100ms period) "
            "applied to a task workspace container (GH#10544). Raising it "
            "allows a workspace container more CPU time per period; "
            "lowering it throttles it more tightly "
            "(services/docker_task_workspace.py)."
        ),
        component="workspace",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_WORKSPACE_PIDS_LIMIT",
        type=int,
        default=512,
        description=(
            "PID-count limit (Linux pids cgroup) applied to a task workspace "
            "container, capping process count so a fork-bomb inside it "
            "cannot exhaust host PIDs (GH#11059). Raising it allows more "
            "processes inside a workspace; lowering it hardens against a "
            "fork-bomb more tightly, at the risk of limiting legitimate "
            "parallelism (services/docker_task_workspace.py)."
        ),
        component="workspace",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PUSH_NOTIFICATION_TTL",
        type=int,
        default=86400,
        description=(
            "TTL, in seconds, applied to a web-push notification payload "
            "(#6743). Raising it lets a push provider retry delivery over a "
            "longer window; lowering it drops a stale, undelivered "
            "notification sooner (services/push_notification_service.py)."
        ),
        component="notifications",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RUN_JWT_DENYLIST_TIMEOUT_S",
        type=float,
        default=2.0,
        description=(
            "Redis lookup budget, in seconds, for the run-JWT denylist check "
            "on the auth path (#12751). Raising it tolerates a slower Redis "
            "before treating it as unavailable (fail-closed); lowering it "
            "falls over to fail-closed sooner on a slow Redis "
            "(services/run_jwt.py)."
        ),
        component="auth",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MAX_UNMATCHED_OUTPUT_CHARS",
        type=int,
        default=20000,
        description=(
            "Cap on unmatched tool-output characters retained before the "
            "filter truncates. Raising it keeps more raw output for "
            "unmatched patterns; lowering it truncates sooner, reducing "
            "memory/storage per tool call (services/tool_output_filter.py)."
        ),
        component="tools",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TEE_RETENTION_HOURS",
        type=int,
        default=168,
        description=(
            "Hours an oversized tool-output tee file is kept on disk before "
            "being pruned (#14142). Raising it keeps oversized captured "
            "output available longer for later inspection; lowering it "
            "prunes it sooner, saving disk (services/tool_output_filter.py)."
        ),
        component="tools",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PAPERCLIP_COMMENT_DEDUP_TTL",
        type=int,
        default=3600,
        description=(
            "TTL, in seconds, for the idempotency key that deduplicates a "
            "Paperclip issue comment. Raising it widens the window in which "
            "a retried comment is treated as a duplicate; lowering it "
            "narrows that window, risking a duplicate comment on a slow "
            "retry (autobot_shared/paperclip_client.py)."
        ),
        component="paperclip",
    )
)
