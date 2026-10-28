# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Data tables in both GUIs move onto the kit's BaseTable (#17562).

**The boundary.** The sites are the ``.vue`` files under each app's ``src`` that
hold a raw ``<table`` tag (then whitespace, ``>`` or line end) outside a ``<!-- -->`` comment (single or
multi-line) and on a line that is not a ``//`` comment, excluding tests, specs and stories. Measured on 8c511bf0d6: 36 in ``autobot-frontend``, 34 in ``autobot-slm-frontend``.
``BaseTable`` (``@autobot/ui``) gives one header style, sorting, the empty state, the loading
state and the accessible caption, so a hand-rolled table re-implements each of them.

**What may stay.** A key/value layout (``ChartCell``, ``EntityDetail``) is not a data table
and may keep ``<table>``. The guard has no by-name exemption: such files stay inside the pin.

**Pinned per file, so a swap fails.** A total passes when one file is converted and another gains a
table, so each app's pin maps a path *relative to that app's src* to its count of table-opening
lines. A file the pin does not list is a NEW site; a listed file whose count fell or vanished is a
STALE entry; both fail, separately. The paths are relative to ``src`` (never repo-root paths) so
``python_filter_covers_its_guards_test.py`` does not read them as inputs and demand the python
suite on every frontend change (see ``_hardcoded_colour_baseline.py``). Pins are exact and
down-only against the base (#19283); a table inside a multi-line ``<!-- -->`` comment is not live
(#19698).
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_table, base_tree_texts

_EXCLUDED = re.compile(r"(\.test\.|\.spec\.|\.stories\.|/__tests__/)")
_TAG = re.compile(r"<table(?:[\s>]|$)")
_COMMENT = re.compile(r"^\s*//")
# Closed comments only: an unclosed ``<!--`` (e.g. inside a JS string) must not swallow the rest of the
# file and hide a live table after it -- an unclosed opener leaves the text counted, failing closed.
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

# Measured on the live tree: 41 table-opening lines in 30 autobot-frontend files, 53 in 34
# autobot-slm-frontend files (#19698). Lower an entry by exactly what a PR converts; delete it at 0.
PINS: dict[str, dict[str, int]] = {
    "autobot-frontend/src": {
        "components/agents/HeartbeatPanel.vue": 2,
        "components/analytics/AdvancedAnalytics.vue": 3,
        "components/analytics/AgentCostPanel.vue": 1,
        "components/analytics/PatternAnalysis.vue": 1,
        "components/analytics/TechnicalDebtDashboard.vue": 1,
        "components/analytics/code-intelligence/FindingsTable.vue": 1,
        "components/artifact-cells/ChartCell.vue": 2,
        "components/audit/AuditLogTable.vue": 1,
        "components/file-browser/FileListTable.vue": 1,
        "components/knowledge/KnowledgeEntries.vue": 1,
        "components/knowledge/graph/EntityDetail.vue": 1,
        "components/llc/ExecutorRollupPanel.vue": 1,
        "components/operations/OperationsList.vue": 1,
        "components/visualizations/ServiceMessageTimeline.vue": 1,
        "views/AdminMcpServersView.vue": 1,
        "views/AdminUsersView.vue": 1,
        "views/AdvancedControlView.vue": 3,
        "views/BenchmarkView.vue": 1,
        "views/BrowserAutomationView.vue": 1,
        "views/BudgetPolicies.vue": 1,
        "views/EvolutionView.vue": 2,
        "views/UsageView.vue": 3,
        "views/VisionAutomationView.vue": 2,
        "views/llc/BacklogView.vue": 1,
        "views/llc/CompanySecretsView.vue": 1,
        "views/llc/CostDashboard.vue": 2,
        "views/llc/HeartbeatMonitor.vue": 1,
        "views/llc/MembersView.vue": 1,
        "views/llc/RoutinesView.vue": 1,
        "views/secrets/LlmApiKeysView.vue": 1,
    },
    "autobot-slm-frontend/src": {
        "components/RoleManagementModal.vue": 1,
        "components/agents/ProcessMonitorTab.vue": 1,
        "components/fleet/NodeLifecyclePanel.vue": 1,
        "components/fleet/NodeServicesPanel.vue": 1,
        "components/monitoring/NodeMetricsGrid.vue": 1,
        "components/monitoring/ledger/LedgerDevLoop.vue": 1,
        "components/monitoring/ledger/LedgerLivePanel.vue": 1,
        "components/skills/ReposTab.vue": 1,
        "views/BackupsView.vue": 1,
        "views/CodeSyncView.vue": 3,
        "views/DeploymentsView.vue": 2,
        "views/ExternalAgentsView.vue": 1,
        "views/MaintenanceView.vue": 1,
        "views/OrchestrationView.vue": 5,
        "views/ReplicationView.vue": 1,
        "views/RolesView.vue": 1,
        "views/SecurityView.vue": 3,
        "views/SharedLinksView.vue": 1,
        "views/SystemUpdatesTab.vue": 2,
        "views/monitoring/AgentLedgerMonitor.vue": 1,
        "views/monitoring/LogViewer.vue": 2,
        "views/performance/AlertRulesView.vue": 1,
        "views/performance/PerformanceOverview.vue": 1,
        "views/performance/TracingView.vue": 1,
        "views/settings/SecuritySettings.vue": 1,
        "views/settings/admin/BudgetAuditView.vue": 1,
        "views/settings/admin/ConfigDefaultsSettings.vue": 1,
        "views/settings/admin/DataHygieneView.vue": 3,
        "views/settings/admin/LLMFallbacksView.vue": 2,
        "views/settings/admin/NPUWorkersSettings.vue": 1,
        "views/settings/admin/SecretsSettings.vue": 1,
        "views/settings/admin/UserManagementSettings.vue": 4,
        "views/tools/admin/AdvancedControlTool.vue": 3,
        "views/tools/admin/FileBrowserTool.vue": 1,
    },
}

# Each app's .vue population is far above these; a scan below one read the wrong tree.
MIN_VUE_FILES_SCANNED = {"autobot-frontend/src": 400, "autobot-slm-frontend/src": 100}


def scan_raw_tables(root: Path) -> tuple[dict[str, int], int]:
    """Return ({path relative to ``root``: table-opening lines}, .vue files scanned)."""
    sites: dict[str, int] = {}
    scanned = 0
    for path in sorted(root.rglob("*.vue")):
        rel = path.relative_to(root).as_posix()
        # Matched inside the scanned root, so a checkout path cannot exclude everything.
        if _EXCLUDED.search("/" + rel):
            continue
        scanned += 1
        if n := count_tables(path.read_text(encoding="utf-8")):
            sites[rel] = n
    return sites, scanned


def count_tables(text: str) -> int:
    """Raw ``<table>``-opening lines in one ``.vue`` file, closed HTML comments stripped first."""
    text = _HTML_COMMENT.sub("", text)
    return sum(1 for line in text.splitlines() if _TAG.search(line) and not _COMMENT.match(line))


def base_sites(app: str) -> dict[str, int]:
    """Per-file table counts under *app* in the BASE tree, for comparing against a legacy total pin."""
    sites = {}
    for path, text in base_tree_texts(repo_root(), app).items():
        rel = path[len(app) + 1 :]
        if path.endswith(".vue") and not _EXCLUDED.search("/" + rel) and (n := count_tables(text)):
            sites[rel] = n
    return sites


def compare_to_pin(sites: dict[str, int], pinned: dict[str, int]) -> tuple[dict, list[str]]:
    """Split a scan against its pin into (new or raised sites, stale or lowered entries)."""
    new = {k: (pinned.get(k, 0), v) for k, v in sites.items() if v > pinned.get(k, 0)}
    stale = [f"{k}: pin {v}, now {sites.get(k, 0)}" for k, v in pinned.items() if sites.get(k, 0) < v]
    return new, stale


class TestTheDetectorWorksBeforeItsOutputIsRead:
    def _w(self, root: Path, rel: str, body: str) -> None:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    def test_it_counts_opening_lines_per_file(self, tmp_path: Path) -> None:
        self._w(tmp_path, "views/A.vue", '<table class="x">\n</table>\n<table>\n</table>\n')
        self._w(tmp_path, "components/B.vue", '<table\n  class="y">\n</table>\n')
        assert scan_raw_tables(tmp_path) == ({"views/A.vue": 2, "components/B.vue": 1}, 2)

    def test_it_skips_tests_stories_comments_and_the_kit_table(self, tmp_path: Path) -> None:
        self._w(tmp_path, "views/A.test.vue", "<table>\n")
        self._w(tmp_path, "views/__tests__/B.vue", "<table>\n")
        self._w(tmp_path, "views/C.stories.vue", "<table>\n")
        self._w(
            tmp_path,
            "views/D.vue",
            '<BaseTable :rows="r" />\n// was a <table> before #17562\n<!-- <table> -->\n<tablex>\n',
        )
        assert scan_raw_tables(tmp_path) == ({}, 1)

    def test_a_table_inside_a_multi_line_html_comment_is_not_live(self, tmp_path: Path) -> None:
        self._w(tmp_path, "views/A.vue", "<!--\n  old markup\n  <table>\n  </table>\n-->\n<BaseTable />\n")
        assert scan_raw_tables(tmp_path) == ({}, 1)

    def test_a_table_after_a_closed_multi_line_comment_is_live(self, tmp_path: Path) -> None:
        self._w(tmp_path, "views/A.vue", "<!--\n  note\n-->\n<table>\n</table>\n")
        assert scan_raw_tables(tmp_path) == ({"views/A.vue": 1}, 1)

    def test_a_checkout_path_that_looks_like_a_test_excludes_nothing(self, tmp_path: Path) -> None:
        root = tmp_path / "x.test.y" / "src"
        self._w(root, "views/A.vue", "<table>\n")
        assert scan_raw_tables(root) == ({"views/A.vue": 1}, 1)

    def test_a_swap_fails_as_one_new_site_and_one_stale_entry(self) -> None:
        pinned = {"views/A.vue": 1, "views/B.vue": 1}
        now = {"views/B.vue": 1, "views/C.vue": 1}  # A converted, C gained a table: same total
        new, stale = compare_to_pin(now, pinned)
        assert new == {"views/C.vue": (0, 1)}
        assert stale == ["views/A.vue: pin 1, now 0"]


def test_neither_gui_hand_rolls_more_tables_than_pinned() -> None:
    for rel, pinned in PINS.items():
        root = repo_root() / rel
        assert root.is_dir(), f"{rel} has moved; this guard reads it by path"
        sites, scanned = scan_raw_tables(root)
        assert scanned >= MIN_VUE_FILES_SCANNED[rel], f"only {scanned} .vue files scanned under {rel}"
        new, stale = compare_to_pin(sites, pinned)
        assert not new, (
            f"NEW raw <table> sites under {rel} (path: (pinned, now)): {new} (#17562). "
            "Use BaseTable from @autobot/ui instead."
        )
        assert not stale, f"STALE pin entries under {rel}: {stale}; lower or delete them in this PR (#17562)."


def test_the_pins_were_not_raised_against_the_base() -> None:
    base = base_table(repo_root(), ("repo_tests/raw_table_ratchet_17562_test.py",), "PINS")
    for rel, pinned in PINS.items():
        old = base.get(rel)
        if old is None:
            continue
        if isinstance(old, int):  # the base pinned a total per app (before #19698): measure its tree
            assert len(pinned) <= old, f"PINS[{rel!r}] lists {len(pinned)} files, the base pinned {old} (#17562)."
            old = base_sites(rel)
        new, _ = compare_to_pin(pinned, old)
        assert not new, f"PINS[{rel!r}] rose or gained entries against the base (path: (base, now)): {new} (#17562)."
