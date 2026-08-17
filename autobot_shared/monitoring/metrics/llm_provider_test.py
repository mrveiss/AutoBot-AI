# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard tests for LLMProviderMetricsRecorder (#14211).

``LLMProviderMetricsRecorder`` (~21 metrics, #470) and the provisioned
``AutoBot LLM Providers`` Grafana dashboard (#475) existed with zero emit
calls anywhere in the codebase — every one of the 16 data panels rendered
``No Data``. These guard tests exist so that gap cannot regrow silently:

1. At least one production call site must reach the recorder's public
   ``record_llm_*`` API (reproduces the issue's own repro command).
2. Every metric series the dashboard queries must be a series the recorder
   can actually emit — catches name drift such as
   ``autobot_llm_provider_available`` vs. ``..._availability``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from prometheus_client import CollectorRegistry

from autobot_shared.monitoring.metrics.llm_provider import LLMProviderMetricsRecorder

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DASHBOARD_PATH = (
    _REPO_ROOT
    / "autobot-infrastructure"
    / "shared"
    / "config"
    / "grafana"
    / "dashboards"
    / "autobot-llm-providers.json"
)

# Public record_* / set_* methods callers use to feed the recorder — mirrors
# the issue's own reproduction grep.
_RECORDER_CALL_PATTERN = re.compile(
    r"\.(?:record_llm_request_start|record_llm_request_complete|record_llm_tokens|"
    r"record_llm_cost|record_llm_error|set_llm_provider_available|update_llm_rate_limits)\("
)

# Files that only *define* the API, or exist purely to exercise it under test —
# neither counts as a production caller.
_NON_PRODUCTION_SUFFIXES = ("_test.py", "prometheus_metrics.py", "llm_provider.py")


def _iter_python_files(root: Path):
    # Exclude by parts *relative to root* — the repo itself may be checked out
    # inside a directory named ".worktrees" (worktree-per-task convention), so
    # matching on the absolute path would wrongly exclude everything.
    for path in root.rglob("*.py"):
        relative_parts = path.relative_to(root).parts
        if any(part in {"venv", "node_modules", ".worktrees", "__pycache__"} for part in relative_parts):
            continue
        yield path


class TestRecorderHasProductionCaller:
    """Guard: LLMProviderMetricsRecorder must have at least one real caller."""

    def test_at_least_one_production_call_site(self):
        search_roots = [_REPO_ROOT / "autobot-backend", _REPO_ROOT / "autobot_shared"]
        offenders_found = []
        for root in search_roots:
            if not root.exists():
                continue
            for path in _iter_python_files(root):
                if path.name.endswith(_NON_PRODUCTION_SUFFIXES):
                    continue
                text = path.read_text(encoding="utf-8")
                if _RECORDER_CALL_PATTERN.search(text):
                    offenders_found.append(path)

        assert offenders_found, (
            "LLMProviderMetricsRecorder has zero production callers — see #14211. "
            "Expected at least one of record_llm_request_start/_complete/"
            "record_llm_tokens/record_llm_cost/record_llm_error to be called "
            "outside recorder definitions and tests."
        )


def _exercise_recorder(recorder: LLMProviderMetricsRecorder) -> None:
    """Call every public record_*/set_*/update_* method once.

    Prometheus client collectors only expose *samples* for series that have
    actually been written to — an un-exercised Counter/Histogram reports an
    empty ``family.samples`` even though it is fully wired. Exercising the
    whole public API here is what "a series the recorder can emit" means.
    """
    recorder.record_request_start("test-provider")
    recorder.record_request_complete("test-provider", "test-model", "chat", 1.0, time_to_first_token_seconds=0.5)
    recorder.record_tokens("test-provider", "test-model", 10, 20)
    recorder.set_context_window_usage("test-provider", "test-model", 42.0)
    recorder.record_cost("test-provider", "test-model", 0.01, 0.02)
    recorder.set_budget_remaining("test-provider", 5.0)
    recorder.record_error("test-provider", "test-model", "timeout")
    recorder.record_retry("test-provider", "test-model", "timeout")
    recorder.set_error_rate("test-provider", 1.0)
    recorder.update_rate_limits("test-provider", 100, 1000, 30.0)
    recorder.record_rate_limited("test-provider")
    recorder.set_provider_available("test-provider", True)
    recorder.set_provider_latency_p99("test-provider", 0.2)
    recorder.record_response_cache_hit("test-endpoint")
    recorder.record_response_cache_miss("test-endpoint")


class TestDashboardSeriesMatchRecorder:
    """Guard: every series the dashboard queries must be emittable (#14211)."""

    @staticmethod
    def _recorder_sample_names() -> set[str]:
        recorder = LLMProviderMetricsRecorder(CollectorRegistry())
        _exercise_recorder(recorder)
        names: set[str] = set()
        for family in recorder.registry.collect():
            for sample in family.samples:
                names.add(sample.name)
        return names

    @staticmethod
    def _dashboard_metric_names() -> set[str]:
        data = json.loads(_DASHBOARD_PATH.read_text(encoding="utf-8"))
        names: set[str] = set()
        pattern = re.compile(r"autobot_llm_[a-z_]+")
        for panel in data.get("panels", []):
            for target in panel.get("targets", []):
                expr = target.get("expr", "")
                names.update(pattern.findall(expr))
        return names

    def test_dashboard_json_exists(self):
        assert _DASHBOARD_PATH.exists(), f"Grafana dashboard not found at {_DASHBOARD_PATH}"

    def test_every_dashboard_series_is_emittable(self):
        dashboard_names = self._dashboard_metric_names()
        assert dashboard_names, "No autobot_llm_* series found in the dashboard — parser or fixture drift"

        emittable = self._recorder_sample_names()
        # Histograms expose <name>_bucket/_sum/_count samples; strip those
        # suffixes to compare against the base histogram name too.
        emittable_bases = {re.sub(r"_(bucket|sum|count)$", "", n) for n in emittable}

        missing = sorted(name for name in dashboard_names if name not in emittable and name not in emittable_bases)
        assert not missing, (
            f"Dashboard queries series the recorder cannot emit: {missing}. "
            "This is exactly the #14211 failure class — a panel that reads as "
            "coverage but can never receive a sample."
        )
