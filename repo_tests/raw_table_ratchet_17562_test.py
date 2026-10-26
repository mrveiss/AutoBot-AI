# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Data tables in both GUIs move onto the kit's BaseTable (#17562).

**The boundary.** The count is the number of ``.vue`` files under each app's ``src`` that
hold a raw ``<table`` tag (then whitespace, ``>`` or line end) on a line that is not a ``//``
or ``<!--`` comment, excluding tests, specs and stories. Measured on 8c511bf0d6: 36 in ``autobot-frontend``, 34 in ``autobot-slm-frontend``.
``BaseTable`` (``@autobot/ui``) gives one header style, sorting, the empty state, the loading
state and the accessible caption, so a hand-rolled table re-implements each of them.

**What may stay.** A key/value layout (``ChartCell``, ``EntityDetail``) is not a data table
and may keep ``<table>``. The guard has no by-name exemption: such files stay inside the pin.

**One number per app, not a per-file table.** A per-file pin would list frontend paths in a
``repo_tests`` module, and ``python_filter_covers_its_guards_test.py`` would then require the
python suite on every frontend change (see ``_hardcoded_colour_baseline.py``). The pins are
down-only against the base (#19283) and exact: a PR that converts a table lowers its app's
pin by the files it cleared.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_table

_EXCLUDED = re.compile(r"(\.test\.|\.spec\.|\.stories\.|/__tests__/)")
_TAG = re.compile(r"<table(?:[\s>]|$)")
_COMMENT = re.compile(r"^\s*(//|<!--)")

# 36 / 34 measured on 8c511bf0d6; 30 after the first batch (ErrorMonitoringView,
# CompanyPortabilityView, AgentLedgerView, CompanyDashboardWidget, CodeQualityDashboard,
# CapabilityAuditLog, #17562). Lower a pin by exactly what a PR converts.
PINS = {"autobot-frontend/src": 30, "autobot-slm-frontend/src": 34}

# Each app's .vue population is far above these; a scan below one read the wrong tree.
MIN_VUE_FILES_SCANNED = {"autobot-frontend/src": 400, "autobot-slm-frontend/src": 100}


def scan_raw_tables(root: Path) -> tuple[int, int]:
    """Return (files holding a raw table, .vue files scanned) under ``root``."""
    hits = scanned = 0
    for path in sorted(root.rglob("*.vue")):
        # Matched inside the scanned root, so a checkout path cannot exclude everything.
        if _EXCLUDED.search("/" + path.relative_to(root).as_posix()):
            continue
        scanned += 1
        lines = path.read_text(encoding="utf-8").splitlines()
        hits += any(_TAG.search(line) and not _COMMENT.match(line) for line in lines)
    return hits, scanned


class TestTheDetectorWorksBeforeItsOutputIsRead:
    def _w(self, root: Path, rel: str, body: str) -> None:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    def test_it_counts_files_not_tags(self, tmp_path: Path) -> None:
        self._w(tmp_path, "views/A.vue", '<table class="x">\n</table>\n<table>\n</table>\n')
        self._w(tmp_path, "components/B.vue", '<table\n  class="y">\n</table>\n')
        assert scan_raw_tables(tmp_path) == (2, 2)

    def test_it_skips_tests_stories_comments_and_the_kit_table(self, tmp_path: Path) -> None:
        self._w(tmp_path, "views/A.test.vue", "<table>\n")
        self._w(tmp_path, "views/__tests__/B.vue", "<table>\n")
        self._w(tmp_path, "views/C.stories.vue", "<table>\n")
        self._w(
            tmp_path,
            "views/D.vue",
            '<BaseTable :rows="r" />\n// was a <table> before #17562\n<!-- <table> -->\n<tablex>\n',
        )
        assert scan_raw_tables(tmp_path) == (0, 1)

    def test_a_checkout_path_that_looks_like_a_test_excludes_nothing(self, tmp_path: Path) -> None:
        root = tmp_path / "x.test.y" / "src"
        self._w(root, "views/A.vue", "<table>\n")
        assert scan_raw_tables(root) == (1, 1)


def test_neither_gui_hand_rolls_more_tables_than_pinned() -> None:
    for rel, pinned in PINS.items():
        root = repo_root() / rel
        assert root.is_dir(), f"{rel} has moved; this guard reads it by path"
        now, scanned = scan_raw_tables(root)
        assert scanned >= MIN_VUE_FILES_SCANNED[rel], f"only {scanned} .vue files scanned under {rel}"
        assert now <= pinned, (
            f"{now} .vue files under {rel} hold a raw <table>, pin allows {pinned} (#17562). "
            "Use BaseTable from @autobot/ui instead."
        )
        assert now == pinned, f"{now} raw-table files under {rel}, pin says {pinned}: lower PINS to {now} (#17562)."


def test_the_pins_were_not_raised_against_the_base() -> None:
    base = base_table(repo_root(), ("repo_tests/raw_table_ratchet_17562_test.py",), "PINS")
    for rel, pinned in PINS.items():
        if rel in base:
            assert pinned <= base[rel], f"PINS[{rel!r}] rose from {base[rel]} to {pinned} (#17562); pins only go down."
