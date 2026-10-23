# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for tools/lint/_file_size_guard.py — the shared core of the three file-size gates (#18954).

The per-language ratchet tests drive the core through the real scripts and the real
tree. These drive it directly against a fake namespace and a temporary tree, so each
rule has a contrast pair that does not depend on the repository's current contents.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

_CORE_PATH = Path(__file__).parent / "_file_size_guard.py"
_spec = importlib.util.spec_from_file_location("_file_size_guard_under_test", _CORE_PATH)
assert _spec is not None and _spec.loader is not None
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)

MAX = 3


class _Log:
    """Records what the guard logs, by level."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.infos: list[str] = []

    def error(self, fmt: str, *args) -> None:
        self.errors.append(fmt % args)

    def info(self, fmt: str, *args) -> None:
        self.infos.append(fmt % args)


def _guard(root: Path, known_large=None, tracked=None, floor=0):
    """A FileSizeGuard over a fake script namespace, bound the way the real scripts bind it."""
    ns = {
        "MAX_LINES": MAX,
        "KNOWN_LARGE": dict(known_large or {}),
        "SELF_REL": "scripts/fake.py",
        "RATCHET_REL": "repo_tests/fake_baseline.py",
        "EXCLUDED_PREFIXES": ("skip/",),
        "MIN_FAKE": floor,
        "logger": _Log(),
        "repo_root": lambda: root,
        "tracked_fake": lambda _root: list(tracked or []),
        "count_lines": core.count_lines,
        "unmeasured": core.unmeasured,
    }
    guard = core.FileSizeGuard(ns, floor_name="MIN_FAKE", tracked_name="tracked_fake", summary="ok %d %d")
    ns.update(
        _grandfathered_verdict=guard.grandfathered_verdict,
        verdict=guard.verdict,
        _vanished_entry_problem=guard.vanished_entry_problem,
        _report_unmeasured=guard.report_unmeasured,
        _scan_tracked_files=guard.scan_tracked_files,
        audit_ceilings=guard.audit_ceilings,
        _reach_breach_problem=guard.reach_breach_problem,
    )
    return guard, ns


def _write(root: Path, rel: str, lines: int) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text("x\n" * lines, encoding="utf-8")


def test_a_file_over_the_ceiling_fails_and_one_at_it_passes(tmp_path):
    guard, _ = _guard(tmp_path)
    assert f"{MAX + 1} lines (max {MAX})" in guard.verdict("new.py", MAX + 1)
    assert guard.verdict("new.py", MAX) is None  # `>` not `>=` on MAX_LINES


def test_a_grandfathered_file_that_grew_fails_and_one_at_its_size_passes(tmp_path):
    guard, _ = _guard(tmp_path, known_large={"old.py": 10})
    assert "over its recorded ceiling of 10" in guard.verdict("old.py", 11)
    assert guard.verdict("old.py", 10) is None


def test_a_grandfathered_file_under_its_ceiling_must_lower_it(tmp_path):
    guard, _ = _guard(tmp_path, known_large={"old.py": 10})
    assert "Lower the ceiling to 9" in guard.verdict("old.py", 9)


def test_a_grandfathered_file_now_compliant_must_drop_its_entry(tmp_path):
    guard, _ = _guard(tmp_path, known_large={"old.py": 10})
    assert "Delete its KNOWN_LARGE entry" in guard.verdict("old.py", MAX)  # at the limit counts as compliant
    assert "Delete its KNOWN_LARGE entry" not in guard.verdict("old.py", MAX + 1)


def test_known_large_keys_match_backslash_paths(tmp_path):
    """normalise() makes a Windows-style path find its forward-slash entry."""
    guard, _ = _guard(tmp_path, known_large={"a/old.py": 10})
    assert guard.verdict("a\\old.py", 11) is not None
    assert core.normalise("a\\b.py") == "a/b.py"


def test_count_lines_counts_and_reports_unreadable_as_none(tmp_path):
    _write(tmp_path, "ok.py", 4)
    (tmp_path / "bin.py").write_bytes(b"\xff\xfe\x00bad\n")
    assert core.count_lines(tmp_path / "ok.py") == 4
    assert core.count_lines(tmp_path / "bin.py") is None  # non-UTF-8: UnicodeDecodeError, not OSError
    assert core.count_lines(tmp_path / "missing.py") is None


def test_an_unreadable_file_is_a_finding_and_does_not_count_as_reached(tmp_path):
    _write(tmp_path, "ok.py", 1)
    (tmp_path / "bin.py").write_bytes(b"\xff\xfe\x00bad\n")
    guard, _ = _guard(tmp_path)
    reached, seen, problems = guard.scan_tracked_files(tmp_path, ["ok.py", "bin.py"])
    assert reached == 1
    assert seen == {"ok.py", "bin.py"}  # seen, so it is not also called moved-or-deleted
    assert len(problems) == 1 and problems[0].startswith("bin.py: could not be read")


def test_a_readable_compliant_tree_has_no_findings(tmp_path):
    _write(tmp_path, "ok.py", MAX)
    guard, _ = _guard(tmp_path)
    assert guard.scan_tracked_files(tmp_path, ["ok.py"]) == (1, {"ok.py"}, [])


def test_audit_ceilings_reports_an_entry_the_walk_never_reached(tmp_path):
    _write(tmp_path, "ok.py", 1)
    guard, _ = _guard(tmp_path, known_large={"gone.py": 10}, tracked=["ok.py"])
    reached, problems = guard.audit_ceilings()
    assert reached == 1
    assert len(problems) == 1 and problems[0].startswith("gone.py: not found by the tracked-file walk")


def test_audit_ceilings_finds_an_oversized_file_nobody_listed(tmp_path):
    _write(tmp_path, "big.py", MAX + 1)
    guard, _ = _guard(tmp_path, tracked=["big.py"])
    _, problems = guard.audit_ceilings()
    assert [p.split(":")[0] for p in problems] == ["big.py"]


def test_run_audit_reports_a_reach_breach_below_the_floor_but_not_at_it(tmp_path):
    _write(tmp_path, "a.py", 1)
    _write(tmp_path, "b.py", 1)
    guard, ns = _guard(tmp_path, tracked=["a.py", "b.py"], floor=3)
    assert guard.run_audit() == 1
    assert "reach check: the tree walk reached 2 tracked file(s)" in ns["logger"].errors[0]
    guard, ns = _guard(tmp_path, tracked=["a.py", "b.py"], floor=2)
    assert guard.run_audit() == 0
    assert ns["logger"].errors == [] and ns["logger"].infos == ["ok 2 0"]


def test_check_paths_skips_excluded_prefixes_and_rules_on_the_rest(tmp_path):
    _write(tmp_path, "skip/big.py", MAX + 5)
    _write(tmp_path, "big.py", MAX + 5)
    guard, ns = _guard(tmp_path)
    assert guard.check_paths(["skip/big.py"]) == 0
    assert guard.check_paths(["big.py"]) == 1
    assert ns["logger"].errors and ns["logger"].errors[0].startswith("big.py:")


def test_check_paths_treats_a_missing_staged_file_as_a_finding(tmp_path):
    guard, ns = _guard(tmp_path)
    assert guard.check_paths(["nope.py"]) == 1
    assert "never measured" in ns["logger"].errors[0]


def test_the_guard_reads_configuration_live_not_at_construction(tmp_path):
    """A patch on the namespace after construction changes the verdict (the 'live namespace' contract)."""
    guard, ns = _guard(tmp_path)
    assert guard.verdict("f.py", MAX + 1) is not None
    ns["MAX_LINES"] = MAX + 1
    assert guard.verdict("f.py", MAX + 1) is None
