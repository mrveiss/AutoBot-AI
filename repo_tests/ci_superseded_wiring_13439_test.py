# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#13439 — the supersession selector must be REACHED, not merely defined.

``superseded_stuck_runs`` shipped complete, with six unit tests, and
``git grep superseded_stuck_runs`` returned the definition and its test and
nothing else. Correct code that nothing calls protects nothing, and the symptom
it names — a ``queued`` predecessor holding a concurrency group that
``cancel-in-progress`` can never reap — stayed invisible to the one probe whose
job is "work is queued and nothing is moving".

Two independent claims are asserted here, because either alone is satisfiable
without the other being true:

* **Behaviour** — ``check_runner_starvation`` now reports a superseded
  predecessor and treats it as a fault, on a fixture where it previously
  returned 0 and said the pool was keeping up.
* **Reachability** — the selector appears in CALL position, inside the
  function the CLI dispatches to, read from the **AST**.

The AST half is not fussiness. A guard that greps for ``superseded_stuck_runs``
is satisfied by a comment, a docstring or a string literal carrying that name —
which is exactly the state this issue describes, since the selector's own
docstring is full of the word. :data:`PROSE_ONLY_FIXTURE` is the contrast case:
a module where the name appears three times and is called zero times. A grep
passes it. This guard must not.
"""

from __future__ import annotations

import ast
import importlib.util
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Set

import pytest
from repo_tests._paths import repo_root

WATCHDOG_PATH = repo_root() / "pipeline-scripts" / "ci_dispatch_watchdog.py"

REPO = "mrveiss/AutoBot-AI"
SELECTOR = "superseded_stuck_runs"
REPORTER = "report_superseded_stuck_runs"
ENTRY = "check_runner_starvation"


# ---------------------------------------------------------------------------
# AST reachability — the string "superseded_stuck_runs" is not the evidence
# ---------------------------------------------------------------------------


def _called_names(tree: ast.AST) -> Set[str]:
    """Every name used in CALL position anywhere under *tree*.

    Deliberately an AST walk rather than a text search. A comment, a docstring
    and a string literal are all invisible to ``ast``, which is the whole point:
    the question is whether the selector RUNS, and only a ``Call`` node answers
    it.
    """
    called: Set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            called.add(func.id)
        elif isinstance(func, ast.Attribute):
            called.add(func.attr)
    return called


def _function(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node  # type: ignore[return-value]
    raise AssertionError(f"{name} is not defined in {WATCHDOG_PATH.name}")


def _referenced_names(tree: ast.AST) -> Set[str]:
    """Every bare name loaded under *tree* — a call, or a function passed along."""
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


@pytest.fixture(scope="module")
def watchdog_tree() -> ast.Module:
    return ast.parse(WATCHDOG_PATH.read_text(encoding="utf-8"))


# A module that mentions the selector three times and calls it zero times.
# Assembled as a fixture rather than described, so the contrast is executable.
PROSE_ONLY_FIXTURE = '''
"""The sweep consults superseded_stuck_runs on every pass."""

# superseded_stuck_runs(runs, now, repo, grace, budget) -- wired in #13439.

WHY = "superseded_stuck_runs selects the predecessors a human must force-cancel"


def check_runner_starvation(api, config):
    return 0
'''

# The positive control, in the one shape the detector must recognise.
REAL_CALL_FIXTURE = """
def check_runner_starvation(api, config):
    return superseded_stuck_runs(api.runs(), None, "r", 10, 20)
"""


def test_the_detector_finds_a_real_call() -> None:
    """Known positive: without this, every assertion below is meaningless."""
    assert SELECTOR in _called_names(ast.parse(REAL_CALL_FIXTURE))


def test_a_name_that_appears_only_in_prose_is_not_a_call() -> None:
    """The trap: a grep passes this module, and it calls nothing.

    This is the mutation the behaviour tests are checked against — replacing the
    production call with a comment that mentions it must turn this guard red.
    """
    assert PROSE_ONLY_FIXTURE.count(SELECTOR) == 3, "fixture must carry the name in docstring, comment and literal"
    assert SELECTOR not in _called_names(ast.parse(PROSE_ONLY_FIXTURE))


def test_the_selector_is_called_from_the_reporter(watchdog_tree: ast.Module) -> None:
    """#13439's defect, stated as a property: the selector has a call site."""
    assert SELECTOR in _called_names(_function(watchdog_tree, REPORTER))


def test_the_reporter_is_called_from_the_cli_entry_point(watchdog_tree: ast.Module) -> None:
    """A call site in the wrong place is worse than none — it looks finished.

    ``check_runner_starvation`` is the function ``--check runner-starvation``
    dispatches to, so a call inside it is a call that actually runs.
    """
    assert REPORTER in _called_names(_function(watchdog_tree, ENTRY))


# `main` that names the entry point without ever invoking it. The real `main`
# does `return check_runner_starvation(api, config)`, so the strict assertion
# below is reachable -- this fixture proves the assertion can FAIL.
REFERENCE_ONLY_FIXTURE = """
def main():
    handler = check_runner_starvation
    print(check_runner_starvation.__name__)
    return 0
"""


def test_the_cli_dispatches_to_that_entry_point(watchdog_tree: ast.Module) -> None:
    """Closes the chain: argv -> main -> check_runner_starvation -> selector.

    CALLED, not merely referenced (CodeRabbit). `_referenced_names` matches any
    bare name load, so a `main` that only assigned or printed the entry point
    satisfied it while the CLI never ran the check -- a wiring pin that passes
    when the wiring is gone.
    """
    assert ENTRY in _called_names(_function(watchdog_tree, "main"))


def test_a_main_that_only_mentions_the_entry_point_fails_the_pin() -> None:
    """Contrast control for the assertion above, per the detector-pair rule."""
    fixture_main = _function(ast.parse(REFERENCE_ONLY_FIXTURE), "main")
    assert ENTRY in _referenced_names(fixture_main), "fixture should still MENTION it"
    assert ENTRY not in _called_names(fixture_main), (
        "a reference-only main must not satisfy the call assertion — otherwise "
        "the pin cannot tell a wired CLI from an unwired one"
    )


# ---------------------------------------------------------------------------
# Behaviour — the report reaches a verdict, and the verdict changed
# ---------------------------------------------------------------------------


def _load_watchdog():
    spec = importlib.util.spec_from_file_location("ci_dispatch_watchdog", WATCHDOG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def watchdog():
    return _load_watchdog()


# Read against the real clock, as `check_runner_starvation` does.
def _ago(minutes: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


# 20 minutes sits deliberately between the two thresholds: past the 10m
# supersession grace window, short of the 45m starvation threshold. So the
# fixture isolates the NEW verdict — nothing here is starved, and before this
# wiring the probe called it a healthy pool.
PREDECESSOR_AGE_MINUTES = 20

_STARVATION_CONFIG: Dict[str, Any] = {
    "stall_minutes": 45,
    "max_job_lookups": 5,
    "job_overdue_minutes": 45,
}


def _group_member(run_number: int, minutes_ago: float, **overrides: Any) -> Dict[str, Any]:
    run = {
        "id": 5000 + run_number,
        "run_number": run_number,
        "name": "Frontend Testing Suite",
        "workflow_id": 77,
        "head_branch": "main",
        "event": "push",
        "status": "queued",
        "conclusion": None,
        "created_at": _ago(minutes_ago),
        "head_repository": {"full_name": REPO},
        "html_url": f"https://example.invalid/runs/{5000 + run_number}",
    }
    run.update(overrides)
    return run


def _api(by_status: Dict[str, List[Dict[str, Any]]], jobs: Iterable[Dict[str, Any]] = ()):
    class _Api:
        repository = REPO

        def recent_runs(self, per_page: int = 100, run_status: str = "") -> List[Dict[str, Any]]:
            return list(by_status.get(run_status, []))

        def run_jobs(self, run_id: int) -> List[Dict[str, Any]]:
            return list(jobs)

    return _Api()


def test_a_superseded_predecessor_is_reported_as_a_fault(watchdog, capsys) -> None:
    """The regression. Before #13439's wiring this returned 0 and said "keeping up".

    Neither run is starved — both are younger than ``stall_minutes`` — so every
    pre-existing signal in this probe is green. The only thing wrong with the
    repository is that run #1 is queued behind nothing, holding its concurrency
    group, while run #2 can never start.
    """
    predecessor = _group_member(1, PREDECESSOR_AGE_MINUTES)
    newest = _group_member(2, 1)

    verdict = watchdog.check_runner_starvation(_api({"queued": [predecessor, newest]}), _STARVATION_CONFIG)

    out = capsys.readouterr().out
    assert verdict == 1, out
    assert "1 workflow run(s) are superseded predecessors" in out
    assert "force-cancel" in out
    assert str(predecessor["html_url"]) in out
    assert str(newest["html_url"]) not in out, "the newest run in a group is never named for cancellation"


def test_the_scan_says_so_when_it_finds_nothing(watchdog, capsys) -> None:
    """`nothing found` and `did not look` must not print the same thing.

    The scan line is emitted on every sweep and carries every selector that
    produced the number — statuses, grace window, fork restriction, grouping —
    so a zero can be read as a measurement rather than as silence.
    """
    lone = _group_member(1, PREDECESSOR_AGE_MINUTES)

    verdict = watchdog.check_runner_starvation(_api({"queued": [lone]}), _STARVATION_CONFIG)

    out = capsys.readouterr().out
    assert verdict == 0, out
    assert "Supersession scan: 0 stuck predecessor(s) among 1 live run(s)" in out
    assert "statuses queued/pending/in_progress" in out
    assert "grace >=10m" in out
    assert f"heads in {REPO} only" in out


def test_the_population_includes_runs_the_queued_page_cannot_see(watchdog, capsys) -> None:
    """A `queued`-only population would make the newest QUEUED run look newest.

    Here the real newest member is ``in_progress`` and therefore absent from the
    ``status=queued`` listing. With only that listing, run #2 would be taken for
    the head of its group and excluded from selection, and the genuine stuck
    predecessor #1 would be the only hit — under-reporting #2 silently.
    """
    first = _group_member(1, PREDECESSOR_AGE_MINUTES + 5)
    second = _group_member(2, PREDECESSOR_AGE_MINUTES)
    working = _group_member(3, 2, status="in_progress")

    verdict = watchdog.check_runner_starvation(
        _api({"queued": [first, second], "in_progress": [working]}),
        _STARVATION_CONFIG,
    )

    out = capsys.readouterr().out
    assert verdict == 1, out
    assert "2 stuck predecessor(s) among 3 live run(s)" in out
    assert str(working["html_url"]) not in out
