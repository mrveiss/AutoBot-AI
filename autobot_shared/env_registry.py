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
