# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The symbol-fork ratchet, and the boundary it depends on (#17312).

`check_symbol_forks.py` answers a question the duplication guard cannot: how
many modules bind one name at module level. These tests exist because a ratchet
baseline cannot, on its own, distinguish "the tree contains N" from "the
detector can see N" (`RATCHET_BASELINES.md`).

So they pin three different things:

  1. the boundary, so it cannot drift silently (rule 2);
  2. the population, re-derived independently and compared as a SET (rules 3-5);
  3. a positive control, so "no new clusters" cannot mean "did not look".
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

# #15925: one canonical spelling of the repo root. Re-deriving it from
# __file__ here would be a fork of exactly the kind this test's subject exists
# to find -- the guard caught it, which is the system working.
_REPO_ROOT = repo_root()
sys.path.insert(0, str(_REPO_ROOT / "tools" / "lint"))

import check_symbol_forks as detector  # noqa: E402
from _scan_helpers import scrubbed_git_env  # noqa: E402

BASELINE = json.loads((_REPO_ROOT / "repo_tests" / "symbol_fork_baseline.json").read_text(encoding="utf-8"))


def test_the_sweep_has_a_reach_floor_not_a_findings_floor() -> None:
    """A guard's vacuity floor binds to REACH, never to the number of findings.

    "0 new clusters" is meaningless if the enumeration collapsed, and a
    findings-based floor cannot tell a clean tree from a broken walk. The floor
    is on files PARSED (CodeRabbit).
    """
    swept = detector.tracked_python_files()
    assert detector.MIN_FILES_SWEPT >= 1000, "a floor this low would not detect a collapse"
    assert len(swept) >= detector.MIN_FILES_SWEPT, (
        f"the sweep reaches {len(swept)} files, under its own declared floor of "
        f"{detector.MIN_FILES_SWEPT} — either the walk broke or the floor is wrong"
    )


def test_a_collapsed_sweep_refuses_to_give_a_verdict(monkeypatch, capsys) -> None:
    """Contrast control for the floor: it must actually fire, not just exist."""
    monkeypatch.setattr(detector, "tracked_python_files", lambda: [Path("only.py")])
    assert detector.main([]) == 2, "a collapsed sweep must not return pass or fail"
    assert "enumeration collapsed" in capsys.readouterr().err


def test_a_stale_baseline_entry_fails_the_default_check(monkeypatch, capsys) -> None:
    """Shrink-only AND bidirectional: a stale entry fails as loudly as a new one.

    `--audit-baseline` only REPORTED staleness. The default path accepted it, so
    a baseline could keep an entry for duplication that was already gone — dead
    policy that silently tolerates whatever takes that name next (CodeRabbit).
    """
    real = detector.load_baseline()
    monkeypatch.setattr(detector, "load_baseline", lambda: real | {"ANameNobodyDefinesTwice"})
    assert detector.main([]) == 1, "a stale baseline entry must fail the default check"
    assert "no longer fork clusters" in capsys.readouterr().out


def test_the_baseline_states_its_boundary() -> None:
    """Rule 1: the number must carry its predicate where the reader meets it."""
    boundary = BASELINE["_boundary"]
    for required in ("MODULE-LEVEL", "test files", "FLOOR", "check_symbol_forks.py"):
        assert required in boundary, f"baseline boundary no longer states {required!r}"
    assert "BIDIRECTIONAL" in BASELINE["_contract"], "the contract must state both directions"
    assert "fails just as loudly" in BASELINE["_contract"]


def test_the_boundary_constants_match_what_the_baseline_describes() -> None:
    """Rule 2: a stated boundary that drifts silently is a stale comment."""
    boundary = BASELINE["_boundary"]
    for root in detector.ROOTS:
        assert root in boundary, f"root {root} is scanned but absent from the stated boundary"
    for part in detector.EXCLUDED_PARTS:
        assert part in boundary, f"excluded dir {part} is not declared in the baseline"
    for name in detector.EXCLUDED_NAMES:
        assert name in boundary, f"excluded name {name} is not declared in the baseline"


def test_route_handlers_are_excluded_and_the_exclusion_is_load_bearing() -> None:
    """Without this, the loudest clusters are endpoints and real forks are buried.

    The first run of this detector reported `list_providers` (10), `test_connection`
    (8) and `get_status` (7) at the top. All were FastAPI handlers in separate
    routers -- normal design, not forks.
    """
    handler = ast.parse("@router.get('/x')\ndef test_connection():\n    pass\n").body[0]
    plain = ast.parse("def test_connection():\n    pass\n").body[0]
    assert detector.is_route_handler(handler)
    assert not detector.is_route_handler(plain)


@pytest.mark.parametrize(
    "source,expected",
    [
        ("@app.post('/x')\ndef f():\n    pass\n", True),
        ("@api_router.put('/x')\ndef f():\n    pass\n", True),
        ("@functools.cache\ndef f():\n    pass\n", False),
        ("@staticmethod\ndef f():\n    pass\n", False),
    ],
)
def test_route_handler_detection_does_not_overreach(source: str, expected: bool) -> None:
    """An over-broad exclusion silently shrinks the population it is measuring."""
    assert detector.is_route_handler(ast.parse(source).body[0]) is expected


def _independent_population() -> set[str]:
    """Rule 3-5: a second derivation that replicates the PREDICATE, exemptions included.

    Deliberately ad hoc and shaped differently from the detector -- it walks
    `git ls-files` output with its own filtering and its own AST pass. It must
    reproduce every exemption, or it answers a looser question and reports the
    answer as though it were the same one.
    """
    # Scrubbed env, not the detector's helper: independence is the property
    # doing the work here, so this must not share `tracked_paths`. It must
    # still be CORRECT though -- an inherited GIT_DIR outranks `cwd=` and would
    # enumerate another worktree's index (#14896). Both copies shared that bug
    # until a pre-commit guard caught it, which is rule 5 exactly: a second
    # derivation that repeats the original's mistake measures nothing.
    out = subprocess.run(
        ["git", "ls-files", "--", "autobot-backend", "autobot-slm-backend", "autobot_shared"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(_REPO_ROOT),
        env=scrubbed_git_env(),
    ).stdout.splitlines()

    seen: dict[str, set[str]] = defaultdict(set)
    banned_dirs = {"__pycache__", "node_modules", "venv", ".venv", "migrations", "alembic"}
    banned_names = {"main", "upgrade", "downgrade", "migrate"}
    for rel in out:
        if not rel.endswith(".py"):
            continue
        parts = rel.split("/")
        base = parts[-1]
        if banned_dirs & set(parts):
            continue
        if base.endswith("_test.py") or base.startswith("test_") or "tests" in parts:
            continue
        try:
            body = ast.parse((_REPO_ROOT / rel).read_text(encoding="utf-8")).body
        except (SyntaxError, OSError):
            continue
        for stmt in body:
            if not isinstance(stmt, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if stmt.name.startswith("_") or stmt.name in banned_names:
                continue
            decorated = any(
                isinstance(getattr(d, "func", d), ast.Attribute)
                and isinstance(getattr(d, "func", d).value, ast.Name)
                and getattr(d, "func", d).value.id in {"router", "app", "api_router"}
                for d in stmt.decorator_list
            )
            if decorated:
                continue
            seen[stmt.name].add(rel)
    return {name for name, files in seen.items() if len(files) > 1}


def test_the_population_matches_an_independent_derivation() -> None:
    """Rule 4: compare SETS, not counts — two implementations can agree on a total."""
    mine = set(detector.find_clusters(detector.tracked_python_files()))
    theirs = _independent_population()
    only_detector = sorted(mine - theirs)
    only_control = sorted(theirs - mine)
    assert (
        not only_detector and not only_control
    ), f"populations disagree — detector-only: {only_detector[:10]}, control-only: {only_control[:10]}"


def test_the_detector_finds_a_planted_fork(tmp_path, monkeypatch) -> None:
    """Positive control. With the real tree clean of NEW clusters, a pass proves nothing."""
    # Bodies must differ in STATEMENT COUNT, not merely in text: `drifted` is a
    # statement-count heuristic, and an earlier fixture used `pass` vs `x = 1`
    # -- one statement each -- so it asserted drift against a detector that
    # could not possibly report it.
    (tmp_path / "a.py").write_text("class Widget:\n    pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("class Widget:\n    x = 1\n    y = 2\n    z = 3\n", encoding="utf-8")
    monkeypatch.setattr(detector, "_REPO_ROOT", tmp_path)
    clusters = detector.find_clusters([Path("a.py"), Path("b.py")])
    assert "Widget" in clusters, "the detector cannot see a two-file fork it is pointed at"
    assert clusters["Widget"].drifted, "differing bodies should read as drifted"


def test_a_single_definition_is_not_a_cluster(tmp_path, monkeypatch) -> None:
    """Negative control: the detector must not report a name defined once."""
    (tmp_path / "only.py").write_text("class Solo:\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(detector, "_REPO_ROOT", tmp_path)
    assert detector.find_clusters([Path("only.py")]) == {}


def test_no_new_fork_clusters() -> None:
    """The ratchet itself. A new name here means a new concept fork landed."""
    current = set(detector.find_clusters(detector.tracked_python_files()))
    new = sorted(current - set(BASELINE["clusters"]))
    assert not new, (
        f"{len(new)} new fork cluster(s): {new[:10]}. "
        "Give the new concept its own name, or extend the existing definition (#17312)."
    )
