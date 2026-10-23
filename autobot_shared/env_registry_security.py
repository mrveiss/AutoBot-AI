# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Security AUTOBOT_* environment variable registrations.

Split out of ``env_registry.py`` rather than added inline, for the reason that
file's own docstring gives: a new variable goes in an
``env_registry_<component>.py`` sibling. The mechanical reason is the one
``env_registry_logging.py`` records — ``env_registry.py`` sits at its
grandfathered file-size ceiling (#14236) with no slack, and the ratchet forbids
raising a ceiling to make room, so an inline registration cannot land there at
all.

#13602 added the first ``component="security"`` variable, so this is the
component's first home rather than a move of existing entries.

Registration contract (import side effect, ordering): see ``env_registry`` (#16415).
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LOG_VALUE_MAX_CHARS",
        type=int,
        default=256,
        description=(
            "Longest untrusted value sanitize_log_value() will interpolate into a log line "
            "(#13602). Beyond it the value is truncated with an explicit marker, so the "
            "subject of a rejected request cannot pad the log store out. A negative value is "
            "rejected in favour of the default: disabling the bound would defeat the guard."
        ),
        component="security",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EGRESS_INTERNAL_ORIGINS_TTL_S",
        type=int,
        default=60,
        description=(
            "Seconds the egress policy reuses the origins returned by registered internal-origin "
            "providers (e.g. SLM-managed nodes) before asking them again (#17576). Static origins "
            "from the SSOT are never cached. A provider that raises is logged and skipped."
        ),
        component="security",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EXECUTION_MEMORY_LIMIT",
        type=str,
        default="512m",
        description=(
            "Memory cap (Docker memory string) for pooled and snapshot-restored execution "
            "containers; swap is capped at the same value, so there is no swap (#17267). "
            "Cold-start tasks size their own cap from the task's resource limits. Raising it "
            "lets warm-pool code use more memory before the kernel OOM-kills it "
            "(autobot_shared/container_hardening.py)."
        ),
        component="security",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EGRESS_PROVIDER_TIMEOUT_S",
        type=int,
        default=5,
        description=(
            "Seconds one internal-origin provider may run before it is abandoned for this refresh "
            "(#17576). A provider that times out or raises is logged and skipped; the static SSOT "
            "origins still apply."
        ),
        component="security",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EXECUTION_TMPFS_SIZE",
        type=str,
        default="64m",
        description=(
            "Size of the scratch tmpfs (mounted noexec,nosuid at the container scratch path) "
            "that a read-only execution container writes to (#17267). Raising it lets code "
            "stage larger temporary files; lowering it fails writes sooner "
            "(autobot_shared/container_hardening.py)."
        ),
        component="security",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PROMETHEUS_SCRAPE_TOKEN",
        type=str,
        default="",
        description=(
            "Read-only bearer token Prometheus presents to /api/metrics/prometheus (#16375). "
            "Seeded by the SLM into its secret store and rendered by the deploy roles into "
            "backend.env and Prometheus' bearer_token_file. Unset refuses every scrape."
        ),
        component="security",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RUM_INGEST_RATE_LIMIT",
        type=int,
        default=120,
        description=(
            "Requests per client address per minute accepted by the anonymous RUM ingest "
            "routes, /api/rum/event and /api/rum/metrics (#16375). Over it the caller gets 429 "
            "and nothing is written."
        ),
        component="security",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RUM_EVENT_MAX_BYTES",
        type=int,
        default=16384,
        description="Largest request body /api/rum/event accepts; larger is refused with 413 (#16375).",
        component="security",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RUM_METRICS_MAX_BYTES",
        type=int,
        default=65536,
        description="Largest request body /api/rum/metrics accepts; larger is refused with 413 (#16375).",
        component="security",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RUM_MAX_EVENTS",
        type=int,
        default=5000,
        description="RUM events held in memory; the oldest is dropped as each new one arrives (#16375).",
        component="security",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RUM_MAX_SESSIONS",
        type=int,
        default=1000,
        description=(
            "RUM session tallies held in memory (#16375). An anonymous caller mints a session id "
            "per request at will, so the table is capped and the oldest session is evicted."
        ),
        component="security",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RUM_METRICS_MAX_ITEMS",
        type=int,
        default=100,
        description="Longest list in any field of a /api/rum/metrics batch; longer is refused with 422 (#18368).",
        component="security",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RUM_METRICS_MAX_FIELD_CHARS",
        type=int,
        default=512,
        description="Longest string anywhere in a /api/rum/metrics batch; longer is refused with 422 (#18368).",
        component="security",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RUM_LABEL_MAX_VALUES",
        type=int,
        default=50,
        description=(
            "Distinct values each frontend RUM metric label admits; later new values record as "
            "'other', so anonymous input cannot create unbounded Prometheus series (#18368)."
        ),
        component="security",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RUM_LABEL_MAX_CHARS",
        type=int,
        default=128,
        description="Longest frontend RUM metric label value; longer records as 'other' (#18368).",
        component="security",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SECRETS_BACKUP_MAX_AGE_S",
        type=int,
        default=86400,
        description=(
            "Longest age, in seconds, of a secrets-store backup that a destructive secrets "
            "proposal (e.g. the OAuth bundle strip) accepts as its safety net (#18281). Older "
            "backups are refused, so the verifier fails closed. Default is one day: long enough "
            "to cover human approval latency, short enough that few secrets changed since. "
            "Lowering it demands a fresher backup before each destructive action."
        ),
        component="security",
        range=(60, 2592000),
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PROVIDER_KEY_HYDRATION_TIMEOUT_S",
        type=int,
        default=30,
        description=(
            "Seconds a process waits for its one-time provider-key vault hydration before treating the "
            "vault as unreachable (#18094). On timeout every vault-resolved key is refused (fail closed); a "
            "hydration that finishes later still swaps its result in."
        ),
        component="security",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PROVIDER_KEY_REHYDRATE_BACKOFF_S",
        type=int,
        default=30,
        description=(
            "First delay before a process whose provider-key vault was unreachable tries to hydrate again on a "
            "later key resolution (#18094). Doubles after each failed retry, capped at 20x this value; a "
            "successful hydration resets it. Until a retry succeeds, keys stay refused, never served from env."
        ),
        component="security",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MCP_GIT_RATE_LIMIT",
        type=int,
        default=60,
        description=(
            "Requests per 60-second window accepted by the Git MCP bridge (/api/git_mcp/*), shared by all workers "
            "(#18087). One Redis-backed count across all workers; over it the caller is refused "
            "(HTTP 429, or JSON-RPC -32029 on the MCP server). Fails open while Redis is unreachable."
        ),
        component="security",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MCP_BROWSER_RATE_LIMIT",
        type=int,
        default=60,
        description=(
            "Requests per 60-second window accepted by the browser automation MCP bridge, shared by all workers "
            "(#18087). One Redis-backed count across all workers; over it the caller is refused "
            "(HTTP 429, or JSON-RPC -32029 on the MCP server). Fails open while Redis is unreachable."
        ),
        component="security",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MCP_DATABASE_RATE_LIMIT",
        type=int,
        default=60,
        description=(
            "Requests per 60-second window accepted by the database MCP bridge, shared by all workers "
            "(#18087). One Redis-backed count across all workers; over it the caller is refused "
            "(HTTP 429, or JSON-RPC -32029 on the MCP server). Fails open while Redis is unreachable."
        ),
        component="security",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MCP_HTTP_CLIENT_RATE_LIMIT",
        type=int,
        default=120,
        description=(
            "Requests per 60-second window accepted by the HTTP client MCP bridge, shared by all workers "
            "(#18087). One Redis-backed count across all workers; over it the caller is refused "
            "(HTTP 429, or JSON-RPC -32029 on the MCP server). Fails open while Redis is unreachable."
        ),
        component="security",
    )
)


register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MCP_SERVER_RATE_LIMIT",
        type=int,
        default=50,
        description=(
            "Requests per 60-second window accepted per token by the AutoBot MCP server (post-auth), shared by all "
            "workers (#18087). One Redis-backed count across all workers; over it the caller is refused "
            "(HTTP 429, or JSON-RPC -32029 on the MCP server). Fails open while Redis is unreachable."
        ),
        component="security",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RATE_LIMITER_FAIL_OPEN_WARN_INTERVAL",
        type=float,
        default=60.0,
        description=(
            "Minimum seconds between fail-open warnings per rate-limiter instance (#18617). While Redis is "
            "unreachable the limiters allow requests; the warning names only the limiter scope and is emitted "
            "at most once per interval so an outage cannot flood the log."
        ),
        component="security",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_JWT_CLOCK_SKEW_LEEWAY_SECONDS",
        type=int,
        default=5,
        description=(
            "Clock-skew tolerance in seconds for JWT verification (#18792). A backward "
            "wall-clock step (WSL2) or skew between issuing and verifying hosts otherwise "
            "rejects a fresh token whose iat is ahead of the verifier's clock. Applies to the iat "
            "and nbf claims only; exp stays strict. Clamped to 0-60."
        ),
        component="security",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_THREAT_INTEL_CACHE_TTL",
        type=int,
        default=7200,
        description=(
            "Seconds a threat-intelligence verdict (VirusTotal/URLVoid) stays cached in-process "
            "(#18888). Measured on a monotonic clock, so a wall-clock step cannot extend it. Clamped to 1-604800."
        ),
        component="security",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_FEATURE_FLAG_CACHE_TTL_SECONDS",
        type=float,
        default=5.0,
        description=(
            "Seconds this process serves the access-control enforcement mode and per-endpoint "
            "overrides from memory (#18998). A write in the same process invalidates at once; "
            "a write from another process is seen within this window. 0 disables the cache. "
            "Clamped to 0-60."
        ),
        component="security",
        range=(0, 60),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CONFIG_REGISTRY_CACHE_TTL_SECONDS",
        type=float,
        default=60.0,
        description=(
            "Seconds the config registry serves a resolved value, and the fact that "
            "Redis holds nothing for a key, from process memory before asking Redis "
            "again. A change written by another process is visible within this window. "
            "Clamped to 0-3600: an hour is the longest a stale config value is tolerable "
            "without a restart; 0 disables the cache."
        ),
        component="redis",
        range=(0, 3600),
    )
)

# --- LLM provider sign-in (#19241) -------------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LLM_OAUTH_UNUSABLE_TTL_SECONDS",
        type=int,
        default=300,
        description=(
            "How long a signed-in LLM provider token whose refresh failed is skipped before "
            "another refresh is tried (llm_shared/provider_token_refresh.py). While skipped, "
            "calls fall through to the next credential (the system token, then the API key). "
            "Floored at 60 so the backoff cannot become a re-POST on every call."
        ),
        component="auth",
        range=(60, None),
    )
)
