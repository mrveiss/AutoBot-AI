#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Distributed System Integration Testing for AutoBot
Tests the 6-VM architecture and prevents distributed system failures

Converted from an operational script to a pytest suite (#14979). The
``DistributedSystemTester`` class defined ``__init__``, so pytest collected
none of its three ``test_*`` methods; they were helpers taking arguments,
called by a ``run_comprehensive_distributed_tests`` driver that printed a
health score and by the three module-level tests below.

The service registry, health probes and partition scenarios are now
module-level helpers, so the three module-level tests and the three class
methods share one implementation and every one of them collects. Each class
method asserts something the module-level rate assertions do not cover.

Two endpoints the original drove do not exist on the backend and could never
have reported communication: ``/api/system/status`` and ``/api/llm/status``
(404 and 401 respectively). The Redis path now reads ``components.redis`` from
``/api/system/health``, which the backend does serve, and the Ollama path
probes the LLM endpoint's own ``/api/tags``.
"""

import asyncio
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import pytest

from autobot_shared.live_service_probe import endpoint_is_listening, require_live_endpoint
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

# #12510: every check dials a real service across the distributed topology.
pytestmark = pytest.mark.distributed

# #1618: hosts and ports come from the SSOT — the literal 10.0.0.x addresses
# this registry used to carry were an internal topology hardcoded in a test.
SERVICES: Dict[str, Dict[str, Any]] = {
    "main": {"host": config.vm.main, "port": config.port.backend, "name": "Backend API"},
    "frontend": {"host": config.vm.frontend, "port": config.port.frontend, "name": "Web Interface"},
    "npu_worker": {"host": config.vm.npu, "port": config.port.npu, "name": "NPU Worker"},
    "redis": {"host": config.vm.redis, "port": config.port.redis, "name": "Redis Data Layer"},
    "ai_stack": {"host": config.vm.aistack, "port": config.port.aistack, "name": "AI Processing"},
    "browser": {"host": config.vm.browser, "port": config.port.browser, "name": "Web Automation"},
    "ollama": {"host": config.vm.ollama, "port": config.port.ollama, "name": "LLM Processing"},
    "vnc": {"host": config.vm.main, "port": config.port.vnc, "name": "Desktop Access"},
}

CRITICAL_PATHS: List[Tuple[str, str]] = [
    ("frontend", "main"),
    ("main", "redis"),
    ("main", "ai_stack"),
    ("main", "ollama"),
    ("ai_stack", "npu_worker"),
    ("main", "browser"),
]

# Env-var-backed module constants: a fleet deployment needs a different budget
# from a loopback install, and no call site should hardcode its own.
HEALTH_TIMEOUT_SECONDS = 10.0
RECOVERY_BUDGET_SECONDS = 30.0

MIN_SERVICE_HEALTH_RATE = 60.0
MIN_COMMUNICATION_SUCCESS_RATE = 50.0
CONSISTENCY_PROBE_KEY = "autobot_distributed_consistency_probe"
UNROUTED_BACKEND_PATH = "/api/__autobot_unrouted_probe__"

PARTITION_SCENARIOS: Dict[str, List[str]] = {
    "redis_isolation": ["redis"],
    "frontend_backend_split": ["frontend", "main"],
    "ai_stack_isolation": ["ai_stack", "npu_worker"],
}


@dataclass
class ServiceResult:
    """Result of service health check"""

    service_name: str
    host: str
    port: int
    status: str
    response_time: float
    error: Optional[str] = None
    details: Optional[Dict] = None


@dataclass
class NetworkPartitionResult:
    """Result of network partition test"""

    partition_type: str
    affected_services: List[str]
    recovery_time: float
    data_consistency: bool
    error_handling: bool


@pytest.fixture(autouse=True)
def _require_live_backend() -> None:
    """Skip when the AutoBot backend is absent (#14930).

    The backend anchors every path in ``CRITICAL_PATHS`` and answers the
    component health this module reads. With it down, each check here reports a
    refused connection rather than a distributed-system result.
    """
    require_live_endpoint(_service_url("main"), what="the AutoBot backend API")


def _service_url(name: str) -> str:
    """Return the base HTTP URL of a registered service."""
    service = SERVICES[name]
    return f"http://{service['host']}:{service['port']}"


def _is_listening(name: str) -> bool:
    """True when a registered service is accepting TCP connections."""
    service = SERVICES[name]
    return endpoint_is_listening(str(service["host"]), port=int(service["port"]))


def _require_full_topology() -> None:
    """Skip unless every registered service is accepting connections.

    The two aggregate assertions below score a *deployed* topology. On a host
    where the VMs were never brought up, a low score measures the host's
    inventory, not AutoBot — the non-result class #14930 exists to stop. A
    service that is listening but answering wrongly still fails, which is the
    distinction that matters.
    """
    absent = sorted(name for name in SERVICES if not _is_listening(name))
    if absent:
        pytest.skip(f"the distributed topology is not deployed on this host — absent services: {absent}")


async def _probe_service_health(service_name: str, timeout: float = HEALTH_TIMEOUT_SECONDS) -> ServiceResult:
    """Return the health of one registered service."""
    service = SERVICES[service_name]

    if service_name == "redis":
        return await _probe_redis_health(service)
    if service_name == "vnc":
        return await _probe_http_health(service_name, service, timeout, path="/vnc.html")
    if service_name == "frontend":
        return await _probe_http_health(service_name, service, timeout, path="/")
    if service_name == "ollama":
        return await _probe_http_health(service_name, service, timeout, path="/api/tags")
    if service_name == "main":
        # The backend mounts everything under /api; a bare /health is unrouted.
        return await _probe_http_health(service_name, service, timeout, path="/api/health")
    return await _probe_http_health(service_name, service, timeout, path="/health")


async def _probe_http_health(name: str, service: Dict, timeout: float, path: str) -> ServiceResult:
    """Return the health of one HTTP service, reporting transport faults as errors."""
    url = f"http://{service['host']}:{service['port']}{path}"
    started = time.time()

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(url) as response:
                try:
                    details = await response.json(content_type=None)
                except ValueError:
                    details = {"text": (await response.text())[:200]}

                return ServiceResult(
                    service_name=name,
                    host=str(service["host"]),
                    port=int(service["port"]),
                    status="healthy" if response.status == 200 else "unhealthy",
                    response_time=time.time() - started,
                    details=details if isinstance(details, dict) else {"body": details},
                )
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        return ServiceResult(
            service_name=name,
            host=str(service["host"]),
            port=int(service["port"]),
            status="error",
            response_time=time.time() - started,
            error=f"{type(exc).__name__}: {exc}",
        )


async def _probe_redis_health(service: Dict) -> ServiceResult:
    """Return Redis health measured with a real PING over redis-cli."""
    started = time.time()
    if shutil.which("redis-cli") is None:
        return ServiceResult(
            service_name="redis",
            host=str(service["host"]),
            port=int(service["port"]),
            status="error",
            response_time=time.time() - started,
            error="redis-cli is not installed on this host",
        )

    result = _redis_cli(service, ["ping"])
    healthy = result.returncode == 0 and "PONG" in result.stdout
    return ServiceResult(
        service_name="redis",
        host=str(service["host"]),
        port=int(service["port"]),
        status="healthy" if healthy else "unhealthy",
        response_time=time.time() - started,
        details={"response": result.stdout.strip()} if healthy else None,
        error=None if healthy else (result.stderr.strip() or "no PONG response"),
    )


def _redis_cli(service: Dict, arguments: List[str]) -> subprocess.CompletedProcess:
    """Run redis-cli against a registered Redis service."""
    return subprocess.run(
        ["redis-cli", "-h", str(service["host"]), "-p", str(service["port"]), *arguments],
        capture_output=True,
        text=True,
        timeout=HEALTH_TIMEOUT_SECONDS,
        encoding="utf-8",
    )


async def _probe_service_communication(source: str, target: str) -> Tuple[bool, str, float]:
    """Return whether one service can reach another, with the elapsed seconds."""
    if source == "main" and target == "redis":
        return await _probe_backend_component("redis")
    if source == "main" and target == "ollama":
        return await _probe_named_service("ollama", "/api/tags")
    if source == "main" and target == "ai_stack":
        return await _probe_named_service("ai_stack", "/health")
    return await _probe_named_service(target, "/health" if target != "main" else "/api/health", source=source)


async def _probe_named_service(target: str, path: str, source: str = "main") -> Tuple[bool, str, float]:
    """Probe one service's endpoint and describe the path result."""
    started = time.time()
    result = await _probe_http_health(target, SERVICES[target], HEALTH_TIMEOUT_SECONDS, path)
    elapsed = time.time() - started

    if result.status == "healthy":
        return True, f"{source}->{target} communication successful", elapsed
    return False, f"{source}->{target} failed: {result.status} ({result.error or result.details})", elapsed


async def _probe_backend_component(component: str) -> Tuple[bool, str, float]:
    """Read one component's state out of the backend's own health report."""
    started = time.time()
    result = await _probe_http_health("main", SERVICES["main"], HEALTH_TIMEOUT_SECONDS, "/api/system/health")
    elapsed = time.time() - started

    if result.status != "healthy":
        return False, f"backend health report unavailable: {result.status} ({result.error})", elapsed

    state = (result.details or {}).get("components", {}).get(component)
    if state == "ok":
        return True, f"backend reports component {component!r} ok", elapsed
    return False, f"backend reports component {component!r} as {state!r}, expected 'ok'", elapsed


async def _run_partition_scenario(partition_type: str) -> NetworkPartitionResult:
    """Measure how the named scenario's services report after a disruption window.

    Nothing here severs a link — the runner has no authority over the fabric.
    What is measured is real: how long the affected services take to report
    healthy, whether a Redis write survives the window, and whether the backend
    still rejects an unrouted path cleanly instead of hanging or crashing.
    """
    affected = PARTITION_SCENARIOS[partition_type]
    for name in affected:
        require_live_endpoint(_service_url(name), what=f"the AutoBot {SERVICES[name]['name']} service")

    logger.info("Measuring partition scenario %s over services %s", partition_type, affected)
    recovery_time = await _measure_recovery(affected)

    return NetworkPartitionResult(
        partition_type=partition_type,
        affected_services=affected,
        recovery_time=recovery_time,
        data_consistency=_check_redis_round_trip(),
        error_handling=await _check_backend_rejects_unrouted_path(),
    )


async def _measure_recovery(affected_services: List[str]) -> float:
    """Return the seconds until every affected service reports healthy."""
    started = time.time()

    while time.time() - started < RECOVERY_BUDGET_SECONDS:
        results = [await _probe_service_health(name, timeout=5) for name in affected_services]
        if all(result.status == "healthy" for result in results):
            break
        await asyncio.sleep(1)

    return time.time() - started


def _check_redis_round_trip() -> bool:
    """True when a value written to Redis reads back intact."""
    if shutil.which("redis-cli") is None:
        pytest.skip("redis-cli is not installed — the data-consistency check writes through it")

    service = SERVICES["redis"]
    written = _redis_cli(service, ["set", CONSISTENCY_PROBE_KEY, "consistent", "EX", "30"])
    read_back = _redis_cli(service, ["get", CONSISTENCY_PROBE_KEY])
    _redis_cli(service, ["del", CONSISTENCY_PROBE_KEY])

    return written.returncode == 0 and read_back.returncode == 0 and read_back.stdout.strip() == "consistent"


async def _check_backend_rejects_unrouted_path() -> bool:
    """True when the backend answers an unrouted path with a clean client error."""
    result = await _probe_http_health("main", SERVICES["main"], HEALTH_TIMEOUT_SECONDS, UNROUTED_BACKEND_PATH)
    return result.status == "unhealthy"


class TestDistributedSystem:
    """Per-path assertions the aggregate rate checks below do not cover."""

    def setup_method(self) -> None:
        """Bind the SSOT service registry and the critical-path list."""
        self.services = SERVICES
        self.critical_paths = CRITICAL_PATHS

    async def test_service_health(self) -> None:
        """The backend anchor answers its health check with a usable report."""
        result = await _probe_service_health("main")

        assert result.status == "healthy", (
            f"the Backend API at {result.host}:{result.port} reported {result.status!r} "
            f"after {result.response_time:.3f}s: {result.error!r}"
        )
        assert isinstance(result.details, dict) and result.details.get(
            "status"
        ), f"the Backend API answered 200 but its health report carries no 'status': {result.details!r}"

    async def test_service_communication(self) -> None:
        """The frontend-to-backend critical path answers."""
        success, message, elapsed = await _probe_service_communication("frontend", "main")

        assert success, f"the frontend->main critical path failed after {elapsed:.3f}s: {message}"

    async def test_network_partition_simulation(self) -> None:
        """Services in a partition scenario report back inside the recovery budget."""
        result = await _run_partition_scenario("frontend_backend_split")

        assert result.recovery_time < RECOVERY_BUDGET_SECONDS, (
            f"services {result.affected_services} did not all report healthy within "
            f"{RECOVERY_BUDGET_SECONDS:.0f}s (took {result.recovery_time:.1f}s)"
        )
        assert result.error_handling, (
            f"the backend did not answer the unrouted path {UNROUTED_BACKEND_PATH} with a client error — "
            f"an unrouted request must be rejected cleanly, not served or hung"
        )


# Test Functions for Pytest Integration
async def test_all_services_healthy():
    """Test that all distributed services are healthy"""
    _require_full_topology()

    results = [await _probe_service_health(name) for name in SERVICES]
    healthy = [result for result in results if result.status == "healthy"]
    health_rate = (len(healthy) / len(results)) * 100
    unhealthy = {result.service_name: result.status for result in results if result.status != "healthy"}

    assert health_rate >= MIN_SERVICE_HEALTH_RATE, (
        f"only {health_rate:.1f}% of services healthy, expected at least "
        f"{MIN_SERVICE_HEALTH_RATE:.0f}%; not healthy: {unhealthy}"
    )


async def test_critical_communication_paths():
    """Test critical communication paths work"""
    _require_full_topology()

    outcomes = [
        (source, target, await _probe_service_communication(source, target)) for source, target in CRITICAL_PATHS
    ]
    successful = [entry for entry in outcomes if entry[2][0]]
    success_rate = (len(successful) / len(outcomes)) * 100
    failures = [f"{source}->{target}: {result[1]}" for source, target, result in outcomes if not result[0]]

    assert success_rate >= MIN_COMMUNICATION_SUCCESS_RATE, (
        f"only {success_rate:.1f}% of communication paths working, expected at least "
        f"{MIN_COMMUNICATION_SUCCESS_RATE:.0f}%; failing paths: {failures}"
    )


async def test_network_partition_recovery():
    """Test system recovers from network partitions"""
    partition_result = await _run_partition_scenario("redis_isolation")

    assert partition_result.recovery_time < RECOVERY_BUDGET_SECONDS, (
        f"partition recovery took {partition_result.recovery_time:.1f}s, " f"expected < {RECOVERY_BUDGET_SECONDS:.0f}s"
    )
    assert partition_result.data_consistency, (
        f"a value written to Redis at {SERVICES['redis']['host']}:{SERVICES['redis']['port']} "
        f"did not read back intact across the partition window"
    )
    assert (
        partition_result.error_handling
    ), f"the backend did not answer the unrouted path {UNROUTED_BACKEND_PATH} with a client error"
