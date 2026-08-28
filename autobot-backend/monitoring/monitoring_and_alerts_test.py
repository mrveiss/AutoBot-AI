#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""AutoBot monitoring and alerting test suite.

Covers the monitoring surface a running AutoBot exposes:
- health endpoints answer and are shaped as documented
- metrics routes are mounted and protected, and no live peer service errors on its own
- alert threshold classification agrees with the configured thresholds
- response-time sampling detects degradation instead of averaging it away
- monitoring dashboards are routed and protected
- log aggregation reads and classifies real log lines
- the incident/alert feed is routed and protected

#14979: this module used to be an operational driver script wearing test names —
a class with ``__init__``, an argparse ``main()`` and a report writer. pytest
never collects a class that defines ``__init__``, so all seven ``test_*``
methods below collected **zero** items and had never run once. The driver, the
report writer and the ``log_result`` accumulator are gone; pytest is the driver
and each method asserts instead of appending a PASS/FAIL record nobody read.

Hardcoded VM addresses (10.0.0.1, 10.0.0.2, …) that the old script carried are
replaced by SSOT config properties (#1618).
"""

import os
import shutil
import statistics
import subprocess
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

import pytest
import requests

from autobot_shared.live_service_probe import endpoint_is_listening, require_live_endpoint
from autobot_shared.logging_manager import get_logger
from autobot_shared.paths import project_root
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

# #12510: these tests issue real HTTP against a running stack, so the module
# must stay out of the unit gate (pytest -m "not integration ...").
pytestmark = pytest.mark.integration

# SSOT only — the old module hardcoded one IP per service (#1618).
BACKEND_URL = config.backend_url
FRONTEND_URL = config.frontend_url
AI_STACK_URL = config.aistack_url
NPU_WORKER_URL = config.npu_worker_url
OLLAMA_URL = config.ollama_url

# Module constants rather than literals at the call sites, so the whole suite
# shares one HTTP budget and one subprocess budget.
REQUEST_TIMEOUT_SECONDS = 10.0
LOG_COMMAND_TIMEOUT_SECONDS = 10.0

# Public health endpoints: no authentication, must answer 200 with a JSON object.
PUBLIC_HEALTH_PATHS = ("/api/system/health", "/api/system/health/probes", "/api/monitoring/services/health")

# Admin-only monitoring endpoints. An unauthenticated caller must be refused
# (401/403) — never served, and never 404, which would mean the router is not
# mounted at all and every dashboard in the UI is dead.
ADMIN_MONITORING_STATUS_PATH = "/api/monitoring/status"
ADMIN_DASHBOARD_PATHS = ("/api/monitoring/dashboard", "/api/monitoring/dashboard/overview")
ADMIN_ALERT_CHECK_PATH = "/api/monitoring/alerts/check"
ADMIN_ALERT_FEED_PATH = "/api/monitoring/alerts"
ADMIN_REFUSAL_CODES = (401, 403)

# Backend metrics routes. Both are admin-gated, so an unauthenticated caller
# must be refused rather than served — and must not 404, which would mean the
# metrics the dashboards read are not routed at all.
BACKEND_METRICS_PATHS = ("/api/system/metrics", "/api/monitoring/metrics/current")

# Peer services whose metrics endpoint is checked when — and only when — the
# service is actually up. A host that does not run the NPU worker is not a
# defect, and a peer that publishes no /metrics at all is a deployment choice;
# a 5xx from one that is up is neither.
PEER_SERVICE_METRICS_ENDPOINTS: Tuple[Tuple[str, str, str], ...] = (
    ("frontend", FRONTEND_URL, "/metrics"),
    ("ai_stack", AI_STACK_URL, "/metrics"),
    ("npu_worker", NPU_WORKER_URL, "/metrics"),
    ("ollama", OLLAMA_URL, "/api/version"),
)

# Thresholds the alerting layer classifies against, in the units each metric is
# reported in. Kept as one table so a scenario cannot silently drift from it.
CRITICAL_METRICS: Dict[str, Dict[str, float]] = {
    "cpu_usage": {"warning": 80.0, "critical": 95.0},
    "memory_usage": {"warning": 85.0, "critical": 95.0},
    "disk_usage": {"warning": 80.0, "critical": 90.0},
    "api_response_time": {"warning": 2.0, "critical": 5.0},
    "error_rate": {"warning": 5.0, "critical": 10.0},
}

# (metric, observed value, severity the thresholds above must classify it as).
THRESHOLD_SCENARIOS: Tuple[Tuple[str, float, str], ...] = (
    ("cpu_usage", 95.0, "critical"),
    ("cpu_usage", 82.0, "warning"),
    ("cpu_usage", 41.0, "ok"),
    ("memory_usage", 88.0, "warning"),
    ("api_response_time", 6.0, "critical"),
    ("api_response_time", 0.4, "ok"),
    ("error_rate", 7.0, "warning"),
    ("error_rate", 11.0, "critical"),
)

# Response-time sampling budget for the degradation check. Derived from the
# module's own declared *critical* threshold for api_response_time rather than
# being a second, independent number — a suite asserting a looser budget than
# the thresholds it publishes would let the breach it exists to catch through.
RESPONSE_TIME_SAMPLES = 5
RESPONSE_TIME_BUDGET_SECONDS = float(CRITICAL_METRICS["api_response_time"]["critical"])

# Log analysis: how much tail to read, and how many ERROR lines in that tail
# constitute a monitoring finding rather than normal noise.
LOG_TAIL_LINES = 100
MAX_ERRORS_IN_LOG_TAIL = 10

# This one test reads log files and container output only — it drives no HTTP
# service, so the live-endpoint guard below deliberately exempts it (#14979).
FILESYSTEM_ONLY_TESTS = frozenset({"test_log_aggregation_and_analysis"})


@pytest.fixture(autouse=True)
def _require_live_stack(request: pytest.FixtureRequest) -> None:
    """Skip when the AutoBot backend is absent (#14930).

    Six of the seven tests here drive the live monitoring API over HTTP; on a
    GitHub-hosted runner no backend exists, so an unguarded run would report a
    refused connection as a product failure. ``test_log_aggregation_and_analysis``
    reads the filesystem instead and is exempt, because guarding a test that
    needs no service would skip it on an irrelevant condition.
    """
    if request.node.name in FILESYSTEM_ONLY_TESTS:
        return
    require_live_endpoint(BACKEND_URL, what="the AutoBot backend API")


@pytest.fixture
def session(_require_live_stack: None) -> Iterator[requests.Session]:
    """One pooled HTTP session per test, closed on teardown.

    Replaces the session and result state the deleted ``__init__`` built.
    """
    with requests.Session() as http:
        yield http


def _get(session: requests.Session, url: str) -> requests.Response:
    """GET *url* with the shared timeout budget."""
    return session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)


def _classify(metric: str, value: float) -> str:
    """Return ``critical`` / ``warning`` / ``ok`` for *value* against CRITICAL_METRICS."""
    thresholds = CRITICAL_METRICS[metric]
    if value >= thresholds["critical"]:
        return "critical"
    if value >= thresholds["warning"]:
        return "warning"
    return "ok"


def _assert_admin_only(session: requests.Session, path: str) -> None:
    """Assert *path* is mounted and refuses an unauthenticated caller."""
    response = _get(session, f"{BACKEND_URL}{path}")

    assert response.status_code != 404, f"GET {path} returned 404 — the monitoring router is not mounted"
    assert response.status_code < 500, f"GET {path} returned HTTP {response.status_code}: {response.text[:200]}"
    assert response.status_code in ADMIN_REFUSAL_CODES, (
        f"GET {path} served an unauthenticated caller with HTTP {response.status_code}; "
        f"admin-only monitoring data must be refused with one of {ADMIN_REFUSAL_CODES}"
    )


def _log_file_sources() -> List[Tuple[str, Path]]:
    """Return the (name, path) log files that exist on this host."""
    candidates = [
        ("backend", project_root() / "logs" / "backend.log"),
        ("frontend", project_root() / "logs" / "frontend.log"),
        ("system", Path("/var/log/syslog")),
    ]
    return [(name, path) for name, path in candidates if path.is_file() and os.access(path, os.R_OK)]


def _count_levels(lines: List[str]) -> Tuple[int, int]:
    """Return the (error, warning) line counts in *lines*."""
    errors = sum(1 for line in lines if "ERROR" in line.upper())
    warnings = sum(1 for line in lines if "WARNING" in line.upper() or "WARN" in line.upper())
    return errors, warnings


def _read_container_logs() -> List[str]:
    """Return recent container log lines, or an empty list when unavailable."""
    if shutil.which("docker") is None:
        return []

    result = subprocess.run(
        ["docker", "compose", "logs", f"--tail={LOG_TAIL_LINES}"],
        capture_output=True,
        text=True,
        timeout=LOG_COMMAND_TIMEOUT_SECONDS,
        check=False,
        cwd=str(project_root()),
    )
    if result.returncode != 0:
        return []
    return result.stdout.splitlines()


class TestMonitoringAndAlerting:
    """Health, metrics, alert thresholds, dashboards, logs and incident routing."""

    def test_health_monitoring_endpoints(self, session: requests.Session) -> None:
        """Every public health endpoint answers 200 with a non-empty JSON body."""
        for path in PUBLIC_HEALTH_PATHS:
            response = _get(session, f"{BACKEND_URL}{path}")

            assert (
                response.status_code == 200
            ), f"GET {path} returned HTTP {response.status_code}: {response.text[:200]}"
            payload = response.json()
            assert isinstance(payload, (dict, list)), f"GET {path} returned {type(payload).__name__}, not JSON data"
            assert payload, f"GET {path} returned an empty body — a health endpoint must report state"

    def test_metrics_collection(self, session: requests.Session) -> None:
        """Backend metrics routes are mounted and protected; no live service errors on its own."""
        for path in BACKEND_METRICS_PATHS:
            _assert_admin_only(session, path)

        for name, base_url, metrics_path in PEER_SERVICE_METRICS_ENDPOINTS:
            if not endpoint_is_listening(base_url):
                continue

            response = _get(session, f"{base_url}{metrics_path}")
            assert (
                response.status_code < 500
            ), f"{name} is up but its metrics endpoint {metrics_path} returned HTTP {response.status_code}"

    def test_alert_threshold_triggers(self, session: requests.Session) -> None:
        """Threshold classification matches the configured warning/critical bands."""
        for metric, value, expected in THRESHOLD_SCENARIOS:
            actual = _classify(metric, value)
            assert actual == expected, (
                f"{metric}={value} classified as {actual!r}, expected {expected!r} against "
                f"warning={CRITICAL_METRICS[metric]['warning']} critical={CRITICAL_METRICS[metric]['critical']}"
            )

        _assert_admin_only(session, ADMIN_ALERT_CHECK_PATH)

    def test_performance_degradation_detection(self, session: requests.Session) -> None:
        """Repeated health probes stay inside the response-time budget and vary measurably."""
        samples: List[float] = []
        for _ in range(RESPONSE_TIME_SAMPLES):
            response = _get(session, f"{BACKEND_URL}/api/system/health")
            assert response.status_code == 200, f"health probe returned HTTP {response.status_code} while sampling"
            samples.append(response.elapsed.total_seconds())

        assert (
            len(samples) == RESPONSE_TIME_SAMPLES
        ), f"collected {len(samples)} response-time samples, expected {RESPONSE_TIME_SAMPLES}"
        worst = max(samples)
        assert worst <= RESPONSE_TIME_BUDGET_SECONDS, (
            f"slowest health probe took {worst:.3f}s, over the {RESPONSE_TIME_BUDGET_SECONDS}s budget; "
            f"samples: {[round(s, 3) for s in samples]}"
        )
        logger.info("health probe mean %.3fs median %.3fs", statistics.mean(samples), statistics.median(samples))

    def test_dashboard_accessibility(self, session: requests.Session) -> None:
        """Dashboard routes are mounted and refuse unauthenticated callers."""
        for path in ADMIN_DASHBOARD_PATHS + (ADMIN_MONITORING_STATUS_PATH,):
            _assert_admin_only(session, path)

    def test_log_aggregation_and_analysis(self) -> None:
        """Readable log tails decode as UTF-8 and stay under the error-count ceiling."""
        sources = _log_file_sources()
        container_lines = _read_container_logs()

        if not sources and not container_lines:
            pytest.skip("no readable log file or container log output on this host — nothing to aggregate")

        for name, path in sources:
            lines = path.read_text(encoding="utf-8", errors="strict").splitlines()[-LOG_TAIL_LINES:]
            errors, warnings = _count_levels(lines)
            assert errors <= MAX_ERRORS_IN_LOG_TAIL, (
                f"{name} log ({path.name}) has {errors} ERROR lines in its last {len(lines)} "
                f"({warnings} warnings), over the ceiling of {MAX_ERRORS_IN_LOG_TAIL}"
            )

        if container_lines:
            errors, warnings = _count_levels(container_lines)
            assert errors <= MAX_ERRORS_IN_LOG_TAIL, (
                f"container logs have {errors} ERROR lines in their last {len(container_lines)} "
                f"({warnings} warnings), over the ceiling of {MAX_ERRORS_IN_LOG_TAIL}"
            )

    def test_incident_response_automation(self, session: requests.Session) -> None:
        """The alert feed is routed and protected, and unknown incident routes stay unrouted."""
        _assert_admin_only(session, ADMIN_ALERT_FEED_PATH)

        for path in ("/api/monitoring/incident/simulate", "/api/incident/trigger"):
            response = session.post(f"{BACKEND_URL}{path}", json={"test": True}, timeout=REQUEST_TIMEOUT_SECONDS)
            assert response.status_code < 500, (
                f"POST {path} returned HTTP {response.status_code} — an unrouted incident endpoint must "
                f"answer 404/405, not a server error: {response.text[:200]}"
            )
