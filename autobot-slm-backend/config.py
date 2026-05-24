# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
from pathlib import Path

from pydantic import ConfigDict
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# Filename for the auto-generated persistent keys file inside data_dir.
# Issue #1726 — keeps keys stable across restarts when env vars are absent.
_SLM_KEYS_FILE = ".slm_keys"


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


# Load SSOT defaults at module level so Settings class can reference them.
_SSOT_POOL_SIZE, _SSOT_MAX_OVERFLOW, _SSOT_POOL_RECYCLE = _get_ssot_pool_defaults()


class Settings(BaseSettings):
    """SLM Server Settings."""

    # Paths - relative to slm-server directory (where config.py lives)
    base_dir: Path = Path(__file__).parent
    data_dir: Path = Path(__file__).parent / "data"
    config_dir: Path = Path(__file__).parent / "config"
    ansible_dir: Path = Path(__file__).parent / "ansible"
    backup_dir: Path = Path(os.getenv("SLM_BACKUP_DIR", str(Path.home() / "slm-backups")))

    # ==========================================================================
    # PostgreSQL Database Configuration (Issue #786)
    # ==========================================================================
    # Main SLM operational database (nodes, deployments, backups, etc.)
    database_url: str = os.getenv(
        "SLM_DATABASE_URL",
        "postgresql+asyncpg://slm_app@127.0.0.1:5432/slm",
    )

    # SLM admin users database (fleet administrators)
    slm_users_database_url: str = os.getenv(
        "SLM_USERS_DATABASE_URL",
        "postgresql+asyncpg://slm_app@127.0.0.1:5432/slm_users",
    )

    # AutoBot application users database (colocated on SLM server)
    autobot_users_database_url: str = os.getenv(
        "AUTOBOT_USERS_DATABASE_URL",
        "postgresql+asyncpg://slm_app@127.0.0.1:5432/autobot_users",
    )

    # Database connection pool settings (#2860) — SSOT-coordinated defaults.
    # SLM_DB_POOL_* env vars still override for per-service tuning.
    db_pool_size: int = int(os.getenv("SLM_DB_POOL_SIZE", str(_SSOT_POOL_SIZE)))
    db_pool_max_overflow: int = int(os.getenv("SLM_DB_POOL_MAX_OVERFLOW", str(_SSOT_MAX_OVERFLOW)))
    db_pool_recycle: int = int(os.getenv("SLM_DB_POOL_RECYCLE", str(_SSOT_POOL_RECYCLE)))

    # Server
    host: str = "0.0.0.0"  # nosec B104 — bound behind nginx reverse proxy
    port: int = 8000
    debug: bool = False

    # Authentication
    secret_key: str = os.getenv("SLM_SECRET_KEY", "")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # HMAC signing key for API key hashing (#2160).
    # Default preserves backward compatibility with existing hashed keys.
    # Override in production via SLM_HMAC_API_KEY_SECRET env var.
    hmac_api_key_secret: str = os.getenv("SLM_HMAC_API_KEY_SECRET", "autobot-api-key-v1")

    # Encryption for sensitive data (credentials, etc.)
    encryption_key: str = os.getenv("SLM_ENCRYPTION_KEY", "")

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
    grafana_url: str = "http://127.0.0.1:3000"
    prometheus_url: str = "http://127.0.0.1:9090"

    # Health checks
    heartbeat_interval: int = 30  # seconds
    health_check_timeout: int = 10  # seconds
    unhealthy_threshold: int = 3  # missed heartbeats

    # Reconciliation
    reconcile_interval: int = 60  # seconds

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
    external_url: str = os.getenv("SLM_EXTERNAL_URL", f"https://{_get_local_ip()}")

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
        env_file=(".env", "/etc/autobot/db-credentials.env"),
        extra="ignore",
    )


settings = Settings()

# Validate secrets on import (generate random if not set)
settings.validate_secrets()

# Ensure directories exist
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.config_dir.mkdir(parents=True, exist_ok=True)
