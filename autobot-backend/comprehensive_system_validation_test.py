#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
AutoBot Phase 9 Comprehensive System Validation
Comprehensive testing and validation suite for production readiness.

Converted from a hand-driven script to collectable pytest tests (#14979). The
previous shape -- a class with ``__init__``, a ``run_comprehensive_validation``
driver and methods that appended to a results list instead of asserting --
collected zero items, so none of these eight checks had ever run under pytest.
Hardcoded VM addresses were replaced with SSOT config lookups (#1618).
"""

import shutil
import subprocess
from http import HTTPStatus

import pytest
import requests

from autobot_shared.live_service_probe import endpoint_is_listening, require_live_endpoint
from autobot_shared.ssot_config import config

BACKEND_URL = config.backend_url

# Every service the validator probes, addressed through the SSOT rather than a
# literal VM address. Keys are the human names used in assertion messages.
BACKEND_SERVICE = "the AutoBot backend API"
REDIS_SERVICE = "Redis"
DISTRIBUTED_SERVICES = {
    BACKEND_SERVICE: BACKEND_URL,
    REDIS_SERVICE: config.redis_url,
    "the frontend dev server": config.frontend_url,
    "the NPU worker": config.npu_worker_url,
    "the AI stack": config.aistack_url,
    "the browser service": config.browser_service_url,
}

# Services no other check in this module can proceed without.
CORE_SERVICES = (BACKEND_SERVICE, REDIS_SERVICE)

HEALTH_ENDPOINT = "/api/health"
KB_STATS_ENDPOINT = "/api/knowledge_base/stats/basic"
LLM_STATUS_ENDPOINT = "/api/llm/status"
LLM_MODELS_ENDPOINT = "/api/llm/models"

API_ENDPOINTS = (
    (HEALTH_ENDPOINT, "Health Check"),
    ("/api/endpoints", "Router Registry"),
    (KB_STATS_ENDPOINT, "Knowledge Base Stats"),
    (LLM_STATUS_ENDPOINT, "LLM Status"),
    ("/api/system/status", "System Status"),
    ("/ws/health", "WebSocket Health"),
    ("/api/chat/health", "Chat Health"),
)

# Env-var backed rather than a literal at each call site: a loaded stack needs a
# wider budget than a loopback one, and no caller should hardcode its own.
REQUEST_TIMEOUT_SECONDS = 10.0
COMMAND_TIMEOUT_SECONDS = 30.0

# `docker ps` failure text that means the daemon is absent rather than broken.
DOCKER_ABSENT_MARKERS = ("cannot connect to the docker daemon", "could not be found", "is the docker daemon running")


def _get(path: str) -> requests.Response:
    """GET a backend path through the SSOT-resolved base URL."""
    return requests.get(f"{BACKEND_URL}{path}", timeout=REQUEST_TIMEOUT_SECONDS)


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    """Run a host inspection command with a bounded budget."""
    return subprocess.run(argv, capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SECONDS, check=False)


def _root_disk_usage_percent(df_output: str) -> int:
    """Parse the used-percentage column out of ``df -h /`` output."""
    rows = [line.split() for line in df_output.strip().splitlines()[1:] if line.strip()]
    assert rows, f"`df -h /` produced no data row: {df_output!r}"
    percentages = [field for field in rows[0] if field.endswith("%")]
    assert percentages, f"`df -h /` row carries no usage percentage: {rows[0]}"
    return int(percentages[0].rstrip("%"))


@pytest.mark.integration
class TestAutoBotSystemValidation:
    """Production-readiness checks that drive the deployed AutoBot stack."""

    @pytest.fixture(autouse=True)
    def _require_live_stack(self) -> None:
        """Skip when the AutoBot backend is absent (#14930)."""
        require_live_endpoint(BACKEND_URL, what=BACKEND_SERVICE)

    def test_infrastructure_connectivity(self) -> None:
        """The distributed stack's services accept connections.

        The core pair is mandatory; the original script graded a minority
        outage as a warning and only a majority outage as a failure, and that
        severity model is preserved rather than tightened silently.
        """
        unreachable = [name for name, url in DISTRIBUTED_SERVICES.items() if not endpoint_is_listening(url)]

        core_down = [name for name in CORE_SERVICES if name in unreachable]
        assert not core_down, f"core services of the distributed stack are not accepting connections: {core_down}"

        tolerated = len(DISTRIBUTED_SERVICES) // 2
        assert len(unreachable) <= tolerated, (
            f"{len(unreachable)} of {len(DISTRIBUTED_SERVICES)} configured services are unreachable "
            f"({unreachable}); at most {tolerated} may be down before the stack counts as failed"
        )

    def test_api_endpoints(self) -> None:
        """Every documented endpoint answers, and none answers with a server error.

        Auth-gated routes legitimately answer 401 to this unauthenticated
        client, so the contract asserted here is "the backend answered and did
        not fault", plus at least one successful response.
        """
        statuses = {f"{description} ({path})": _get(path).status_code for path, description in API_ENDPOINTS}

        faulted = {name: code for name, code in statuses.items() if code >= HTTPStatus.INTERNAL_SERVER_ERROR}
        assert not faulted, f"backend endpoints answered with a server error: {faulted}"

        assert (
            HTTPStatus.OK in statuses.values()
        ), f"the backend accepted the connection but served none of its documented endpoints: {statuses}"

    def test_single_endpoint(self) -> None:
        """The health endpoint -- the one route every other check depends on."""
        response = _get(HEALTH_ENDPOINT)

        assert (
            response.status_code == HTTPStatus.OK
        ), f"GET {HEALTH_ENDPOINT} answered {response.status_code}, expected 200"
        payload = response.json()
        assert payload.get("status"), f"{HEALTH_ENDPOINT} returned no 'status' field: {sorted(payload)}"
        assert payload.get("service"), f"{HEALTH_ENDPOINT} names no service: {sorted(payload)}"
        assert isinstance(
            payload.get("services"), dict
        ), f"{HEALTH_ENDPOINT} published no per-service health map: {sorted(payload)}"

    def test_knowledge_base_functionality(self) -> None:
        """The knowledge base router is mounted and reports itself healthy."""
        response = _get(KB_STATS_ENDPOINT)

        assert (
            response.status_code != HTTPStatus.NOT_FOUND
        ), f"{KB_STATS_ENDPOINT} is not served — the knowledge base router is not mounted"
        assert (
            response.status_code < HTTPStatus.INTERNAL_SERVER_ERROR
        ), f"{KB_STATS_ENDPOINT} faulted with HTTP {response.status_code}"

        if response.status_code == HTTPStatus.OK:
            stats = response.json()
            for counter in ("total_documents", "total_chunks", "total_facts"):
                value = stats.get(counter)
                assert isinstance(value, int) and value >= 0, f"{counter} is not a non-negative integer: {value!r}"

        kb_state = _get(HEALTH_ENDPOINT).json().get("services", {}).get("knowledge_base")
        assert kb_state, "the backend health map reports no knowledge_base state"
        assert kb_state not in {"error", "unavailable", "failed"}, f"the knowledge base reports state {kb_state!r}"

    def test_llm_integration(self) -> None:
        """The LLM status and model routes are mounted and answer without faulting."""
        for path in (LLM_STATUS_ENDPOINT, LLM_MODELS_ENDPOINT):
            response = _get(path)
            assert response.status_code != HTTPStatus.NOT_FOUND, f"{path} is not served — the LLM router is not mounted"
            assert (
                response.status_code < HTTPStatus.INTERNAL_SERVER_ERROR
            ), f"{path} faulted with HTTP {response.status_code}"

        status = _get(LLM_STATUS_ENDPOINT)
        if status.status_code == HTTPStatus.OK:
            payload = status.json()
            assert payload, f"{LLM_STATUS_ENDPOINT} answered 200 with an empty body"
            ollama = payload.get("ollama")
            if ollama is not None:
                assert ollama.get("status"), f"{LLM_STATUS_ENDPOINT} reported an Ollama entry with no status: {ollama}"

    def test_docker_services(self) -> None:
        """The AutoBot stack is running under the local Docker daemon."""
        if shutil.which("docker") is None:
            pytest.skip("docker is not installed on this host")

        result = _run(["docker", "ps", "--format", "{{.Names}}"])
        output = f"{result.stdout}\n{result.stderr}".lower()
        if result.returncode != 0:
            if any(marker in output for marker in DOCKER_ABSENT_MARKERS):
                pytest.skip(f"the Docker daemon is not reachable: {result.stderr.strip() or result.stdout.strip()}")
            pytest.fail(f"`docker ps` exited {result.returncode}: {result.stderr.strip()}")

        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        autobot_containers = [name for name in names if "autobot" in name.lower()]
        assert autobot_containers, f"no AutoBot container is running; Docker reports: {names or 'no containers'}"


class TestSystemValidationLocalEnvironment:
    """Checks that run entirely in-process or against the local host."""

    def test_router_registry(self) -> None:
        """The router registry is populated and its status view is self-consistent."""
        from api.registry import registry

        enabled = registry.get_enabled_routers()
        assert enabled, "the router registry reports no enabled routers — the backend would serve nothing"
        assert set(enabled) <= set(
            registry.routers
        ), f"get_enabled_routers() returned names the registry does not hold: {sorted(set(enabled) - set(registry.routers))}"

        incomplete = {
            name: [field for field in ("module_path", "prefix", "tags") if not getattr(entry, field)]
            for name, entry in enabled.items()
        }
        broken = {name: missing for name, missing in incomplete.items() if missing}
        assert not broken, f"enabled routers are missing the fields needed to mount them: {broken}"

        chat_routers = {name: entry for name, entry in enabled.items() if "chat" in name}
        assert chat_routers, f"no chat router is enabled; enabled routers: {sorted(enabled)}"
        for name, entry in chat_routers.items():
            assert entry.prefix, f"enabled chat router {name!r} declares no URL prefix"

    def test_system_resources(self) -> None:
        """CPU, memory and disk telemetry are readable from the host."""
        for tool in ("top", "df"):
            if shutil.which(tool) is None:
                pytest.skip(f"{tool} is not available on this host")

        top_result = _run(["top", "-bn1"])
        assert top_result.returncode == 0, f"`top -bn1` exited {top_result.returncode}: {top_result.stderr.strip()}"
        lines = top_result.stdout.splitlines()
        assert any("Cpu" in line for line in lines), "`top -bn1` produced no CPU line"
        assert any("Mem" in line for line in lines), "`top -bn1` produced no memory line"

        disk_result = _run(["df", "-h", "/"])
        assert disk_result.returncode == 0, f"`df -h /` exited {disk_result.returncode}: {disk_result.stderr.strip()}"
        usage = _root_disk_usage_percent(disk_result.stdout)
        assert 0 <= usage <= 100, f"`df -h /` reported an impossible root usage of {usage}%"
