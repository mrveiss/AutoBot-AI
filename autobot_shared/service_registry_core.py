# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The overlapping core of the two ServiceRegistry implementations (#12771).

The backend registry (`autobot-backend/utils/service_registry.py`) and the deployment
scripts' registry (`autobot-infrastructure/shared/scripts/deployment_registry.py`) used
to mirror each other by comment, each with its own service table, URL builder and
health-state shape. This module is the one place those live; both are thin consumers.

What is here, and only this:

* ``SERVICE_DEFINITIONS`` -- service names, URL scheme and health path. Ports and hosts
  are NOT copied: each definition names the ``ssot_config`` attribute that owns them and
  reads it, so there is no second port table (``autobot_shared/ssot_config.py`` stays the
  single source).
* ``build_base_url`` / ``join_service_path`` -- the URL construction.
* ``ServiceHealth`` -- the health-state shape.
* ``DeploymentMode`` / ``parse_deployment_mode`` / ``detect_deployment_mode`` -- the
  deployment-mode vocabulary and the single detection decision; ``resolve_deployment_mode``
  is the one resolver every caller uses (#19316, #19372): ``AUTOBOT_DEPLOYMENT_MODE`` when
  set and valid, else detection.

What deliberately is NOT here: runtime discovery, circuit breaking and host patterns
(backend-only), and the urllib probe (scripts-only).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from autobot_shared import deployment_profile
from autobot_shared.ssot_config import config as ssot_config
from autobot_shared.ssot_constants import PATH_API_HEALTH, PATH_HEALTH, PATH_OLLAMA_TAGS

_ROOT_PATH = "/"


class DeploymentMode(Enum):
    """Deployment mode detection."""

    LOCAL = "local"  # Single machine, no containers
    DOCKER_LOCAL = "docker_local"  # Docker Compose on single machine
    DISTRIBUTED = "distributed"  # Services across multiple machines
    KUBERNETES = "kubernetes"  # Kubernetes deployment
    CLOUD = "cloud"  # Cloud-managed services


def parse_deployment_mode(raw: str, log: logging.Logger, source: str) -> Optional[DeploymentMode]:
    """Parse an explicit mode setting; warn and return None when it is not a mode."""
    if not raw:
        return None
    try:
        return DeploymentMode(raw.lower())
    except ValueError:
        log.warning("Invalid deployment mode from %s: %s", source, raw)
        return None


def detect_deployment_mode(
    explicit: Optional[DeploymentMode], in_container: bool, kubernetes: bool, distributed: bool
) -> DeploymentMode:
    """The one deployment-mode decision; callers only gather the signals (#12771).

    An explicit, valid mode wins. Otherwise the Kubernetes signal resolves to KUBERNETES
    with or without the Docker container marker (a pod under containerd has no ``/.dockerenv``,
    #19658); a container resolves to DISTRIBUTED, else DOCKER_LOCAL; a bare host is LOCAL.
    The deploy scripts have no cluster signals and pass ``kubernetes=False, distributed=False``.
    """
    if explicit:
        return explicit
    if kubernetes:
        return DeploymentMode.KUBERNETES
    if not in_container:
        return DeploymentMode.LOCAL
    return DeploymentMode.DISTRIBUTED if distributed else DeploymentMode.DOCKER_LOCAL


#: The marker file Docker creates in every container; its presence is the container signal.
_DOCKER_MARKER = "/.dockerenv"


def resolve_deployment_mode(
    log: Optional[logging.Logger] = None, *, kubernetes: bool = False, distributed: bool = False
) -> DeploymentMode:
    """The one deployment-mode resolver (#19316, #19372).

    The explicit mode is ``AUTOBOT_DEPLOYMENT_MODE`` read through ``deployment_profile`` (unset
    is ``""``: detect). An invalid value is warned about and detection decides.
    """
    raw = deployment_profile.deployment_mode()
    explicit = parse_deployment_mode(raw, log or logging.getLogger(__name__), deployment_profile.DEPLOYMENT_MODE_VAR)
    return detect_deployment_mode(
        explicit, in_container=os.path.exists(_DOCKER_MARKER), kubernetes=kubernetes, distributed=distributed
    )


@dataclass(frozen=True)
class ServiceEndpointSpec:
    """One registered service: static facts here, port and host read from ssot_config."""

    name: str
    port_attr: str  # attribute of ssot_config.port
    host_attr: str  # attribute of ssot_config.vm
    health_path: str
    scheme: str = "http"

    @property
    def port(self) -> int:
        """The SSOT port for this service."""
        return int(getattr(ssot_config.port, self.port_attr))

    @property
    def host(self) -> str:
        """The SSOT host for this service."""
        return str(getattr(ssot_config.vm, self.host_attr))

    def base_url(self) -> str:
        """`scheme://host:port` from SSOT; Redis's from the one endpoint resolver (#19232)."""
        if self.name == "redis":
            from autobot_shared.redis_management.endpoint import resolve_redis_endpoint

            return resolve_redis_endpoint().url(with_auth=False)
        return build_base_url(self.scheme, self.host, self.port)


SERVICE_DEFINITIONS: Dict[str, ServiceEndpointSpec] = {
    d.name: d
    for d in (
        ServiceEndpointSpec("redis", "redis", "redis", _ROOT_PATH, scheme="redis"),
        ServiceEndpointSpec("ai-stack", "aistack", "aistack", PATH_HEALTH),
        ServiceEndpointSpec("npu-worker", "npu", "npu", PATH_HEALTH),
        ServiceEndpointSpec("backend", "backend", "main", PATH_API_HEALTH),
        ServiceEndpointSpec("frontend", "frontend", "frontend", _ROOT_PATH),
        ServiceEndpointSpec("playwright-vnc", "browser", "browser", PATH_HEALTH),
        ServiceEndpointSpec("ollama", "ollama", "ollama", PATH_OLLAMA_TAGS),
    )
}


def build_base_url(scheme: str, host: str, port: int) -> str:
    """Build `scheme://host:port`."""
    return f"{scheme}://{host}:{port}"


def join_service_path(base_url: str, service_path: str = "", path: str = "") -> str:
    """Append the service's own path and a requested path to a base URL."""
    full_path = f"{service_path.rstrip('/')}{path}" if path else service_path
    if full_path and not full_path.startswith("/"):
        full_path = f"/{full_path}"
    return f"{base_url}{full_path}"


@dataclass
class ServiceHealth:
    """Service health state. `status` is a caller-owned enum (see each consumer)."""

    status: Any
    last_check: float
    failure_count: int = 0
    circuit_open_until: float = 0
    response_time: float = 0
