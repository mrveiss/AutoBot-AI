# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""scripts/repin_reach_floors.py rewrites exactly the stale floor it measured, and nothing else (#19282).

Re-pinning was a hand edit per floor, every train. The script measures each declaration and
rewrites its literal ``floor=`` mid-window; these tests pin the rewrite itself on fixture source:
the right call, the right line, the standard comment, an expression floor left for a human.
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess

from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

_SPEC = importlib.util.spec_from_file_location("repin_reach_floors", repo_root() / "scripts" / "repin_reach_floors.py")
repin = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(repin)

_SOURCE = """\
OTHER = declare(
    "other-scan",
    discover=_d,
    floor=10,  # untouched
    growth=4,
)
REACH = declare(
    "the-scan",
    discover=_d,
    floor=100,  # mid-window: population 110, window (90, 110)
    growth=20,
)
"""


def test_the_named_declarations_literal_floor_is_rewritten_mid_window() -> None:
    new, status = repin.repin_source(_SOURCE, "the-scan", mid=140, count=150, low=130, high=150)
    assert status == "re-pinned"
    assert "    floor=140,  # mid-window: population 150, window (130, 150)\n" in new
    assert "    floor=10,  # untouched\n" in new, "another declaration's floor was touched"
    assert new.count("floor=") == 2


def test_an_expression_floor_is_left_for_a_human() -> None:
    source = 'R = declare(\n    "x",\n    discover=_d,\n    floor=_FLOOR,\n    growth=4,\n)\n'
    new, status = repin.repin_source(source, "x", mid=5, count=9, low=1, high=9)
    assert new == source and "not a literal integer" in status


def test_a_missing_declaration_is_reported_not_guessed() -> None:
    new, status = repin.repin_source(_SOURCE, "no-such-scan", mid=1, count=1, low=1, high=1)
    assert new == _SOURCE and status == "declare() call not found"


# Split so the reach sweep's declare-call grep (reach_declarations_test) does not read
# this planted source as a production declaration it never imported.
_ONE_LINE_CALL = "R = decl" + "are"


def test_one_line_calls_underscored_and_spaced_floors_are_found() -> None:
    """27's review: located through the AST, not text, so each layout works."""
    for source in (
        _ONE_LINE_CALL + '("x", discover=_d, floor=1_000, growth=40)\n',
        _ONE_LINE_CALL + '("x", discover=_d, floor = 1000, growth=40)\n',
        'R = declare(\n    "x", discover=_d,\n    floor=1000)\n',
    ):
        new, status = repin.repin_source(source, "x", mid=1020, count=1040, low=1000, high=1040)
        assert status == "re-pinned", source
        assert "1020" in new and "1000," not in new.replace("(1000, 1040)", ""), new


def test_non_ascii_before_the_floor_and_a_form_feed_line_break_are_handled() -> None:
    """CodeRabbit on #19364: ast columns are UTF-8 bytes, and str.splitlines breaks on \\f where ast does not."""
    source = "# \x0c\n" + _ONE_LINE_CALL + '("x", what="déjà vu", floor=1000, growth=40)\n'
    new, status = repin.repin_source(source, "x", mid=1020, count=1040, low=1000, high=1040)
    assert status == "re-pinned"
    assert new.startswith("# \x0c\n" + _ONE_LINE_CALL + '("x", what="déjà vu", floor=1020, growth=40)'), new
    ast.parse(new)


def test_a_hand_written_comment_is_kept_and_a_mid_window_one_refreshed() -> None:
    kept, _ = repin.repin_source(
        'R = declare(\n    "x",\n    floor=50,  # see #123 for why\n)\n', "x", mid=60, count=70, low=50, high=70
    )
    assert "    floor=60,  # see #123 for why\n" in kept


class _Reach:
    """A stand-in declaration for main()'s exit codes."""

    def __init__(self, name: str, stale: bool) -> None:
        self.name, self.min_fraction, self._stale = name, None, stale

    def staleness(self, root):
        return f"[{self.name}] floor is stale" if self._stale else None


def _main(monkeypatch, declarations, failures, *argv) -> int:
    monkeypatch.setattr(repin, "_declarations", lambda: (declarations, failures))
    monkeypatch.setattr(repin, "_repin", lambda r: f"PIN   {r.name}")
    return repin.main(list(argv))


def test_main_exit_codes(monkeypatch, capsys) -> None:
    assert _main(monkeypatch, [_Reach("a", False)], {}, "--check") == 0
    assert _main(monkeypatch, [_Reach("a", True)], {}, "--check") == 1
    assert _main(monkeypatch, [_Reach("a", True)], {}) == 0, "write mode re-pinned everything stale"


def test_an_import_failure_is_never_a_clean_result(monkeypatch, capsys) -> None:
    """27's review: a guard that could not import was not measured -- exit 2, in both modes."""
    for argv in (("--check",), ()):
        assert _main(monkeypatch, [_Reach("a", False)], {"broken_test": "ImportError: x"}, *argv) == 2
    assert "No stale reach floors." not in capsys.readouterr().out


def test_ci_enforces_staleness_on_merge_trains() -> None:
    """The one place staleness fails must stay wired: the reach-running job sets the audit on train-*."""
    import yaml
    from repo_tests._reach import REACH_AUDIT_ENV

    steps = yaml.safe_load((repo_root() / ".github/workflows/ci.yml").read_text(encoding="utf-8"))["jobs"][
        "python-shard"
    ]["steps"]
    wired = [
        s
        for s in steps
        if "startsWith(github.head_ref, 'train-')" in str(s.get("if", ""))
        and f"{REACH_AUDIT_ENV}=1" in str(s.get("run", ""))
    ]
    assert wired, f"ci.yml's python-shard job no longer sets {REACH_AUDIT_ENV}=1 on train-* heads"


# ---------------------------------------- #20050: a floor stale on the base, a branch that did not cause it


def _base_stale(monkeypatch, tmp_path, changed):
    guard = tmp_path / "repo_tests" / "g_test.py"
    guard.parent.mkdir()
    guard.write_text("", encoding="utf-8")
    monkeypatch.setattr(repin, "_ROOT", tmp_path)
    monkeypatch.setattr(repin, "_source_file", lambda _r: guard)
    monkeypatch.setattr(repin, "_changed_files", lambda _ref: changed)
    return _main(monkeypatch, [_Reach("a", True)], {}, "--check", "--changed-since", "origin/main")


def test_a_floor_stale_from_the_base_does_not_fail_a_branch_that_left_it_alone(monkeypatch, tmp_path, capsys) -> None:
    assert _base_stale(monkeypatch, tmp_path, {"docs/x.md"}) == 0
    assert capsys.readouterr().out.startswith("BASE-STALE a:")


def test_a_branch_that_touched_the_guard_still_answers_for_its_floor(monkeypatch, tmp_path, capsys) -> None:
    assert _base_stale(monkeypatch, tmp_path, {"repo_tests/g_test.py"}) == 1
    assert capsys.readouterr().out.startswith("STALE a:")


def test_when_git_cannot_say_what_changed_the_floor_still_blocks(monkeypatch, tmp_path, capsys) -> None:
    assert _base_stale(monkeypatch, tmp_path, None) == 1
    assert capsys.readouterr().out.startswith("STALE a:")


def test_without_the_option_every_stale_floor_still_fails(monkeypatch, capsys) -> None:
    assert _main(monkeypatch, [_Reach("a", True)], {}, "--check") == 1
    assert capsys.readouterr().out.startswith("STALE a:")


def test_changed_files_reads_the_branchs_own_diff_from_real_git(monkeypatch, tmp_path) -> None:
    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            env=scrubbed_git_env(),
        )

    git("init", "-q", "-b", "main")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    git("add", "."), git("commit", "-qm", "one")
    git("switch", "-qc", "branch")
    (tmp_path / "mine.txt").write_text("b", encoding="utf-8")
    git("add", "."), git("commit", "-qm", "two")
    git("switch", "-q", "main")
    (tmp_path / "main_only.txt").write_text("c", encoding="utf-8")
    git("add", "."), git("commit", "-qm", "three")
    git("switch", "-q", "branch")
    monkeypatch.setattr(repin, "_ROOT", tmp_path)
    assert repin._changed_files("main") == {"mine.txt"}
    assert repin._changed_files("no-such-ref") is None


def test_an_import_failure_names_its_reason(monkeypatch, capsys) -> None:
    _main(monkeypatch, [], {"g": "Traceback\nModuleNotFoundError: No module named 'x'"}, "--check")
    err = capsys.readouterr().err
    assert "g: ModuleNotFoundError: No module named 'x'" in err and "train audit" in err
