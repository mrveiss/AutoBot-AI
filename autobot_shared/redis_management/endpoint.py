# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ONE resolution path for the Redis endpoint: host, port, credentials, TLS (#19232).

Before #19232 two chains answered "which Redis": the canonical client
(``RedisConnectionManager``: config-manager -> env -> ``NetworkConstants`` -> SSOT) and
``ssot_config.redis_url_with_auth`` / ``get_redis_url_for_db`` (the SSOT fields alone).
They agreed only while every tier happened to hold the same value, and a caller of one
could not tell. Both now read :func:`resolve_redis_endpoint`, so a URL built for a
database names the host, port and credentials the canonical client dials.

Host order (first non-empty wins), unchanged from the canonical client:

1. the backend config manager's ``get_redis_config()`` -- an explicitly configured
   deployment must beat a stray env var (#12778);
2. ``REDIS_HOST`` / ``AUTOBOT_REDIS_HOST`` -- the slm-agent's only source (#12778);
3. ``NetworkConstants.REDIS_VM_IP`` -- empty outside autobot-backend (#14299);
4. the SSOT ``vm.redis`` field;
5. loopback.

Port and credentials follow the same tier order. TLS is on when
``AUTOBOT_REDIS_TLS_ENABLED`` says so, else when the SSOT TLS config does.

Stdlib ``logging`` on purpose: ``redis_client`` imports this module at import time.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from threading import Lock
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from autobot_shared.network_constants import NetworkConstants

if TYPE_CHECKING:
    from autobot_shared.ssot_config import AutoBotConfig

logger = logging.getLogger(__name__)

__all__ = [
    "RedisEndpoint",
    "config_manager_redis",
    "get_config_manager",
    "redis_host_from_env",
    "redis_tls_port",
    "reset_config_manager",
    "resolve_redis_endpoint",
    "ssot_redis_host",
]

# Lazily-loaded backend config manager -- present only inside autobot-backend.
_config_manager: Any = None
_config_manager_lock = Lock()


@dataclass(frozen=True)
class RedisEndpoint:
    """Where Redis is and how to authenticate to it; the password never reaches a repr."""

    host: str
    port: int
    password: str | None = field(default=None, repr=False)
    username: str | None = None
    tls: bool = False

    def url(self, db: int | None = None, *, with_auth: bool = True) -> str:
        """``redis[s]://[user:pass@]host:port[/db]``, credentials URL-encoded (#16626)."""
        scheme = "rediss" if self.tls else "redis"
        userinfo = ""
        if with_auth and self.password:
            userinfo = f"{quote(self.username or '', safe='')}:{quote(self.password, safe='')}@"
        suffix = "" if db is None else f"/{db}"
        return f"{scheme}://{userinfo}{self.host}:{self.port}{suffix}"


def get_config_manager() -> Any:
    """The backend config manager, or None where ``config`` is not importable (#2854: thread-safe)."""
    global _config_manager
    if _config_manager is None:
        with _config_manager_lock:
            if _config_manager is None:
                try:
                    # autobot-backend package; absent (ImportError) everywhere else
                    from config import config as cm  # type: ignore[attr-defined]

                    _config_manager = cm
                except ImportError:
                    pass
    return _config_manager


def reset_config_manager() -> None:
    """Drop the cached config manager, so a stub cached under test is not reused (#11830)."""
    global _config_manager
    with _config_manager_lock:
        _config_manager = None


def config_manager_redis() -> Any:
    """The config manager's Redis section, or ``{}`` where it has none."""
    try:
        cm = get_config_manager()
        return cm.get_redis_config() if cm is not None else {}
    except AttributeError:
        # ssot_config._ConfigProxy has no get_redis_config(); the later tiers answer.
        return {}


def _first_env(*names: str) -> str | None:
    """The first of *names* set to a non-blank value, stripped."""
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return None


def redis_host_from_env() -> str | None:
    """``REDIS_HOST`` / ``AUTOBOT_REDIS_HOST`` if either is set (#12778)."""
    return _first_env("REDIS_HOST", "AUTOBOT_REDIS_HOST")


def _ssot(ssot: AutoBotConfig | None) -> AutoBotConfig | None:
    """*ssot*, else the process SSOT config; None where ``ssot_config`` cannot load (#14299)."""
    if ssot is not None:
        return ssot
    try:
        from autobot_shared.ssot_config import get_config

        return get_config()
    except Exception as exc:  # pydantic-settings absent or the env unparseable: the next tier answers
        logger.debug("SSOT config unavailable for Redis resolution: %s", exc)
        return None


def ssot_redis_host(ssot: AutoBotConfig | None = None) -> str:
    """The SSOT ``vm.redis`` host, or ``""`` where SSOT config is unavailable (#14299)."""
    cfg = _ssot(ssot)
    return (cfg.vm.redis or "").strip() if cfg is not None else ""


def redis_tls_port(ssot: AutoBotConfig | None = None) -> int | None:
    """The TLS port when Redis TLS is on, else None. The env var wins over the SSOT field."""
    flag = os.getenv("AUTOBOT_REDIS_TLS_ENABLED")
    cfg = None if flag is not None else _ssot(ssot)
    enabled = flag.lower() == "true" if flag is not None else bool(cfg and cfg.tls.redis_tls_enabled)
    if not enabled:
        return None
    explicit = _first_env("AUTOBOT_REDIS_TLS_PORT")
    if explicit is not None:
        return int(explicit)
    cfg = _ssot(ssot)
    if cfg is None:
        raise ValueError("AUTOBOT_REDIS_TLS_ENABLED=true but no AUTOBOT_REDIS_TLS_PORT and no SSOT config")
    return int(cfg.tls.redis_tls_port)


def _resolve_host(cm: Any, ssot: AutoBotConfig | None) -> str:
    """The first configured host, in the module docstring's order."""
    return str(
        cm.get("host")
        or redis_host_from_env()
        or NetworkConstants.REDIS_VM_IP
        or ssot_redis_host(ssot)
        or NetworkConstants.LOCALHOST_IP
    )


def _credential(cm: Any, key: str, ssot: AutoBotConfig | None) -> str | None:
    """*key* (``password``/``username``): config manager, ``REDIS_*``, ``AUTOBOT_REDIS_*``, SSOT."""
    upper = key.upper()
    value = cm.get(key) or _first_env(f"REDIS_{upper}", f"AUTOBOT_REDIS_{upper}")
    if value:
        return str(value)
    cfg = _ssot(ssot)
    return getattr(cfg.redis, key, None) if cfg is not None else None


def resolve_redis_endpoint(ssot: AutoBotConfig | None = None) -> RedisEndpoint:
    """The Redis endpoint every client and URL in the process uses.

    *ssot* is the SSOT tier (default: the process config); every earlier tier is
    process-wide, so a URL built from any config object names the canonical client's host.
    """
    cm = config_manager_redis()
    tls_port = redis_tls_port(ssot)
    plain_port = cm.get("port") or _first_env("REDIS_PORT", "AUTOBOT_REDIS_PORT") or NetworkConstants.REDIS_PORT
    return RedisEndpoint(
        host=_resolve_host(cm, ssot),
        port=int(tls_port if tls_port is not None else plain_port),
        password=_credential(cm, "password", ssot),
        username=_credential(cm, "username", ssot),
        tls=tls_port is not None,
    )
