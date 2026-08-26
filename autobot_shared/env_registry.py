# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Registry for AUTOBOT_* environment variables.

Provides discovery, documentation, and type-safe access.
All AUTOBOT_* vars must be registered here before use; the
``check_env_var_registry`` pre-commit hook enforces this.

Closes GH#7081.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EnvVarSpec:
    """Specification for a single AUTOBOT_* environment variable."""

    name: str  # e.g. "AUTOBOT_REDIS_HOST"
    type: type  # int, float, str, bool
    default: Any  # default value when not set
    description: str  # human-readable description
    component: str  # "redis", "auth", "otel", etc.
    range: tuple | None = None  # (min, max) for numeric vars
    deprecated_since: str | None = None
    replaces: list = field(default_factory=list)


REGISTRY: dict[str, EnvVarSpec] = {}


def register_env_var(spec: EnvVarSpec) -> None:
    """Add a spec to the global registry."""
    REGISTRY[spec.name] = spec


def env(name: str, default: Any = None) -> Any:
    """Type-safe env var accessor that enforces registry membership.

    Raises KeyError if *name* is not in REGISTRY — this is intentional:
    unregistered vars are not allowed in production code.
    """
    spec = REGISTRY.get(name)
    if spec is None:
        raise KeyError(f"Unregistered env var: {name}. " f"Add it to autobot_shared/env_registry.py before use.")
    raw = os.getenv(name)
    if raw is None:
        return spec.default if default is None else default
    try:
        if spec.type is bool:
            return raw.lower() in ("1", "true", "yes", "on")
        return spec.type(raw)
    except (ValueError, TypeError):
        return spec.default if default is None else default


# ---------------------------------------------------------------------------
# Registered variables — grouped by component
# ---------------------------------------------------------------------------

# The "ai" component (LLM/model config, delegation, chat trajectories) lives in
# a sibling module, split out to keep this file under its file-size ceiling
# (#14236, #14856). Importing it here — after EnvVarSpec/register_env_var/REGISTRY
# are defined above, and before anything below can observe the registry — is a
# side effect that fully populates the "ai" entries. See env_registry_ai.py.
from autobot_shared import env_registry_ai  # noqa: E402,F401

# --- events (#14817, #14818) -------------------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHANNEL_SEQ_KEY_PREFIX",
        type=str,
        default="autobot:events:seq:",
        description=("Redis key prefix for per-channel live-event sequence counters."),
        component="events",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHANNEL_STREAM_KEY_PREFIX",
        type=str,
        default="autobot:events:channel:",
        description=("Redis key prefix for per-channel live-event replay streams."),
        component="events",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHANNEL_STREAM_MAX_ENTRIES",
        type=int,
        default=1000,
        description=(
            "Events retained per channel for reconnect replay. A client whose "
            "last_event_id has fallen outside this window is told to resync "
            "rather than handed a partial history."
        ),
        component="events",
        range=(1, 1000000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHANNEL_STREAM_TTL_SECONDS",
        type=int,
        default=86400,
        description=("Idle expiry for a per-channel replay stream, so session and chat channels do not accumulate."),
        component="events",
        range=(60, 2592000),
    )
)


# --- backend ----------------------------------------------------------------

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
        name="AUTOBOT_BACKEND_URL",
        type=str,
        default="http://10.255.255.254:8001",
        description="Full base URL of the AutoBot backend service (overrides HOST+PORT).",
        component="backend",
    )
)

# --- chat -------------------------------------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHATS_DIRECTORY",
        type=str,
        default="data/chats",
        description="Filesystem path where chat session files are stored.",
        component="chat",
    )
)

# --- ai ---------------------------------------------------------------------
#
# Kept here rather than moved to env_registry_ai.py (#14856): these three
# carry hardcoded-value baseline entries keyed to this file's path in
# pipeline-scripts/hardcoded_values_baseline.txt, and check_baseline_no_growth.sh
# has no route to repoint an entry onto a file that did not exist at the base
# ref. See env_registry_ai.py's module docstring and #13131.

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CLASSIFICATION_MODEL",
        type=str,
        default="gemma2:2b",
        description="Ollama model name used for intent classification.",
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_OLLAMA_BASE_URL",
        type=str,
        default=None,
        description="Base URL of the local Ollama API (e.g. http://localhost:11434).",
        component="ai",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ORCHESTRATOR_MODEL",
        type=str,
        default="llama3.2:1b",
        description="Ollama model name used for the main orchestrator/routing loop.",
        component="ai",
    )
)

# --- system -----------------------------------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_DEPLOYMENT_MODE",
        type=str,
        default="distributed",
        description="Deployment topology: 'distributed' or 'standalone'.",
        component="system",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ENV",
        type=str,
        default="production",
        description="Short environment label used in logs and traces (e.g. 'development', 'production').",
        component="system",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ENVIRONMENT",
        type=str,
        default="development",
        description=(
            "Full environment name for OTel deployment.environment attribute. " "Prefer AUTOBOT_ENV for new code."
        ),
        component="system",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_GIT_BRANCH",
        type=str,
        default="Dev_new_gui",
        description="Git branch that the running instance was built from.",
        component="system",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_REQUIRE_CLASSIFICATION",
        type=bool,
        default=False,
        description=(
            "Fail orchestrator construction when request classification is unavailable. "
            "Default (off) degrades gracefully: every request is defaulted to COMPLEX and "
            "the reason is reported in the orchestration status. Deployments that depend on "
            "classification set this so the failure is loud instead of silent (#13807)."
        ),
        component="orchestrator",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SHOW_DEPRECATION_WARNINGS",
        type=bool,
        default=False,
        description="Emit Python DeprecationWarnings for deprecated AutoBot APIs when truthy.",
        component="system",
    )
)

# --- auth -------------------------------------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_INTERNAL_API_KEY",
        type=str,
        default="",
        description="Shared secret used to authenticate internal service-to-service calls.",
        component="auth",
    )
)

# --- kb (knowledge base) ----------------------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_KB_TIMEOUT",
        type=int,
        default=30,
        description="Timeout in seconds for knowledge-base HTTP requests.",
        component="kb",
        range=(1, 300),
    )
)

# --- logging ----------------------------------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LOGS_BACKUP_DIR",
        type=str,
        default="backup",
        description="Directory where rotated log archives are written.",
        component="logging",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LOGS_DIR",
        type=str,
        default="logs",
        description="Primary directory for application log files.",
        component="logging",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LOG_VIEWER_URL",
        type=str,
        default="http://localhost:5341",
        description="Base URL of the Seq (or compatible) structured-log viewer.",
        component="logging",
    )
)

# --- otel -------------------------------------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_OTEL_ENABLED",
        type=bool,
        default=False,
        description="Enable OpenTelemetry tracing when truthy.",
        component="otel",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_OTEL_ENDPOINT",
        type=str,
        default=None,
        description="OTLP collector endpoint URL (e.g. http://otel-collector:4317).",
        component="otel",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_OTEL_PROTOCOL",
        type=str,
        default="grpc",
        description="OTLP export protocol: 'grpc' or 'http/protobuf'.",
        component="otel",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_OTEL_SAMPLE_RATE",
        type=float,
        default=0.1,
        description="Fraction of traces to sample (0.0–1.0).",
        component="otel",
        range=(0.0, 1.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_OTEL_SERVICE_VERSION",
        type=str,
        default="1.5.0",
        description="Service version tag attached to all OTel spans.",
        component="otel",
    )
)

# --- postgres ---------------------------------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_POSTGRES_DB",
        type=str,
        default="autobot_users",
        description="PostgreSQL database name.",
        component="postgres",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_POSTGRES_HOST",
        type=str,
        default="127.0.0.1",
        description="PostgreSQL server hostname or IP.",
        component="postgres",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_POSTGRES_PASSWORD",
        type=str,
        default="",
        description="PostgreSQL user password.",
        component="postgres",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_POSTGRES_PORT",
        type=str,
        default="5432",
        description="PostgreSQL server port.",
        component="postgres",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_POSTGRES_USER",
        type=str,
        default="slm_app",
        description="PostgreSQL login role.",
        component="postgres",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_USERS_DATABASE_URL",
        type=str,
        default=None,
        description=(
            "Full SQLAlchemy connection URL for the users database. "
            "Overrides AUTOBOT_POSTGRES_* individual vars when set."
        ),
        component="postgres",
    )
)

# --- monitoring -------------------------------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PROMETHEUS_URL",
        type=str,
        default="http://10.0.0.4:9090",
        description="Base URL of the Prometheus metrics server.",
        component="monitoring",
    )
)

# --- redis ------------------------------------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_REDIS_DB_ANALYTICS",
        type=int,
        default=11,
        description="Redis logical database number for analytics data.",
        component="redis",
        range=(0, 15),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_REDIS_DB_KNOWLEDGE",
        type=int,
        default=1,
        description="Redis logical database number for knowledge-base vectors.",
        component="redis",
        range=(0, 15),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_REDIS_DB_MAIN",
        type=int,
        default=0,
        description="Redis logical database number for primary application data.",
        component="redis",
        range=(0, 15),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_REDIS_HOST",
        type=str,
        default="localhost",
        description="Redis server hostname or IP address.",
        component="redis",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_REDIS_PASSWORD",
        type=str,
        default=None,
        description="Redis AUTH password (omit or leave blank for unauthenticated servers).",
        component="redis",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_REDIS_PORT",
        type=int,
        default=6379,
        description="Redis server TCP port (plain connection).",
        component="redis",
        range=(1, 65535),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_REDIS_TLS_ENABLED",
        type=bool,
        default=False,
        description="Enable TLS for Redis connections when truthy.",
        component="redis",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_REDIS_TLS_PORT",
        type=int,
        default=6380,
        description="Redis server TCP port for TLS connections.",
        component="redis",
        range=(1, 65535),
    )
)

# --- tls --------------------------------------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TLS_CA_PATH",
        type=str,
        default=None,
        description="Path to the CA certificate file for TLS verification.",
        component="tls",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TLS_CERT_DIR",
        type=str,
        default="/etc/autobot/certs",
        description="Directory containing TLS certificate and key files.",
        component="tls",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TLS_CERT_PATH",
        type=str,
        default=None,
        description="Path to the TLS client/server certificate file.",
        component="tls",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TLS_KEY_PATH",
        type=str,
        default=None,
        description="Path to the TLS private key file.",
        component="tls",
    )
)

# --- network ----------------------------------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TRUSTED_PROXIES",
        type=str,
        default="",
        description=(
            "Comma-separated list of trusted reverse-proxy IP addresses or CIDR ranges "
            "for X-Forwarded-For header trust."
        ),
        component="network",
    )
)

# --- voice / speech-to-text -------------------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_STT_SILENCE_RMS_THRESHOLD",
        type=float,
        default=0.005,
        description=(
            "Audio RMS below which the waveform is treated as silence, so any STT "
            "transcript over it is a hallucination rather than a user turn (#13104)."
        ),
        component="voice",
        range=(0.0, 1.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_STT_NO_SPEECH_PROB_THRESHOLD",
        type=float,
        default=0.8,
        description=(
            "Decoder no-speech probability at or above which an STT transcript is "
            "discarded as a silence hallucination (#13104)."
        ),
        component="voice",
        range=(0.0, 1.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MULTIMODAL_VOICE_CONFIDENCE_THRESHOLD",
        type=float,
        default=0.7,
        description=(
            "Fallback confidence threshold for VoiceProcessor when the multimodal.voice "
            "config section omits it (#13207)."
        ),
        component="voice",
        range=(0.0, 1.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MULTIMODAL_VOICE_PROCESSING_TIMEOUT",
        type=int,
        default=30,
        description=(
            "Fallback processing timeout in seconds for VoiceProcessor when the "
            "multimodal.voice config section omits it (#13207)."
        ),
        component="voice",
    )
)


# --- provider OAuth / device-code flow (#14223) ------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PROVIDER_OAUTH_STATE_TTL_SECONDS",
        type=int,
        default=600,
        description=(
            "Lifetime of a pending OAuth `state` value. A provider authorisation "
            "that is not completed within this window is rejected as expired "
            "(api/provider_auth.py)."
        ),
        component="auth",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_DEVICE_POLL_MIN_INTERVAL_SECONDS",
        type=int,
        default=5,
        description=(
            "Floor on how often the device-code flow polls the provider for "
            "completion, regardless of the interval the provider advertises."
        ),
        component="auth",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_DEVICE_POLL_BACKOFF_SECONDS",
        type=int,
        default=5,
        description=("Extra delay added to the device-code poll interval after the " "provider answers `slow_down`."),
        component="auth",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_DEVICE_POLL_MAX_ATTEMPTS",
        type=int,
        default=360,
        description=(
            "Maximum device-code poll attempts before the flow is abandoned. "
            "Bounds the poll loop independently of the time window below."
        ),
        component="auth",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_DEVICE_POLL_WINDOW_SECONDS",
        type=int,
        default=1800,
        description=(
            "Wall-clock ceiling on a device-code flow. Reached first when the "
            "provider advertises a long interval, whereas the attempt cap above "
            "binds first when it advertises a short one."
        ),
        component="auth",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_OAUTH_REFRESH_LOCK_TTL_MS",
        type=int,
        default=90_000,
        description=(
            "Milliseconds a connector holds the single-flight lock while "
            "refreshing an OAuth token. Derived as three times the token request "
            "timeout — 90000 with the default 30s timeout — so it tracks that "
            "timeout instead of drifting from it "
            "(knowledge/connectors/credential_store.py). This variable can only "
            "RAISE it: a smaller value is floored back to the derived TTL and a "
            "warning is logged, because the lease is held across the store write "
            "as well as the HTTP call, and one that expires mid-refresh lets two "
            "workers rotate the same token (#14238)."
        ),
        component="auth",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_OAUTH_REFRESH_WAIT_S",
        type=float,
        default=0.0,
        description=(
            "Seconds a caller waits for another worker's in-flight token refresh "
            "before refreshing itself. The effective value is floored at the lock "
            "TTL plus five seconds — 95 with the defaults — because a caller that "
            "gives up before the lease expires abandons a refresh still in "
            "progress. Setting it below that floor therefore has no effect."
        ),
        component="auth",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_OAUTH_REFRESH_POLL_S",
        type=float,
        default=0.2,
        description=(
            "Polling interval while waiting on another worker's token refresh. "
            "Floored at 0.05s, since zero would busy-loop the executor."
        ),
        component="auth",
    )
)


# --- gateway connectors (#14223) ---------------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_IMESSAGE_ENABLED",
        type=bool,
        default=False,
        description=(
            "Opt in to the iMessage gateway adapter. Off by default: it is "
            "macOS-only and needs Full Disk Access to the Messages database."
        ),
        component="gateway",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SIGNAL_ENABLED",
        type=bool,
        default=False,
        description=(
            "Opt in to the Signal gateway adapter. Off by default: it needs a "
            "running signal-cli daemon and a registered number."
        ),
        component="gateway",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_MATRIX_E2EE",
        type=bool,
        default=False,
        description=(
            "Opt in to end-to-end encryption for the Matrix adapter. Off by "
            "default because E2EE needs the optional olm dependency and a "
            "persisted device store."
        ),
        component="gateway",
    )
)


# --- execution sandbox and snapshots (#14223) --------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_DOCKER_USE_POOL",
        type=bool,
        default=False,
        description=(
            "Reuse a pool of warm containers for tool execution instead of "
            "starting one per call. Off by default — the pool trades isolation "
            "between calls for start-up latency."
        ),
        component="execution",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_DOCKER_POOL_SIZE",
        type=int,
        default=3,
        description=(
            "Number of warm containers kept when AUTOBOT_DOCKER_USE_POOL is on. "
            "Ignored entirely when pooling is off."
        ),
        component="execution",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SNAPSHOT_STORAGE_PATH",
        type=str,
        default="",
        description=(
            "Directory holding execution snapshots. Empty means 'derive it' — "
            "the default is `<project root>/snapshots`, so it follows the "
            "install location rather than being pinned to one path."
        ),
        component="execution",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SNAPSHOT_TTL_DAYS",
        type=int,
        default=7,
        description=(
            "Age at which the cleanup task removes an execution snapshot. "
            "Snapshots are a debugging aid, so the default is deliberately short."
        ),
        component="execution",
    )
)


# --- worker and analysis pools (#14223) --------------------------------------

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


# --- timeouts and backoffs (#14223) ------------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PROVISION_STALE_SECONDS",
        type=int,
        default=1800,
        description=(
            "How long a provision run may report no progress before the setup "
            "wizard treats it as abandoned and lets a new run supersede it "
            "(#14856). Keyed on observed progress, not on time since start, so "
            "a slow-but-live run is never superseded; the floor keeps a value "
            "too small to distinguish the two from wedging the wizard the other way."
        ),
        component="provisioning",
        range=(60, 86400),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CONFIG_REGISTRY_REDIS_RETRY_SECONDS",
        type=float,
        default=30.0,
        description=(
            "Interval between config-registry attempts to reconnect to Redis "
            "after a failure, so a Redis outage does not become a reconnect storm."
        ),
        component="redis",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_RETRIEVAL_REDIS_TIMEOUT",
        type=float,
        default=1.5,
        description=(
            "Seconds the retrieval learner waits for its Redis lock before "
            "proceeding without it. Short on purpose — retrieval must answer "
            "even when the learner cannot record what it learned."
        ),
        component="redis",
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
        name="AUTOBOT_GRAPH_PATH_TIMEOUT_SECONDS",
        type=float,
        default=10.0,
        description=(
            "Ceiling on a knowledge-graph path search. Path queries are "
            "unbounded in the worst case, so this is what stops one request "
            "occupying a worker indefinitely."
        ),
        component="kb",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SUMMARY_FAILURE_BACKOFF_SECONDS",
        type=int,
        default=300,
        description=(
            "Quiet period after a context-overflow summarisation failure before "
            "another is attempted, so a persistently failing summary does not "
            "retry on every turn."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_COMPACTION_USER_MESSAGE_CAP",
        type=int,
        default=40,
        description=(
            "How many of the most recent user messages cross a context compaction "
            "verbatim instead of being summarised. Bounded so repeated compaction "
            "cannot grow the preserved set without limit."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_COMPACTION_TOOL_RESULT_CLIP_CHARS",
        type=int,
        default=400,
        description=(
            "Maximum characters of a tool result in the summarised region before "
            "it is clipped for the summariser; a file read many turns ago is "
            "cheaper to re-read than to carry."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_COMPACTION_BOUNDARY_WINDOW",
        type=int,
        default=10,
        description=(
            "How far back the compaction boundary looks for a user turn before "
            "settling for any turn start, so the cut cannot be dragged far from "
            "the midpoint."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_COMPACTION_STATE_COMMAND_CAP",
        type=int,
        default=10,
        description="Most recent shell commands named in a compaction's extracted state block.",
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_GATEWAY_REQUIRE_OUTBOUND_APPROVAL",
        type=bool,
        default=False,
        description=(
            "Require approval before the Gateway hands an agent-authored message "
            "to a channel adapter. Off means audit-only: every governed send is "
            "recorded, none is blocked. On fails closed — no registered approver, "
            "a denial, or an approver error all deny the send."
        ),
        component="gateway",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_REMOTE_APPROVAL_FLAG_TTL_SECONDS",
        type=int,
        default=604800,
        description=(
            "How long a session stays flagged for remote approval routing without being "
            "refreshed. Expiry returns the session to asking inline; it never widens autonomy."
        ),
        component="approvals",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_REMOTE_APPROVAL_TTL_SECONDS",
        type=int,
        default=86400,
        description=(
            "How long a remotely delivered approval stays correlatable with its reply. "
            "After this the reply can no longer be tied to a request and resolves nothing."
        ),
        component="approvals",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LLC_H2A_BRIEF_CACHE_TTL",
        type=int,
        default=86400,
        description=(
            "Cache lifetime in seconds for a human-to-agent handoff brief " "(llc/services/handoff.py). One day."
        ),
        component="orchestrator",
    )
)


# --- storage paths and toolsets (#14223) -------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TRANSCRIBER_DB_PATH",
        type=str,
        default="data/transcriber.db",
        description=(
            "SQLite database backing the transcriber. Relative to the working "
            "directory unless given as an absolute path."
        ),
        component="voice",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_VOICE_TOOLSETS",
        type=str,
        default="voice_safe",
        description=(
            "Comma-separated toolset bundles a voice session may call. Defaults "
            "to the restricted `voice_safe` bundle — voice input is harder to "
            "confirm than typed input, so the surface is narrowed by default."
        ),
        component="voice",
    )
)


# --- monitoring endpoints (#14223) -------------------------------------------

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_GRAFANA_PORT",
        type=str,
        default="3000",
        description=(
            "TCP port of the Grafana instance. Also declared in ssot_config.py; "
            "3000 is Grafana's own default and is NOT the browser service, which "
            "is 9001 (#4052, #14198)."
        ),
        component="monitoring",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PROMETHEUS_PORT",
        type=str,
        default="9090",
        description=("TCP port of the Prometheus instance. Also declared in ssot_config.py."),
        component="monitoring",
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

# --- backfilled from the env_utils helper form (#14265) -----------------------
# These were read via env_int/env_flag/env_str/env_float and were therefore
# invisible to the registry checker until it learned that form. Defaults and
# types are taken from each call site, not guessed.

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ALLOW_CONFIG_EDITS",
        type=bool,
        default=False,
        description=(
            "Permit writes to the repository's tracked config files. Off by default: the "
            "codebase is the source of truth and an edit made here is invisible to "
            "deployment (#11220)."
        ),
        component="system",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_APPROVAL_PENDING_SESSION_TTL_SECONDS",
        type=int,
        default=604800,
        description=(
            "Seconds a session holding a pending approval survives in Redis. Deliberately "
            "long — what it waits for is a person, and expiring sooner discards the "
            "approval rather than the wait (#13478)."
        ),
        component="execution",
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
        name="AUTOBOT_CODEEXEC_APPROVAL_POLL_SECONDS",
        type=int,
        default=2,
        description=("Seconds between polls while waiting for a code-execution approval decision."),
        component="execution",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CODEEXEC_APPROVAL_WAIT_SECONDS",
        type=int,
        default=1800,
        description=(
            "Seconds a code-execution request waits for approval before expiring. Expiry is "
            "a decision the caller can act on, not a side effect of how long a coroutine "
            "lives (GH#11568)."
        ),
        component="execution",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CODEEXEC_AUTOAPPROVE_READONLY",
        type=bool,
        default=True,
        description=(
            "Auto-approve code-execution calls limited to the read-only tool set. The "
            "eligible set is fixed in code, not configurable here (GH#11568, GH#11662)."
        ),
        component="execution",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CODEEXEC_ENABLED",
        type=bool,
        default=False,
        description=("Master switch for the compose/code-execution tool. Ships off (GH#11568)."),
        component="execution",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CODEEXEC_MAX_SCRIPT_RETRIES",
        type=int,
        default=1,
        description=("How many times a failed generated script may be retried within one " "code-execution call."),
        component="execution",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CODEEXEC_MAX_TOOL_CALLS",
        type=int,
        default=50,
        description=(
            "Ceiling on tool calls a single code-execution script may make, bounding a "
            "runaway loop inside the sandbox."
        ),
        component="execution",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CODEEXEC_TIMEOUT_SECONDS",
        type=int,
        default=120,
        description=("Seconds a compose-tool sandbox execution may run (GH#11568)."),
        component="execution",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_INJECTION_HARDBLOCK_ENABLED",
        type=bool,
        default=False,
        description=(
            "Hard-block prompt injection rather than only flagging it. When on and "
            "confidence clears the threshold, the request is refused instead of annotated."
        ),
        component="auth",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_INJECTION_HARDBLOCK_THRESHOLD",
        type=float,
        default=0.75,
        description=(
            "Confidence in [0.0, 1.0] at or above which a detected injection is "
            "hard-blocked. 0.75 maps to HIGH; 1.0 would block only CRITICAL."
        ),
        component="auth",
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
        name="AUTOBOT_STT_PEAK_WINDOW_MS",
        type=int,
        default=100,
        description=(
            "Window in milliseconds over which speech energy is measured. Measuring across "
            "the whole buffer averages a short reply into silence (#13104)."
        ),
        component="voice",
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
        name="AUTOBOT_LIVE_PROBE_TIMEOUT_SECONDS",
        type=float,
        default=1.0,
        description=(
            "Seconds a test's live-service precondition probe waits for a TCP connect "
            "before reporting the service as absent and skipping "
            "(autobot_shared/live_service_probe.py, #14930). Short by default: a "
            "refused loopback connect returns immediately, and this runs once per "
            "endpoint per process. Raise it when probing a fleet host across a link "
            "slow enough that a live service could be mistaken for a missing one."
        ),
        component="testing",
        range=(0.1, 60.0),
    )
)
