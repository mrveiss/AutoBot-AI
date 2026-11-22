# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One ServiceRegistry for the infrastructure deployment scripts (#18132).

`ServiceStatus` is an ALIAS of the canonical `autobot_shared.status_enums.HealthStatus`,
not a new enum: #6973 forbids a fresh `*Status(Enum)` outside the canonical module, and
the three members the scripts used (HEALTHY/UNHEALTHY/UNKNOWN) are an exact subset of
HealthStatus by NAME AND VALUE, so the alias changes no serialized value.

`ServiceRegistry` was defined six times across `autobot-infrastructure/shared/scripts`,
with six distinct bodies: a copied class that each script then trimmed to what it needed
(9, 8, 8, 4, 3 and 2 methods). The method bodies agreed, which is why a body-level census
reported them as identical duplication -- but the classes were subsets of one another, so
the remediation is a union, not a move.

This is that union: the richest copy's nine methods plus `update_service_url`, which
existed only in `zero_downtime_deploy.py`.

It lives beside the scripts because they reach siblings through the
`_SCRIPTS_DIR`-on-sys.path pattern they already use for `backup_manager` (#14518), and
it reaches `autobot_shared` through the repo-root bootstrap `deployment_rollback.py`
uses (#11761).

Since #12771 the service table, URL construction, health-state shape and
`DeploymentMode` are NOT defined here: they come from
`autobot_shared.service_registry_core`, the same module the backend registry consumes,
and ports/hosts come from `ssot_config` through it. What stays here is what only the
scripts do: the urllib/TCP probe, env-driven mode detection and `populate_services`.

Env contract (#12771): hosts and ports resolve through `ssot_config`, so they follow the
SSOT's env names and `.env`. Six of the seven former `AUTOBOT_<NAME>_HOST` names are SSOT
aliases and behave as before (BACKEND, FRONTEND, REDIS, OLLAMA, AI_STACK, NPU_WORKER).
MIGRATION: `AUTOBOT_PLAYWRIGHT_VNC_HOST` is no longer read; set `AUTOBOT_BROWSER_SERVICE_HOST`
(its SSOT name; nothing in the repo set the old one). The unset-host default is now
`127.0.0.1` where it was `localhost`.

Two divergences are preserved deliberately rather than flattened:

* `_SERVICE_DEFS` had two shapes -- a 2-tuple in `backup_manager.py` and a 3-tuple
  elsewhere. The superset (with health path) is what the shared table now carries.
* `populate_services` exists because `zero_downtime_deploy.py` deliberately started with
  an EMPTY registry and filled it through `update_service_url`. A union that always built
  URLs eagerly would have changed its behaviour silently, so it passes False.
"""

from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# The repo root goes on sys.path so autobot_shared is importable from this
# standalone-script directory -- same bootstrap deployment_rollback.py already uses for
# autobot_shared.paths (#11761).
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from autobot_shared.logging_manager import get_logger  # noqa: E402
from autobot_shared.service_registry_core import (  # noqa: E402 - follows the sys.path setup
    SERVICE_DEFINITIONS,
    DeploymentMode,
    ServiceHealth,
    join_service_path,
    resolve_deployment_mode,
)
from autobot_shared.status_enums import HealthStatus  # noqa: E402

logger = get_logger(__name__)

#: #6973: the canonical ladder, aliased rather than re-declared.
ServiceStatus = HealthStatus

__all__ = [
    "SERVICE_DEFINITIONS",
    "DeploymentMode",
    "ServiceHealth",
    "ServiceRegistry",
    "ServiceStatus",
    "get_deployment_registry",
]


class ServiceRegistry:
    """Canonical service registry for the deployment scripts.

    `services` is built eagerly unless `populate_services=False`, which preserves the
    one caller that fills the map itself.
    """

    def __init__(self, config_file: Optional[str] = None, *, populate_services: bool = True) -> None:
        self.config_file = config_file
        self.deployment_mode = self._detect_deployment_mode()
        self.services: Dict[str, str] = (
            {name: d.base_url() for name, d in SERVICE_DEFINITIONS.items()} if populate_services else {}
        )

    @staticmethod
    def _detect_deployment_mode() -> DeploymentMode:
        """The shared resolver: AUTOBOT_DEPLOYMENT_MODE when set and valid, else detection (#19316)."""
        return resolve_deployment_mode(logger)

    @staticmethod
    def _probe(url: str, timeout: float = 5.0) -> bool:
        """Probe a service: TCP connect for redis, HTTP GET otherwise."""
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme == "redis":
            try:
                with socket.create_connection((parsed.hostname, parsed.port), timeout=timeout):
                    return True
            except OSError:
                return False
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
                # bool() because urlopen's response is typed Any under strict mypy.
                return bool(response.status == 200)
        except (urllib.error.URLError, OSError, ValueError):
            return False

    async def check_all_services_health(self) -> Dict[str, ServiceHealth]:
        """Check health of all registered services."""
        names = self.list_services()
        results = await asyncio.gather(*(self.check_service_health(name) for name in names))
        return dict(zip(names, results))

    async def check_service_health(self, service_name: str) -> ServiceHealth:
        """Check health of a single service."""
        url = self.get_service_url(service_name, SERVICE_DEFINITIONS[service_name].health_path)
        start = time.time()
        ok = await asyncio.get_running_loop().run_in_executor(None, self._probe, url)
        return ServiceHealth(
            status=ServiceStatus.HEALTHY if ok else ServiceStatus.UNHEALTHY,
            last_check=time.time(),
            response_time=time.time() - start,
        )

    def get_deployment_info(self) -> Dict[str, Any]:
        """Get deployment information."""
        return {
            "deployment_mode": self.deployment_mode.value,
            "services_count": len(self.services),
            "services": {name: {"url": url} for name, url in self.services.items()},
        }

    def get_service_url(self, service_name: str, path: str = "") -> str:
        """Get full URL for a service."""
        if service_name not in self.services:
            raise ValueError(f"Service '{service_name}' not found in registry")
        return join_service_path(self.services[service_name], "", path)

    def list_services(self) -> List[str]:
        """List registered service names."""
        return list(self.services)

    def update_service_url(self, name: str, url: str) -> None:
        """Point a service at a new base URL.

        In-process only: this standalone stand-in has no persistent store —
        the canonical registry lives in autobot-backend/utils/service_registry.py.
        """
        self.services[name] = url


_registries: Dict[Tuple[Optional[str], bool], ServiceRegistry] = {}


def get_deployment_registry(config_file: Optional[str] = None, *, populate_services: bool = True) -> ServiceRegistry:
    """Get the process-wide ServiceRegistry for these arguments (#18964).

    One instance per ``(config_file, populate_services)`` pair, so the script that fills
    the map itself (``populate_services=False``) never shares an instance with one that
    expects the eager default, even when both run in the same process.
    """
    key = (config_file, populate_services)
    if key not in _registries:
        _registries[key] = ServiceRegistry(config_file, populate_services=populate_services)
    return _registries[key]
