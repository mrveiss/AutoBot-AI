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
        default=0,
        description=(
            "Milliseconds a connector holds the single-flight lock while "
            "refreshing an OAuth token. Zero means 'derive it' — the default is "
            "computed as three times the token request timeout, so it tracks that "
            "timeout instead of drifting from it (knowledge/connectors/credential_store.py)."
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
            "before refreshing itself. Zero disables waiting, so every caller "
            "refreshes independently."
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
            "Only consulted when AUTOBOT_OAUTH_REFRESH_WAIT_S is non-zero."
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
        name="AUTOBOT_LLM_MAX_RETRY_AFTER_SECONDS",
        type=float,
        default=30.0,
        description=(
            "Cap applied to a provider's `Retry-After`. Without it a provider "
            "advertising a long back-off would stall a request for that whole "
            "period (services/llm_service.py)."
        ),
        component="ai",
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
        name="AUTOBOT_OPENVINO_CACHE_DIR",
        type=str,
        default="data/openvino_cache",
        description=(
            "Directory for compiled OpenVINO model artefacts. Relative to the "
            "working directory unless given as an absolute path."
        ),
        component="ai",
    )
)

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
