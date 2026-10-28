# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Knowledge-component AUTOBOT_* environment variable registrations.

Split out of ``env_registry_backend_services.py`` because adding these there
would push it past the file-size ceiling (600 lines).

Registration contract (import side effect, ordering): see ``env_registry``.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_KB_CHUNK_MAX_TOKENS",
        type=int,
        default=800,
        description=(
            "Token budget (~4 chars per token) per stored chunk when KnowledgeBase.add_document "
            "splits a long document; read by knowledge/document_ingest.py (#17830)."
        ),
        component="knowledge",
        range=(50, 100000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_KB_INGEST_RECORD_TTL_SECONDS",
        type=int,
        default=2592000,
        description=(
            "Seconds a per-document ingest status record (success/partial/timeout) is kept so a "
            "retry can resume after the last stored chunk; read by knowledge/document_ingest.py (#17986)."
        ),
        component="knowledge",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHROMA_REPAIR_LOCK_TIMEOUT_SECONDS",
        type=float,
        default=30.0,
        description=(
            "Total seconds to wait for the cross-process lock that guards the local ChromaDB "
            "store repairs before giving up; on timeout the store still opens and the repairs "
            "retry on the next open; read by utils/chromadb_store_repairs.py (#18789)."
        ),
        component="knowledge",
        range=(0.1, 3600.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_REDIS_SCAN_COUNT",
        type=int,
        default=1000,
        description=(
            "COUNT hint for every pattern walk through autobot_shared/redis_scan.py: keys the "
            "server examines per SCAN call. redis-py defaults to 10, which turns a 1500-key "
            "keyspace into ~150 round trips per walk (#18999)."
        ),
        component="knowledge",
        range=(10, 100000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_KB_METRICS_COUNT_REFRESH_SECONDS",
        type=float,
        default=300.0,
        description=(
            "Minimum seconds between the doc:* and kb_cache:* keyspace walks that feed the "
            "kb_vector_count / kb_cache_entries gauges; the cached count is served in between; "
            "read by utils/system_metrics.py (#18999)."
        ),
        component="knowledge",
        range=(1.0, 86400.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_KB_RETRY_COOLDOWN_SECONDS",
        type=int,
        default=60,
        description=(
            "Seconds after a failed knowledge-base initialization during which every access "
            "path returns None instead of retrying ChromaDB; force_refresh bypasses it; read "
            "by knowledge_factory.py (#3094, #18122)."
        ),
        component="knowledge",
        range=(1, 86400),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EMBEDDING_OVERRIDE_CACHE_SECONDS",
        type=float,
        default=5.0,
        description=(
            "Seconds each process caches the user's embedding-model override (Redis key "
            "autobot:kb:embedding_model) before re-reading it, so a switch reaches every reader "
            "within this window; read by autobot_shared/embedding_model.py (#19377)."
        ),
        component="knowledge",
        range=(0.0, 300.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EMBEDDING_SPACE_CHECK_SECONDS",
        type=float,
        default=5.0,
        description=(
            "Seconds between a knowledge-base process's checks for an embedding-model switch made "
            "in another process; on a newer generation it rebinds its collection, write buffer and "
            "embed model (knowledge/embedding_space_binding.py, #19379)."
        ),
        component="knowledge",
        range=(0.0, 300.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EMBEDDING_SWITCH_BATCH_SIZE",
        type=int,
        default=64,
        description=(
            "Facts re-embedded per call to the embedding provider while an embedding-model switch "
            "rebuilds the knowledge base into a new collection (knowledge/embedding_switch.py, #19379)."
        ),
        component="knowledge",
        range=(1, 1000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EMBEDDING_SWITCH_STALE_SECONDS",
        type=float,
        default=300.0,
        description=(
            "Seconds without a heartbeat after which a running embedding-model switch is stale (its "
            "worker presumed dead): its Redis lock expires, the status reads stale, and a new start or a "
            "cancel recovers (knowledge/embedding_switch.py, #19379)."
        ),
        component="knowledge",
        range=(30.0, 86400.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EMBEDDING_SWITCH_DEADLINE_SECONDS",
        type=float,
        default=21600.0,
        description=(
            "Overall deadline for an embedding-model switch, from start to cutover; a build past it fails"
            " and leaves the active model and collection unchanged (knowledge/embedding_switch.py, "
            "#19379)."
        ),
        component="knowledge",
        range=(60.0, 604800.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EMBEDDING_SWITCH_SETTLE_MARGIN_SECONDS",
        type=float,
        default=2.0,
        description=(
            "Seconds added to the override cache and space-check windows while an embedding-model switch "
            "waits, after cutover, for every process to rebind before its final replay "
            "(knowledge/embedding_switch.py, #19379)."
        ),
        component="knowledge",
        range=(0.0, 300.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EMBEDDING_SWITCH_REPLAY_ROUNDS",
        type=int,
        default=5,
        description=(
            "Rounds an embedding-model switch replays writes made during the build, until none are "
            "pending and the new collection holds one vector per fact, before it gives up without "
            "switching (knowledge/embedding_switch.py, #19379)."
        ),
        component="knowledge",
        range=(1, 100),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EMBEDDING_PROBE_TIMEOUT_SECONDS",
        type=int,
        default=60,
        description=(
            "Seconds one background test embedding by the embedding_model health probe may run "
            "before it is abandoned and recorded as 'timed out'; read by "
            "api/embedding_model_health.py (#18834)."
        ),
        component="knowledge",
        range=(1, 600),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EMBEDDING_PROBE_TTL_SECONDS",
        type=int,
        default=300,
        description=(
            "Seconds a background test embedding of the configured embedding model stays valid "
            "for the embedding_model health probe before it is re-run; read by "
            "api/embedding_model_health.py (#18834)."
        ),
        component="knowledge",
        range=(10, 86400),
    )
)

# Where the knowledge indexers (and every other regenerable cache) keep their caches (#19553).
register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CACHE_DIR",
        type=str,
        default=None,
        description=(
            "Root for every regenerable cache (autobot_shared.paths.cache_root, #19553). Unset: "
            "$XDG_CACHE_HOME/autobot, else ~/.cache/autobot; a value inside the code tree is skipped. "
            "A container whose HOME is under the project root should mount a volume here."
        ),
        component="backend",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_KB_TENANT_GROUPS_TTL_SECONDS",
        type=int,
        default=60,
        description=(
            "Seconds a user's team memberships, resolved for the KB visibility principal of a "
            "tenant-context route, are reused before the team service is asked again; a membership "
            "removal or team delete bumps the organisation's membership epoch and drops every "
            "worker's entries at once; an epoch that cannot be read re-resolves and neither serves nor "
            "fills the cache, so this window bounds staleness only after a bump exhausts its "
            "retries; 0 disables the cache; read by "
            "knowledge/tenant_groups.py (#19007, #19630)."
        ),
        component="knowledge",
        range=(0, 3600),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MEMBERSHIP_EPOCH_BUMP_ATTEMPTS",
        type=int,
        default=3,
        description=(
            "Tries the post-commit bump of an organisation's team-membership epoch gets before the "
            "failure is raised; every failed try is logged at error level; read by "
            "autobot_shared/membership_epoch.py (#19630)."
        ),
        component="knowledge",
        range=(1, 10),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MEMBERSHIP_EPOCH_BUMP_BACKOFF_SECONDS",
        type=float,
        default=0.2,
        description=(
            "Seconds before the second try of a failed team-membership epoch bump; doubles on each "
            "further try; read by autobot_shared/membership_epoch.py (#19630)."
        ),
        component="knowledge",
        range=(0.0, 10.0),
    )
)
