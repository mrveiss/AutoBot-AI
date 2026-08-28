#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot Functionality Test Suite
Comprehensive testing of all AutoBot components and features

Converted from an operational script to a pytest suite (#14979). The class
previously defined ``__init__``, so pytest refused to collect it and all eight
``test_*`` methods reported nothing at all; each one returned ``True``/``False``
to a hand-rolled ``run_comprehensive_tests`` driver that printed a summary.

Every check now asserts. Each test names the endpoint it drives and calls
``require_live_endpoint`` for *that* endpoint rather than sharing one autouse
guard: the eight checks cover six independent services, and a single guard
requiring all of them would skip the Redis check because RedisInsight is down.
"""

import shutil
import subprocess
from urllib.parse import urlsplit

import pytest
import requests

from autobot_shared.live_service_probe import require_live_endpoint, require_real_redis_client
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.ssot_config import config
from autobot_shared.ssot_constants import TTL_10_SECONDS

# #12510: every check here issues real HTTP/Redis traffic against a running
# stack, so the suite must stay out of the unit gate.
pytestmark = pytest.mark.integration

# #1618: endpoints come from the SSOT — no hardcoded hosts or ports.
FRONTEND_URL = config.frontend_url
BACKEND_URL = config.backend_url
NPU_WORKER_URL = config.npu_worker_url
AI_STACK_URL = config.aistack_url
REDIS_URL = config.redis_url

# RedisInsight has no SSOT entry (it is an operator convenience, not a service
# AutoBot talks to), so its port stays a named module constant rather than a
# bare literal at the call site. Its host is always the Redis host.
REDIS_INSIGHT_PORT = 8002
REDIS_INSIGHT_URL = f"http://{urlsplit(REDIS_URL).hostname}:{REDIS_INSIGHT_PORT}"

HTTP_TIMEOUT_SECONDS = 10.0
MIN_HEALTHY_CONTAINERS = 3
REDIS_PROBE_KEY = "autobot_functionality_probe"


class TestAutoBotFunctionality:
    """Component-by-component checks of a running AutoBot stack."""

    def setup_method(self) -> None:
        """Bind the SSOT service endpoints each test dials."""
        self.services = {
            "frontend": FRONTEND_URL,
            "backend": BACKEND_URL,
            "npu_worker": NPU_WORKER_URL,
            "ai_stack": AI_STACK_URL,
            "redis": REDIS_URL,
            "redis_insight": REDIS_INSIGHT_URL,
        }

    def test_frontend_accessibility(self) -> None:
        """The frontend dev server serves the AutoBot application."""
        url = self.services["frontend"]
        require_live_endpoint(url, what="the AutoBot frontend dev server")

        response = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS)

        assert response.status_code == 200, f"frontend {url} returned HTTP {response.status_code}, expected 200"
        assert "AutoBot" in response.text, (
            f"frontend {url} answered 200 but the body carries no 'AutoBot' marker — "
            f"something other than the AutoBot application is serving this port"
        )

    def test_backend_api(self) -> None:
        """The backend health endpoint answers with a status field."""
        url = f"{self.services['backend']}/api/system/health"
        require_live_endpoint(self.services["backend"], what="the AutoBot backend API")

        response = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS)

        assert response.status_code == 200, f"backend {url} returned HTTP {response.status_code}, expected 200"
        payload = response.json()
        assert payload.get("status"), f"backend {url} returned a health payload with no 'status' field: {payload!r}"

    def test_npu_worker(self) -> None:
        """The NPU worker identifies itself and names its inference device.

        The worker derives ``status`` from its own capability probe
        (``healthy`` iff an NPU device is usable — see
        ``roles/npu-worker/templates/npu-worker.py.j2``), so ``degraded`` is a
        statement about this host's hardware rather than about AutoBot. What is
        asserted is that the NPU port is held by the NPU worker and that the
        worker can name a device to target.
        """
        url = f"{self.services['npu_worker']}/health"
        require_live_endpoint(self.services["npu_worker"], what="the AutoBot NPU worker")

        response = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS)

        assert response.status_code == 200, f"NPU worker {url} returned HTTP {response.status_code}, expected 200"
        payload = response.json()
        assert payload.get("service") == "npu-worker", (
            f"{url} answers but names itself {payload.get('service')!r}, not 'npu-worker' — "
            f"another service holds the NPU worker port"
        )

        capabilities = payload.get("capabilities", {})
        assert capabilities.get("device"), f"NPU worker {url} reports no inference device: {capabilities!r}"

    def test_ai_stack_container(self) -> None:
        """The AI stack reports healthy and exposes at least one healthy agent."""
        url = f"{self.services['ai_stack']}/health"
        require_live_endpoint(self.services["ai_stack"], what="the AutoBot AI stack")

        response = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS)

        assert response.status_code == 200, f"AI stack {url} returned HTTP {response.status_code}, expected 200"
        payload = response.json()
        assert (
            payload.get("status") == "healthy"
        ), f"AI stack {url} reported status {payload.get('status')!r}, expected 'healthy'"

        agents = payload.get("agents", {})
        healthy = [name for name, data in agents.items() if data.get("status") == "healthy"]
        assert healthy, f"AI stack {url} is healthy but none of its {len(agents)} agents are: {agents!r}"

    async def test_redis_connectivity(self) -> None:
        """A value written through the centralised Redis client reads back intact."""
        require_real_redis_client("the AutoBot Redis connectivity check")
        require_live_endpoint(REDIS_URL, what="the AutoBot Redis data layer")

        client = await get_async_redis_client(database="main")
        assert (
            client is not None
        ), f"get_async_redis_client(database='main') returned None while {REDIS_URL} is accepting connections"

        await client.ping()
        await client.set(REDIS_PROBE_KEY, "test_value", ex=TTL_10_SECONDS)
        value = await client.get(REDIS_PROBE_KEY)
        await client.delete(REDIS_PROBE_KEY)

        assert (
            value == "test_value"
        ), f"Redis round-trip of {REDIS_PROBE_KEY!r} returned {value!r}, expected 'test_value'"

    def test_redis_insight(self) -> None:
        """The RedisInsight web interface serves its UI."""
        url = self.services["redis_insight"]
        require_live_endpoint(url, what="the AutoBot RedisInsight interface")

        response = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS)

        assert response.status_code == 200, f"RedisInsight {url} returned HTTP {response.status_code}, expected 200"

    def test_docker_containers(self) -> None:
        """At least three AutoBot containers report an up or healthy state."""
        _require_docker_daemon()

        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=HTTP_TIMEOUT_SECONDS,
            encoding="utf-8",
        )
        assert result.returncode == 0, f"`docker ps` exited {result.returncode}: {result.stderr.strip()!r}"

        containers = [line for line in result.stdout.splitlines() if "autobot" in line.lower()]
        healthy = [line for line in containers if _reports_running(line)]

        assert len(healthy) >= MIN_HEALTHY_CONTAINERS, (
            f"only {len(healthy)} of {len(containers)} AutoBot containers report up/healthy, "
            f"expected at least {MIN_HEALTHY_CONTAINERS}: {containers!r}"
        )

    def test_system_integration(self) -> None:
        """A listening frontend is backed by a live node/vite process."""
        require_live_endpoint(FRONTEND_URL, what="the AutoBot frontend dev server")

        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=HTTP_TIMEOUT_SECONDS,
            encoding="utf-8",
        )
        assert result.returncode == 0, f"`ps aux` exited {result.returncode}: {result.stderr.strip()!r}"

        vite_processes = [line for line in result.stdout.splitlines() if "node" in line and "vite" in line]

        assert vite_processes, (
            f"the frontend answers on {FRONTEND_URL} but no node/vite process is running on this host — "
            f"the port is served by something other than the AutoBot dev server"
        )


def _require_docker_daemon() -> None:
    """Skip the calling test iff no Docker daemon is reachable.

    The same narrow boundary ``live_service_probe`` draws for TCP endpoints:
    *the runtime under inspection is absent* is a skip, and anything the daemon
    itself reports back is a real result. ``shutil.which`` alone is not enough —
    WSL ships a ``docker`` shim that exists even when Docker Desktop's
    integration is off, and it exits non-zero with an advisory instead.
    """
    if shutil.which("docker") is None:
        pytest.skip("the docker CLI is not installed — this test inspects a live container runtime")

    probe = subprocess.run(
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        capture_output=True,
        text=True,
        timeout=HTTP_TIMEOUT_SECONDS,
        encoding="utf-8",
    )
    if probe.returncode != 0:
        pytest.skip(f"no Docker daemon is reachable from this host: {probe.stderr.strip() or probe.stdout.strip()!r}")


def _reports_running(container_line: str) -> bool:
    """True when a ``docker ps`` line reports an up or healthy container."""
    status = container_line.split("\t")[-1].lower()
    return "healthy" in status or "up" in status
