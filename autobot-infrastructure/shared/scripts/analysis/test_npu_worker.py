#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Simplified NPU Worker Test for AutoBot Startup
==============================================

Tests basic NPU Worker functionality without external dependencies.
Used during AutoBot startup to verify NPU Worker health.

Converted from an operational script to a pytest suite (#14979). The class
defined ``__init__``, so pytest collected none of its three ``test_*`` methods;
they returned ``(bool, payload)`` tuples to a ``run_tests`` driver that printed
an 80%-pass-rate verdict. Every check now asserts, and the ``requests`` /
``urllib`` availability shims are gone — both are hard dependencies of this
repository, and a missing one is an installation fault, not a test outcome.
"""

import json
import urllib.request

import pytest
import requests

from autobot_shared.live_service_probe import require_live_endpoint
from autobot_shared.ssot_config import config

# #12510: every check dials the NPU worker over real HTTP.
pytestmark = pytest.mark.integration

# #1618: endpoint from the SSOT — no hardcoded host or port.
NPU_WORKER_URL = config.npu_worker_url
HTTP_TIMEOUT_SECONDS = 10.0

# The service name and the status/capability invariant below are the worker's
# own published contract — see roles/npu-worker/templates/npu-worker.py.j2,
# which serves exactly two routes (/health and /) and derives
# ``status = "healthy" if capabilities["available"] else "degraded"``.
NPU_WORKER_SERVICE_NAME = "npu-worker"


def _assert_status_matches_capabilities(payload: dict) -> None:
    """Assert the reported status agrees with the reported accelerator state.

    ``degraded`` is a legitimate steady state — it means this host has no usable
    NPU — so asserting ``healthy`` outright would make the suite a hardware
    inventory. What must always hold is that the worker's headline status and
    its own capability report agree; a mismatch is a real defect in the worker.
    """
    capabilities = payload.get("capabilities", {})
    available = bool(capabilities.get("available", False))
    expected = "healthy" if available else "degraded"
    assert payload.get("status") == expected, (
        f"NPU worker reports status {payload.get('status')!r} while its capability report says "
        f"available={available!r}; the two contradict each other: {payload!r}"
    )


@pytest.fixture(autouse=True)
def _require_live_npu_worker() -> None:
    """Skip when the NPU worker is absent (#14930).

    All three checks drive the same one service, so a single module-level guard
    names the missing half of the stack once instead of reporting three refused
    connections as failures.
    """
    require_live_endpoint(NPU_WORKER_URL, what="the AutoBot NPU worker")


class TestNPUWorker:
    """Health and endpoint checks against a running NPU worker."""

    def setup_method(self) -> None:
        """Bind the SSOT NPU worker endpoint and the request budget."""
        self.npu_url = NPU_WORKER_URL
        self.timeout = HTTP_TIMEOUT_SECONDS

    def test_health_urllib(self) -> None:
        """The health endpoint answers 200 and identifies itself over stdlib urllib."""
        request = urllib.request.Request(f"{self.npu_url}/health")

        with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - SSOT http endpoint
            status = response.status
            body = response.read().decode("utf-8")

        assert status == 200, f"NPU worker {self.npu_url}/health returned HTTP {status} over urllib, expected 200"
        payload = json.loads(body)
        assert payload.get("service") == NPU_WORKER_SERVICE_NAME, (
            f"{self.npu_url} answers /health but names itself {payload.get('service')!r}, "
            f"not {NPU_WORKER_SERVICE_NAME!r} — another service holds the NPU worker port"
        )

    def test_health_requests(self) -> None:
        """The health endpoint reports a status consistent with its capabilities."""
        response = requests.get(f"{self.npu_url}/health", timeout=self.timeout)

        assert (
            response.status_code == 200
        ), f"NPU worker {self.npu_url}/health returned HTTP {response.status_code} over requests, expected 200"
        payload = response.json()
        assert payload.get("version"), f"NPU worker health payload carries no 'version' field: {payload!r}"
        _assert_status_matches_capabilities(payload)

    def test_basic_endpoints(self) -> None:
        """The root endpoint advertises the routes the worker actually serves."""
        response = requests.get(f"{self.npu_url}/", timeout=self.timeout)

        assert (
            response.status_code == 200
        ), f"NPU worker {self.npu_url}/ returned HTTP {response.status_code}, expected 200"
        payload = response.json()
        endpoints = payload.get("endpoints", [])
        assert "/health" in endpoints, (
            f"NPU worker root advertises {endpoints!r}, which omits /health — the route every "
            f"caller in this repository probes"
        )

        health = requests.get(f"{self.npu_url}/health", timeout=self.timeout).json()
        capabilities = health.get("capabilities", {})
        assert capabilities.get("device"), (
            f"NPU worker reports no inference device in its capabilities — it cannot serve "
            f"accelerated work: {capabilities!r}"
        )
        assert isinstance(
            capabilities.get("models_loaded"), list
        ), f"NPU worker reports models_loaded={capabilities.get('models_loaded')!r}, expected a list"
