# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SLM Server Configuration

Centralized configuration for the standalone SLM backend.
PostgreSQL replaces SQLite for all database operations (Issue #786).
"""

import logging
import os
import secrets
import socket
import stat
from functools import cached_property
from pathlib import Path
from typing import Optional

from pydantic import ConfigDict, field_validator
from pydantic_settings import BaseSettings

from autobot_shared import postgres_identity as pg
from autobot_shared.fleet_constants import DEFAULT_HEARTBEAT_INTERVAL
from autobot_shared.secret_redaction import RedactedReprMixin
from autobot_shared.service_registry_core import DeploymentMode, resolve_deployment_mode
from user_management.config import get_autobot_db_config, get_slm_db_config

logger = logging.getLogger(__name__)

#: The boolean spellings pydantic accepts for a ``bool`` setting.
_BOOL_WORDS = frozenset({"1", "0", "true", "false", "yes", "no", "on", "off", "t", "f", "y", "n"})

# Filename for the auto-generated persistent keys file inside data_dir.
# Issue #1726 — keeps keys stable across restarts when env vars are absent.
_SLM_KEYS_FILE = ".slm_keys"

# Candidate env files, most general first. /etc/autobot/db-credentials.env is
# written by Ansible as 0600 autobot:autobot, so only the service user and root
# can read it (#13089).
_ENV_FILE_CANDIDATES = (".env", "/etc/autobot/db-credentials.env")


def _readable_env_files(candidates: tuple[str, ...] = _ENV_FILE_CANDIDATES) -> tuple[str, ...]:
    """Return only the env files this process can actually read.

    python-dotenv skips a *missing* env_file silently but raises
    ``PermissionError`` on one that exists and is unreadable. Because
    ``Settings()`` is instantiated at import time (below), that turns any
    unprivileged import of this module into a hard crash — which is what made
    ``scripts/dump_openapi.py`` and ``audit_api_wiring.py --dump-slm-openapi``
    unrunnable except as root (#13089).

    CI never saw it: the file does not exist on runners, so dotenv skipped it.
    Filtering to readable paths makes local behaviour match CI without widening
    access to the credential file.

    A file that exists but cannot be read is logged at WARNING, so a genuine
    production permission regression stays loud instead of silently falling
    back to defaults.
    """
    usable: list[str] = []
    for path in candidates:
        if os.access(path, os.R_OK):
            usable.append(path)
        elif os.path.exists(path):
            logger.warning(
                "Env file %s exists but is not readable by uid=%s — skipping it. "
                "Settings that file would supply will fall back to environment "
                "variables or defaults.",
                path,
                os.geteuid(),
            )
    return tuple(usable)


def _get_local_ip() -> str:
    """Return the machine's primary outbound IP address.

    Opens a UDP socket toward a public address (no packet is actually sent)
    to let the OS select the correct source interface, then reads the bound
    address.  Falls back to ``127.0.0.1`` if the probe fails (e.g. no
    network at import time), which is safe because callers that need a
    routable IP should always set ``SLM_EXTERNAL_URL`` via the env file.

    Issue #2758 — prevents external_url from defaulting to a hardcoded IP.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _get_cors_origins() -> list:
    """Build CORS origins from env var or infrastructure SSOT.

    Override with SLM_CORS_ORIGINS (comma-separated).
    Otherwise, generates origins from all known infrastructure VMs via
    NetworkConstants (backed by ConfigRegistry / redis-databases.yaml SSOT).

    Issue #2862 — removed hardcoded fallback IPs; all values now flow through
    NetworkConstants so ConfigRegistry overrides are respected.
    """
    env_origins = os.getenv("SLM_CORS_ORIGINS", "")
    if env_origins:
        return [o.strip() for o in env_origins.split(",") if o.strip()]

    try:
        from autobot_shared.network_constants import NetworkConstants

        origins: set[str] = set()
        for host in NetworkConstants.get_host_configs():
            ip = host["ip"]
            port = host["port"]
            origins.add(f"http://{ip}:{port}")
            origins.add(f"https://{ip}")
        # Ensure the SLM VM and frontend VM are always included as HTTPS origins
        # (they may only appear with their service port in get_host_configs()).
        origins.add(f"https://{NetworkConstants.SLM_VM_IP}")
        origins.add(f"https://{NetworkConstants.FRONTEND_VM_IP}")
        return sorted(origins)
    except ImportError:
        logger.warning("autobot_shared not available; falling back to localhost CORS only")
        return ["https://127.0.0.1", "http://127.0.0.1"]


def _get_trusted_proxies() -> list:
    """Build the trusted reverse-proxy list from env var or SSOT.

    Override with SLM_TRUSTED_PROXIES (comma-separated IPs).
    Otherwise, includes localhost addresses and the SLM/frontend VM IPs
    read from NetworkConstants (backed by ConfigRegistry SSOT).

    Issue #2862 — replaced hardcoded IP fallback with SSOT-derived values.
    """
    env_proxies = os.getenv("SLM_TRUSTED_PROXIES", "")
    if env_proxies:
        return [ip.strip() for ip in env_proxies.split(",") if ip.strip()]

    proxies = ["127.0.0.1", "::1"]
    try:
        from autobot_shared.network_constants import NetworkConstants

        proxies.append(NetworkConstants.SLM_VM_IP)
        proxies.append(NetworkConstants.FRONTEND_VM_IP)
    except ImportError:
        logger.warning("autobot_shared not available; trusted_proxies limited to localhost")
    return proxies


def _get_ssot_pool_defaults() -> tuple:
    """Load database pool defaults from SSOT config (#2860).

    Returns:
        Tuple of (pool_size, max_overflow, pool_recycle) from SSOT config.
    """
    try:
        from autobot_shared.ssot_config import get_config

        pool_cfg = get_config().database_pool
        return (pool_cfg.pool_size, pool_cfg.max_overflow, pool_cfg.pool_recycle)
    except Exception:
        return (10, 10, 3600)


def _get_ssot_backend_url() -> str:
    """Derive the autobot-backend URL from SSOT config (vm.main / port.backend).

    Falls back to localhost:8001 if autobot_shared is unavailable (#10573).
    """
    try:
        from autobot_shared.ssot_config import get_config

        return get_config().backend_url
    except Exception:
        return "http://127.0.0.1:8001"  # canonical: ignore py-hardcoded-url - bootstrap: ssot_config unavailable


#: #19322: the backend's old name for the manager's node id, now a deprecated alias of
#: AUTOBOT_SLM_NODE_ID. The name stays live as the SLM agent's OWN per-host id
#: (slm-agent.service sets it on every node), which is why the manager's id left it.
_LEGACY_SLM_NODE_ID_VAR = "SLM_NODE_ID"


def _resolve_slm_node_id() -> str:
    """The SLM manager's node id: ``MiscConfig.slm_node_id`` (AUTOBOT_SLM_NODE_ID), the one home.

    A deployment that set only the legacy ``SLM_NODE_ID`` keeps the id it registered under,
    with a deprecation warning, so no existing manager row is orphaned (#19322). A blank value
    of either name counts as unset, as ``ssot-config.sh`` treats it: canonical, then legacy,
    then the field default -- never an empty id.
    """
    from autobot_shared.ssot_config import get_config

    misc = get_config().misc
    canonical = misc.slm_node_id.strip()
    default = type(misc).model_fields["slm_node_id"].default
    legacy = os.environ.get(_LEGACY_SLM_NODE_ID_VAR, "").strip()
    if not legacy or legacy == canonical:
        return canonical or default
    # Set explicitly (environment or .env), even to the default value: the canonical name wins.
    if canonical and "slm_node_id" in misc.model_fields_set:
        logger.error("SLM_NODE_ID=%s ignored: AUTOBOT_SLM_NODE_ID=%s is set and wins", legacy, canonical)
        return canonical
    logger.warning("SLM_NODE_ID is deprecated for the manager's node id; set AUTOBOT_SLM_NODE_ID=%s", legacy)
    return legacy


# Load SSOT defaults at module level so Settings class can reference them.
_SSOT_POOL_SIZE, _SSOT_MAX_OVERFLOW, _SSOT_POOL_RECYCLE = _get_ssot_pool_defaults()
_SSOT_BACKEND_URL = _get_ssot_backend_url()


class Settings(RedactedReprMixin, BaseSettings):
    """SLM Server Settings."""

    # Paths - relative to slm-server directory (where config.py lives)
    base_dir: Path = Path(__file__).parent
    data_dir: Path = Path(os.getenv("SLM_DATA_DIR", str(Path(__file__).parent / "data")))
    config_dir: Path = Path(os.getenv("SLM_CONFIG_DIR", str(Path(__file__).parent / "config")))
    ansible_dir: Path = Path(__file__).parent / "ansible"
    # #18892: where the SLM SPA is served (vite `base: '/slm/'`). Browser redirects
    # the backend issues -- the SSO callback -- must carry it: a bare `/sso-callback`
    # is served by the USER frontend on the shared vhost. Read from SLM_FRONTEND_BASE_PATH
    # (env_prefix) and normalised below: one leading slash, no trailing slash.
    frontend_base_path: str = "/slm"

    @field_validator("frontend_base_path")
    @classmethod
    def _normalise_frontend_base_path(cls, raw: str) -> str:
        """`slm`, `/slm/` and `/slm` all mean `/slm`; `/` or blank is the root (#18892).

        Without the leading slash the SSO redirect would be relative and resolve under `/api/auth/sso/`.
        """
        trimmed = raw.strip().strip("/")
        return f"/{trimmed}" if trimmed else ""

    # #13307: was `Path.home() / "slm-backups"`, which put every backup in the
    # service account's home directory — on the root filesystem, in a place
    # nobody thinks to look, chosen by a fallback rather than a decision. It also
    # contradicted services/backup.py, which named /var/lib/slm/backups as its
    # own (dead) fallback. One answer now, and it is the FHS location for service
    # state. The ansible backend role creates it with the right ownership.
    backup_dir: Path = Path(os.getenv("SLM_BACKUP_DIR", "/var/lib/slm/backups"))

    # #13307: how many backups to keep per (node, service_type), and how long.
    # Without a delete route nothing could reclaim space, so storage only grew —
    # on the root filesystem. 0 disables that dimension of the policy.
    backup_retention_count: int = int(os.getenv("SLM_BACKUP_RETENTION_COUNT", "10"))
    backup_retention_days: int = int(os.getenv("SLM_BACKUP_RETENTION_DAYS", "30"))

    # ==========================================================================
    # PostgreSQL Database Configuration (Issue #786)
    # ==========================================================================
    # Main SLM operational database (nodes, deployments, backups, etc.)
    database_url: str = os.getenv(
        "SLM_DATABASE_URL",
        f"postgresql+asyncpg://{pg.SLM_DB_ROLE}@{pg.SLM_DB_HOST}:{pg.DB_PORT}/{pg.SLM_DB_NAME}",
    )

    # SLM admin users database (fleet administrators)
    # #18094: the one resolver (SLM_USERS_DATABASE_URL, else the SLM_POSTGRES_* parts)
    # lives in user_management.config; a literal DSN here was a second default for it.
    slm_users_database_url: str = get_slm_db_config().url

    # AutoBot application users database (colocated on SLM server)
    autobot_users_database_url: str = get_autobot_db_config().url

    # Database connection pool settings (#2860) — SSOT-coordinated defaults.
    # SLM_DB_POOL_* env vars still override for per-service tuning.
    db_pool_size: int = int(os.getenv("SLM_DB_POOL_SIZE", str(_SSOT_POOL_SIZE)))
    db_pool_max_overflow: int = int(os.getenv("SLM_DB_POOL_MAX_OVERFLOW", str(_SSOT_MAX_OVERFLOW)))
    db_pool_recycle: int = int(os.getenv("SLM_DB_POOL_RECYCLE", str(_SSOT_POOL_RECYCLE)))

    # Server
    host: str = "0.0.0.0"  # nosec B104  # bound behind nginx reverse proxy
    port: int = 8000
    debug: bool = False

    # SLM self-identity (#9956, #10110): the SLM manager's own DB node_id -- the one
    # well-known, stable identity in the registry-driven model (every other node
    # self-registers with a uuid4()[:8] node_id). A property, not a field: as a
    # field, env_prefix also bound it to a third name, SLM_SLM_NODE_ID (#19322).
    @cached_property
    def slm_node_id(self) -> str:
        return _resolve_slm_node_id()

    # Authentication
    secret_key: str = os.getenv("SLM_SECRET_KEY", "")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Authority (autobot-backend) RS256 verification — Pattern B (#10197).
    # The SLM fetches the public key from the authority's JWKS endpoint and
    # verifies RS256 tokens locally; the signing private key never leaves the
    # authority.  Override these in /etc/autobot/slm-secrets.env for
    # non-co-located deployments.
    authority_base_url: str = os.getenv("SLM_AUTHORITY_BASE_URL", _SSOT_BACKEND_URL)
    authority_jwks_path: str = os.getenv("SLM_AUTHORITY_JWKS_PATH", "/.well-known/jwks.json")
    # How long to trust a cached JWKS before re-fetching (seconds).
    jwks_cache_ttl_seconds: int = int(os.getenv("SLM_JWKS_CACHE_TTL", "3600"))
    # HTTP connect+read timeout for JWKS endpoint calls (seconds).
    jwks_fetch_timeout_seconds: float = float(os.getenv("SLM_JWKS_FETCH_TIMEOUT", "10"))

    # API-key pepper (#2160, #16299, #19120). The pepper lives in the SLM secrets
    # store (services/api_key_pepper.py); this env value is only a one-time import
    # source for installs that already have it. No in-repo default.
    hmac_api_key_secret: str = os.getenv("SLM_HMAC_API_KEY_SECRET", "")

    # Encryption for sensitive data (credentials, etc.)
    encryption_key: str = os.getenv("SLM_ENCRYPTION_KEY", "")

    # Redis (GH #6511: permission cache + future session storage)
    # Set SLM_REDIS_URL to e.g. "redis://127.0.0.1:6379/0".
    # When absent the RBAC middleware falls back to an in-process dict cache.
    redis_url: Optional[str] = os.getenv("SLM_REDIS_URL")

    # #14362: bound the Prometheus scrape handler's DB work.
    #
    # `metrics_cache_ttl_seconds` bounds how often the handler's two queries
    # can run at all: the rendered text is cached for this many seconds.
    # Deliberately shorter than a real scrape interval — the ansible
    # monitoring role default is 15s
    # (ansible/roles/monitoring/defaults/main.yml:prometheus_scrape_interval)
    # — so a genuine scrape always observes fresh data; only overlapping
    # calls inside the same interval (duplicate scrape configs, retries,
    # manual checks) reuse the cached result instead of re-querying.
    #
    # The trace-duration histogram itself needs no row cap: it is a SQL-side
    # aggregate (COUNT/SUM/bucketed SUM(CASE...)) over the full cutoff-
    # filtered set, computed in `_fetch_trace_duration_histograms`
    # (autobot-slm-backend/api/performance.py) — a `LIMIT` there would make
    # `_count`/`_sum` describe a sample while presenting themselves as the
    # window total (review finding on #14362's original PR).
    metrics_cache_ttl_seconds: float = float(os.getenv("SLM_METRICS_CACHE_TTL_SECONDS", "5"))

    # #14362 (review): `_fetch_top_slow_traces` (autobot-slm-backend/api/
    # performance.py) is a genuine bounded top-N — the slowest traces shown
    # on the authenticated /performance/overview panel — where a cap is the
    # right semantics, unlike the histogram above. Was a bare `10` at the
    # call site; default kept at 10 to preserve existing behaviour while
    # making it configurable instead of hardcoded.
    top_slow_traces_limit: int = int(os.getenv("SLM_TOP_SLOW_TRACES_LIMIT", "10"))

    def _keys_file_path(self) -> Path:
        """Return the path to the persisted-keys file inside data_dir.

        Issue #1726 — keys are stored in the SLM data directory so they
        survive service restarts and code deployments.
        """
        return self.data_dir / _SLM_KEYS_FILE

    def _load_persisted_keys(self) -> dict:
        """Read key=value pairs from the persisted-keys file.

        Returns an empty dict when the file is absent or unreadable.
        Issue #1726.
        """
        path = self._keys_file_path()
        if not path.exists():
            return {}
        try:
            pairs: dict = {}
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    pairs[k.strip()] = v.strip()
            return pairs
        except OSError as exc:
            logger.error("Failed to read SLM keys file %s: %s", path, exc)
            return {}

    def _write_persisted_keys(self, secret_key: str, encryption_key: str) -> None:
        """Write generated keys to the persisted-keys file (mode 0600).

        Issue #1726.
        """
        path = self._keys_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            "# AutoBot SLM — auto-generated persistent keys\n"
            "# Generated once on first startup when env vars are absent.\n"
            "# Do NOT commit this file. Protect it like a password.\n"
            f"SLM_SECRET_KEY={secret_key}\n"
            f"SLM_ENCRYPTION_KEY={encryption_key}\n"
        )
        path.write_text(content, encoding="utf-8")
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
        logger.info("SLM persistent keys written to %s", path)

    def validate_secrets(self) -> None:
        """Ensure secret_key and encryption_key are set and persistent.

        Priority:
          1. SLM_SECRET_KEY / SLM_ENCRYPTION_KEY environment variables
             (set by Ansible via EnvironmentFile=/etc/autobot/slm-secrets.env)
          2. Persisted keys file at <data_dir>/.slm_keys
             (created automatically on first startup when env vars are absent)

        Issue #1726 — random keys caused token invalidation on every restart.
        """
        both_set = self.secret_key and self.encryption_key
        persisted = {} if both_set else self._load_persisted_keys()
        need_write = False

        if not self.secret_key:
            if persisted.get("SLM_SECRET_KEY"):
                self.secret_key = persisted["SLM_SECRET_KEY"]
                logger.info("SLM_SECRET_KEY loaded from persisted keys file.")
            else:
                self.secret_key = secrets.token_urlsafe(48)
                need_write = True

        if not self.encryption_key:
            if persisted.get("SLM_ENCRYPTION_KEY"):
                self.encryption_key = persisted["SLM_ENCRYPTION_KEY"]
                logger.info("SLM_ENCRYPTION_KEY loaded from persisted keys file.")
            else:
                self.encryption_key = secrets.token_urlsafe(48)
                need_write = True

        if need_write:
            self._write_persisted_keys(self.secret_key, self.encryption_key)
            logger.warning(
                "SLM secret keys were not set via environment variables. "
                "Keys have been auto-generated and saved to %s. "
                "For production deployments use Ansible or set "
                "SLM_SECRET_KEY and SLM_ENCRYPTION_KEY explicitly.",
                self._keys_file_path(),
            )

    # VNC defaults (configurable via env vars)
    vnc_default_port: int = int(os.getenv("SLM_VNC_DEFAULT_PORT", "6080"))
    vnc_default_display: int = int(os.getenv("SLM_VNC_DEFAULT_DISPLAY", "1"))

    # Monitoring
    monitoring_mode: str = "local"  # local or remote
    monitoring_host: str | None = None
    grafana_url: str = os.getenv(
        "SLM_GRAFANA_URL",
        f"http://{os.getenv('AUTOBOT_BACKEND_HOST', '127.0.0.1')}:{os.getenv('AUTOBOT_GRAFANA_PORT', '3000')}",
    )
    prometheus_url: str = os.getenv(
        "SLM_PROMETHEUS_URL",
        f"http://{os.getenv('AUTOBOT_BACKEND_HOST', '127.0.0.1')}:{os.getenv('AUTOBOT_PROMETHEUS_PORT', '9090')}",
    )

    # Health checks
    heartbeat_interval: int = DEFAULT_HEARTBEAT_INTERVAL  # seconds; the agent's default too (#18094)
    health_check_timeout: int = 10  # seconds
    unhealthy_threshold: int = 3  # missed heartbeats

    # Reconciliation
    reconcile_interval: int = 60  # seconds

    # Compose fleet nodes (#9761): surface each compose container as a fleet node. The one
    # default (#19323): unset follows the deployment mode -- on in a container (docker_local,
    # the compose stack, and a dev checkout run inside a container), off on a bare-metal/VM
    # fleet and in a dev checkout on the host.
    # SLM_COMPOSE_NODES=true|false overrides it; compose passes it through, never restates it.
    compose_nodes: bool | None = None

    @field_validator("compose_nodes", mode="before")
    @classmethod
    def _unreadable_compose_nodes_is_unset(cls, raw: object) -> object:
        """A blank or unrecognised value means unset (follow the deployment mode), never an import crash.

        Compose passes the name through, so a blank arrives as ``""``; a typo is warned about once.
        """
        if not isinstance(raw, str):
            return raw
        value = raw.strip().lower()
        if value in _BOOL_WORDS:
            return value
        if value:
            logger.warning("SLM_COMPOSE_NODES value %r is not true/false; following the deployment mode (#19323)", raw)
        return None

    @property
    def compose_nodes_enabled(self) -> bool:
        if self.compose_nodes is not None:
            return self.compose_nodes
        return resolve_deployment_mode() is DeploymentMode.DOCKER_LOCAL

    # CORS settings
    cors_origins: list = _get_cors_origins()

    # Trusted reverse-proxy IPs (Issue #2239, #2862).
    # X-Forwarded-For is only honoured when the direct TCP connection comes
    # from one of these addresses.  Override with SLM_TRUSTED_PROXIES
    # (comma-separated).  The default is derived from NetworkConstants so the
    # ConfigRegistry SSOT is respected; no IPs are hardcoded here.
    trusted_proxies: list = _get_trusted_proxies()

    # External URL - remote nodes use nginx reverse proxy.
    # Issue #2758: derive dynamically from local IP when SLM_EXTERNAL_URL is
    # not set, instead of defaulting to a hardcoded address.
    #
    # #16262: a plain field default here calls _get_local_ip() (a real
    # socket.connect) the moment this class body executes -- at import time,
    # unconditionally, even when SLM_EXTERNAL_URL is set. A plain cached
    # property (not @computed_field) defers that call to the first actual
    # access of `settings.external_url`, and caches it since the machine's
    # outbound IP does not change during the process's lifetime --
    # @computed_field would also run the probe from settings.model_dump()/
    # .json(), reintroducing a network call inside a serialization path.
    @cached_property
    def external_url(self) -> str:
        return os.getenv("SLM_EXTERNAL_URL") or f"https://{_get_local_ip()}"

    # TLS verification for outbound HTTPS calls to internal nodes.
    # Set SLM_VERIFY_SSL=false ONLY in dev/test environments that use
    # self-signed certificates.  Production must leave this at the default
    # True value (#2852).
    verify_ssl: bool = os.getenv("SLM_VERIFY_SSL", "true").lower() not in (
        "false",
        "0",
        "no",
    )

    model_config = ConfigDict(
        env_prefix="SLM_",
        # #13089: readable files only — an unreadable one raises at import time.
        env_file=_readable_env_files(),
        extra="ignore",
    )


settings = Settings()

# Validate secrets on import (generate random if not set)
settings.validate_secrets()

# Ensure directories exist
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.config_dir.mkdir(parents=True, exist_ok=True)
