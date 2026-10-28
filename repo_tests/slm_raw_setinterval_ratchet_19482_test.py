# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM console's hand-rolled pollers move onto the kit's usePollingJob (#19482).

**The boundary.** The count is every ``setInterval(`` call in a ``.ts`` or ``.vue`` file
under ``autobot-slm-frontend/src``, excluding tests, specs and stories, and excluding
comment lines. 32 of the 35 measured on 129148ebe9 were pollers. None of those 32 had a
real in-flight guard, and only one (``BatchTool``) stopped after repeated failures.
``usePollingJob`` (``@autobot/ui``) gives scope disposal, a race guard and
``consecutiveErrorLimit``.

**What stays.** Three calls are not pollers and keep ``setInterval``: the WebSocket ping
heartbeat in ``useSlmWebSocket`` (its reconnect already uses ``backoffDelay``), the
progress-bar tick in ``NodeLifecyclePanel``, and the stale-task watchdog in the
``provision`` store. So the floor is 3, not 0.

**One number, not a per-file table.** A per-file pin would list frontend paths in a
``repo_tests`` module, and ``python_filter_covers_its_guards_test.py`` would then require
the python suite on every SLM change (see ``_hardcoded_colour_baseline.py``). The pin is
down-only against the base (#19283) and exact: a PR that migrates a poller lowers it by
what it removed.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_table

_SLM_SRC = "autobot-slm-frontend/src"
_EXCLUDED = re.compile(r"(\.test\.|\.spec\.|\.stories\.|/__tests__/)")
_CALL = re.compile(r"\bsetInterval\s*\(")
_COMMENT = re.compile(r"^\s*(//|\*|/\*)")

# 35 measured on 129148ebe9; 29 after the first batch (BatchTool, InfrastructureWizard,
# SystemUpdatesTab); 23 after the second (RedisServicePanel, NPUPerformanceMetrics,
# NPUWorkerMonitor, LLMFallbacksView, Sidebar, CodeSyncBadge); 4 after the third (AgentsTool,
# MCPTool, NPUWorkersSettings, LogViewer, PerformanceOverview, usePerformanceMonitoring,
# AlertsMonitor, MetricsDetailsView, useFleetMetrics, ErrorMonitor, OrchestrationView,
# AdminMonitoringView, LoadBalancingView, NodeServicesPanel, NodeLifecyclePanel's event
# poller, the provision store's status poller; #19482). The 4 left are the 3 non-pollers
# plus ``composables/useSkills.ts``, deferred because an open PR holds that file; the pin
# reaches FLOOR once it moves. Lower it by exactly what a PR migrates.
PINS = {"raw_setinterval_calls": 4}

# The non-poller calls that keep setInterval; the count cannot go below these.
FLOOR = 3


def count_raw_setinterval(root: Path) -> int:
    total = 0
    for path in sorted(root.rglob("*")):
        # Matched inside the scanned root, so a checkout path cannot exclude everything.
        if path.suffix not in (".ts", ".vue") or _EXCLUDED.search("/" + path.relative_to(root).as_posix()):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not _COMMENT.match(line):
                total += len(_CALL.findall(line))
    return total


class TestTheDetectorWorksBeforeItsOutputIsRead:
    def _w(self, root: Path, rel: str, body: str) -> None:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    def test_it_counts_a_call_in_a_component_and_a_composable(self, tmp_path: Path) -> None:
        self._w(tmp_path, "views/A.vue", "<script setup>\nconst t = setInterval(load, 5000)\n</script>\n")
        self._w(tmp_path, "composables/useB.ts", "timer = setInterval(() => refresh(), ms)\n")
        assert count_raw_setinterval(tmp_path) == 2

    def test_it_skips_tests_stories_and_comments(self, tmp_path: Path) -> None:
        self._w(tmp_path, "views/A.test.ts", "setInterval(x, 1)\n")
        self._w(tmp_path, "views/A.stories.ts", "setInterval(x, 1)\n")
        self._w(tmp_path, "views/__tests__/B.ts", "setInterval(x, 1)\n")
        self._w(tmp_path, "views/C.vue", "// was setInterval(x, 1) before #19482\n * setInterval(y)\n")
        assert count_raw_setinterval(tmp_path) == 0

    def test_a_checkout_path_that_looks_like_a_test_excludes_nothing(self, tmp_path: Path) -> None:
        root = tmp_path / "x.test.y" / "src"
        self._w(root, "views/A.vue", "setInterval(load, 1)\n")
        assert count_raw_setinterval(root) == 1

    def test_clear_interval_is_not_a_call(self, tmp_path: Path) -> None:
        self._w(tmp_path, "views/A.vue", "clearInterval(timer)\n")
        assert count_raw_setinterval(tmp_path) == 0


def test_the_slm_does_not_hand_roll_more_pollers_than_pinned() -> None:
    root = repo_root() / _SLM_SRC
    assert root.is_dir(), f"{_SLM_SRC} has moved; this guard reads it by path"
    now = count_raw_setinterval(root)
    pinned = PINS["raw_setinterval_calls"]
    assert now <= pinned, (
        f"{now} raw setInterval calls in {_SLM_SRC}, pin allows {pinned} (#19482). "
        "Poll with usePollingJob from @autobot/ui instead of a hand-rolled interval."
    )
    assert now == pinned, f"{now} raw setInterval calls, pin says {pinned}: lower PINS to {now} in this PR (#19482)."
    assert now >= FLOOR, f"{now} is below the {FLOOR} non-poller calls; update FLOOR and the docstring"


def test_the_pin_was_not_raised_against_the_base() -> None:
    base = base_table(repo_root(), ("repo_tests/slm_raw_setinterval_ratchet_19482_test.py",), "PINS")
    if not base:
        return  # the guard is new at this base; nothing to compare against yet
    assert PINS["raw_setinterval_calls"] <= base["raw_setinterval_calls"], (
        f"PINS rose from {base['raw_setinterval_calls']} to {PINS['raw_setinterval_calls']} (#19482); "
        "the pin only goes down."
    )
