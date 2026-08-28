#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
AutoBot Multi-Agent Workflow Validation
Tests the complete multi-agent coordination system for production readiness

Every check below issues real HTTP against a deployed backend, so the module
carries ``integration`` and one autouse precondition that skips — with a named
reason — when nothing is listening (``autobot_shared/live_service_probe.py``,
#14930).

Before #14979 this was a driver script wearing test names: the class defined
``__init__`` (so pytest collected nothing at all), each ``test_*`` method
returned ``True``/``False`` into ``run_multi_agent_validation()``, and the only
verdict was a printed summary plus a JSON file nothing read. Six checks that
collected zero items now collect six, and each one asserts.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests

from autobot_shared.live_service_probe import require_live_endpoint
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

# #12510 / #14979: real HTTP against a running backend — excluded from the unit
# gate, selected by marker-tests.yml.
pytestmark = pytest.mark.integration

logger = get_logger(__name__)

# #15133: the host and port were hard-coded here, so the script probed one fixed
# node regardless of where the backend actually runs.
BACKEND_URL = config.backend_url

#: Paths probed to decide whether each agent is reachable. Every entry is a GET
#: the backend actually serves, enforced against the router registry by
#: ``multi_agent_workflow_probe_endpoints_test.py``. The first two entries used
#: to be ``/api/intelligent-agent/deploy`` and ``/api/research/deploy``: no
#: router has served a ``/deploy`` path under either prefix at any commit, under
#: any spelling -- the capability does not exist and never did (#15133).
AGENT_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("/api/intelligent_agent/system-info", "Intelligent Agent"),
    ("/api/research-browser/sessions", "Research Agent"),
    ("/api/knowledge_base/health/status", "Knowledge Agent"),
    ("/api/llm/status", "LLM Agent"),
)

#: The liveness path every AutoBot backend serves, aliased in ``middleware.py``.
HEALTH_PATH = "/api/health"

#: Fired concurrently to prove the backend serves overlapping requests. Reusing
#: the registry-enforced agent paths keeps this list from drifting into probes of
#: routes no router serves — the exact defect #15133 removed from the list above.
PARALLEL_PROBE_PATHS: tuple[str, ...] = (HEALTH_PATH,) + tuple(path for path, _agent in AGENT_ENDPOINTS)

#: Deliberately unserved paths. A backend that is up must answer these with a
#: 4xx; a 5xx means an unhandled error escaped the router, and a refused
#: connection means the process died mid-suite.
UNSERVED_PROBE_PATHS: tuple[str, ...] = (
    "/api/nonexistent/endpoint",
    "/api/chat/invalid_method",
    "/api/knowledge_base/malformed",
)

#: Coordination is meaningful only once more than one agent answers.
MIN_COORDINATING_AGENTS = 2

# Generous, because the backend answers a cold agent route in ~2s and these run
# concurrently: the timeout must not become the thing being measured.
REQUEST_TIMEOUT_SECONDS = 30.0
# A knowledge-base search is a vector query over the whole store, and its latency
# is load-dependent — measured between 0.3s idle and >70s while several suites
# were driving the same host. 30s made this the flakiest assertion in the file,
# failing on load rather than on the behaviour it names. This is an
# `integration`-marked test that only runs where a stack is up, so a long budget
# costs nothing and a breach is then a real statement about the endpoint.
#
# This number is NOT arbitrary and must not be raised again to make a failure go
# away: the endpoint's non-response under load is tracked as #15165, and that
# issue owns lowering this allowance once the endpoint is bounded. Raising it
# further would only hide #15165 the way the pre-conversion `except` did.
TASK_TIMEOUT_SECONDS = 180.0
CHAT_TIMEOUT_SECONDS = 60.0


@pytest.fixture(autouse=True)
def _require_live_backend() -> None:
    """Skip when the AutoBot backend API is absent (#14930).

    All six checks drive the deployed backend over HTTP. On a runner without one
    every check failed with a refused connection — six red results that measured
    the runner's inventory rather than multi-agent coordination.
    """
    require_live_endpoint(BACKEND_URL, what="the AutoBot backend API")


def _get(path: str, timeout: float = REQUEST_TIMEOUT_SECONDS) -> requests.Response:
    """GET *path* on the backend. Transport errors propagate: the autouse probe
    already established that something is listening, so a refused connection here
    is a real regression, not an absent service."""
    return requests.get(f"{BACKEND_URL}{path}", timeout=timeout)


class TestMultiAgentWorkflow:
    """Multi-agent coordination, parallelism, task completion and resilience.

    A deployment may require authentication, and an unauthenticated client then
    gets 401 from every agent route. That is the route answering, not an agent
    being down, so the contract asserted throughout is the one
    ``comprehensive_system_validation_test.py`` settled on: *the path is served
    (not 404) and the backend did not fault (not 5xx)*, with the deeper
    payload assertions applied whenever the client did get a 200.
    """

    def test_backend_availability(self) -> None:
        """The backend answers its health path with HTTP 200."""
        response = _get(HEALTH_PATH)

        assert response.status_code == 200, (
            f"backend health check {HEALTH_PATH} returned HTTP {response.status_code} "
            f"instead of 200; body: {response.text[:300]}"
        )
        logger.info("backend availability confirmed", elapsed_s=response.elapsed.total_seconds())

    def test_multi_agent_coordination(self) -> None:
        """Every probed agent path is served, and enough agent routers answer to coordinate."""
        statuses = {agent: _get(path).status_code for path, agent in AGENT_ENDPOINTS}

        unserved = [
            (path, agent) for (path, agent) in AGENT_ENDPOINTS if statuses[agent] == 404
        ]  # the backend answered, so it is up; it simply does not serve this path (#15133)
        assert not unserved, (
            "no router serves these probed paths — a defect in AGENT_ENDPOINTS, never a "
            "sleeping agent: " + ", ".join(f"{path} ({agent})" for path, agent in unserved)
        )

        faulted = {agent: status for agent, status in statuses.items() if status >= 500}
        assert not faulted, f"agent routes faulted with a server error: {faulted}"

        answering = sorted(agent for agent, status in statuses.items() if status < 500)
        assert len(answering) >= MIN_COORDINATING_AGENTS, (
            f"only {len(answering)} of {len(AGENT_ENDPOINTS)} agent routers answered "
            f"({answering or 'none'}); at least {MIN_COORDINATING_AGENTS} are needed for "
            f"coordination. Full status map: {statuses}"
        )

    def test_parallel_task_execution(self) -> None:
        """Overlapping requests are all served, and do not serialise into a queue."""
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=len(PARALLEL_PROBE_PATHS)) as pool:
            statuses = list(pool.map(lambda path: _get(path).status_code, PARALLEL_PROBE_PATHS))
        elapsed = time.perf_counter() - started

        failures = [(path, status) for path, status in zip(PARALLEL_PROBE_PATHS, statuses) if status >= 500]
        assert not failures, "concurrent requests faulted: " + ", ".join(
            f"{path} -> HTTP {status}" for path, status in failures
        )
        assert 200 in statuses, (
            f"none of the {len(PARALLEL_PROBE_PATHS)} concurrent requests succeeded — the "
            f"backend served no route at all under concurrency: {dict(zip(PARALLEL_PROBE_PATHS, statuses))}"
        )

        serial_ceiling = len(PARALLEL_PROBE_PATHS) * REQUEST_TIMEOUT_SECONDS
        assert elapsed < serial_ceiling, (
            f"{len(PARALLEL_PROBE_PATHS)} concurrent requests took {elapsed:.2f}s, at or beyond "
            f"the fully-serialised ceiling of {serial_ceiling:.0f}s — the backend is not "
            f"overlapping them"
        )

    def test_agent_task_completion(self) -> None:
        """A knowledge-base search — the canonical agent task — is served and completes."""
        try:
            response = requests.post(
                f"{BACKEND_URL}/api/knowledge_base/search",
                json={"query": "AutoBot system architecture", "limit": 5},
                timeout=TASK_TIMEOUT_SECONDS,
            )
        except requests.exceptions.ReadTimeout as exc:
            # Not swallowed — re-raised as the assertion this test exists to make.
            # The pre-conversion version wrapped this call in a bare `except` and
            # logged a warning, which is how an endpoint that never answers stayed
            # invisible for the life of the file (#14979).
            raise AssertionError(
                f"/api/knowledge_base/search accepted the connection but sent no response "
                f"within {TASK_TIMEOUT_SECONDS}s — the canonical agent task never completes (#15165)."
            ) from exc

        assert (
            response.status_code != 404
        ), "/api/knowledge_base/search is not served — the knowledge agent's router is not mounted"
        assert (
            response.status_code < 500
        ), f"knowledge base search faulted with HTTP {response.status_code}; body: {response.text[:300]}"

        if response.status_code == 200:
            payload = response.json()
            assert isinstance(
                payload, dict
            ), f"knowledge base search returned {type(payload).__name__}, expected a JSON object"
            assert "results" in payload, (
                f"knowledge base search answered 200 but the body carries no 'results' key; "
                f"keys present: {sorted(payload)}"
            )

    def test_agent_communication_workflow(self) -> None:
        """A chat turn routes through the agents without the backend erroring."""
        response = requests.post(
            f"{BACKEND_URL}/api/chat/direct",
            json={"message": "What Redis configuration does AutoBot use for distributed VMs?"},
            timeout=CHAT_TIMEOUT_SECONDS,
        )

        assert (
            response.status_code != 404
        ), "/api/chat/direct is not served — the inter-agent chat workflow has no entry point"
        assert response.status_code < 500, (
            f"inter-agent chat workflow returned HTTP {response.status_code} — an unhandled "
            f"server error escaped the chat pipeline; body: {response.text[:300]}"
        )

        if response.status_code == 200:
            assert (
                response.text.strip()
            ), "chat workflow answered 200 with an empty body — the agents produced no response"

    def test_system_resilience(self) -> None:
        """Unserved paths come back as client errors, not server errors."""
        statuses = {path: _get(path).status_code for path in UNSERVED_PROBE_PATHS}

        mishandled = {path: status for path, status in statuses.items() if not 400 <= status < 500}
        assert (
            not mishandled
        ), "the backend did not handle unserved paths gracefully — each should answer 4xx: " + ", ".join(
            f"{path} -> HTTP {status}" for path, status in mishandled.items()
        )
