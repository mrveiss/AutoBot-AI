# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Symbol forks reach codebase analytics through the CI detector (#18067).

The dashboard count and ``tools/lint/check_symbol_forks.py``'s count must be
one number because they are one function (``autobot_shared.symbol_forks``).
Pinned three ways: the real tree agrees, a planted fixture shows the pass finds
a fork and ignores a non-fork, and a pass that could not look says so instead
of reporting zero.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from api.codebase_analytics import cross_file_analysis as xfa
from api.codebase_analytics.fork_findings import SYMBOL_FORK_PROBLEM_TYPE, run_fork_pass
from api.codebase_analytics.type_coverage import problem_type_coverage
from autobot_shared.isolated_git import isolated_git_env

_REPO = repo_root()
_CLI = _REPO / "tools" / "lint" / "check_symbol_forks.py"


def _git_tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=isolated_git_env())
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, env=isolated_git_env())
    return root


def _planted(root: Path) -> Path:
    """One real fork (Shared), one single-definition name, and two by-design repeats."""
    return _git_tree(
        root,
        {
            "autobot_shared/a.py": "def Shared():\n    return 1\n\ndef only_here():\n    return 2\n",
            "autobot-backend/b.py": "def Shared():\n    return 3\n",
            # Route handlers and test files repeat names by design: excluded.
            "autobot-backend/api/x.py": "@router.get('/')\ndef handler():\n    pass\n",
            "autobot-backend/api/y.py": "@router.get('/')\ndef handler():\n    pass\n",
            "autobot-backend/p_test.py": "def Shared():\n    pass\n",
        },
    )


def _ci_clusters() -> tuple[set[str], int]:
    """The CI script's own answer, run as the CI runs it: a child process.

    Not imported: the script is a lint tool outside the backend's package
    layout, and importing it here would drag its path handling into every
    process that collects this file.
    """
    proc = subprocess.run(
        [sys.executable, "-I", str(_CLI), "--report", "--limit", "100000"],
        cwd=_REPO,
        env=isolated_git_env(),
        capture_output=True,
        text=True,
        check=True,
    )
    names = set(re.findall(r"^(\w+)  \(", proc.stdout, flags=re.M))
    total = int(re.search(r"^(\d+) fork clusters", proc.stdout, flags=re.M).group(1))
    return names, total


def test_dashboard_and_ci_detector_agree_on_the_real_tree():
    outcome = run_fork_pass(str(_REPO))
    ci_names, ci_total = _ci_clusters()
    assert outcome.ran, outcome.reason
    assert outcome.clusters == ci_total == len(ci_names) > 0
    assert len(outcome.problems) == ci_total, "one problem row per fork cluster"
    named = {p["description"].split("'")[1] for p in outcome.problems}
    assert named == ci_names, "same clusters, not merely the same count"
    assert {p["type"] for p in outcome.problems} == {SYMBOL_FORK_PROBLEM_TYPE}


def test_a_planted_fork_is_found_and_the_non_forks_are_not(tmp_path):
    outcome = run_fork_pass(str(_planted(tmp_path)))
    assert outcome.ran and outcome.clusters == 1
    assert "'Shared'" in outcome.problems[0]["description"]
    assert "handler" not in outcome.problems[0]["description"]


def test_a_tree_git_cannot_list_did_not_run_rather_than_found_nothing(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    pass\n", encoding="utf-8")
    outcome = run_fork_pass(str(tmp_path))
    assert outcome.ran is False and outcome.reason
    assert outcome.problems == [] and outcome.clusters == 0


def test_a_tree_where_nothing_parses_did_not_run(tmp_path):
    _git_tree(tmp_path, {"autobot_shared/broken.py": "def (:\n"})
    outcome = run_fork_pass(str(tmp_path))
    assert outcome.ran is False, "zero parsed files must not read as zero forks"
    assert "parsed 0" in (outcome.reason or "")


@pytest.mark.asyncio
async def test_the_cross_file_pass_persists_fork_rows_and_reports_what_ran(tmp_path, monkeypatch):
    persisted: list = []

    async def fake_persist(problems, source_id=None, progress_callback=None):
        persisted.extend(problems)
        return len(problems)

    monkeypatch.setattr(xfa, "_persist_to_chromadb", fake_persist)
    outcome = await xfa.analyze_cross_file_with_outcome(str(_planted(tmp_path)), exclude_patterns=["__pycache__"])
    assert outcome.ran and outcome.forks is not None and outcome.forks.ran
    assert outcome.by_type.get(SYMBOL_FORK_PROBLEM_TYPE) == 1
    assert [p["type"] for p in persisted].count(SYMBOL_FORK_PROBLEM_TYPE) == 1


@pytest.mark.asyncio
async def test_a_missing_root_is_not_ran_with_a_reason(tmp_path):
    outcome = await xfa.analyze_cross_file_with_outcome(str(tmp_path / "absent"))
    assert outcome.ran is False and "does not exist" in outcome.reason
    assert await xfa.run_cross_file_analysis(str(tmp_path / "absent")) == 0


@pytest.mark.asyncio
async def test_rules_that_raise_are_not_ran_not_zero_findings(tmp_path, monkeypatch):
    class _Boom:
        async def analyze_cross_file_only(self, **_kwargs):
            raise RuntimeError("simulated")

    import code_analysis.src.anti_pattern_detector as apd

    monkeypatch.setattr(apd, "AntiPatternDetector", lambda: _Boom())
    outcome = await xfa.analyze_cross_file_with_outcome(str(tmp_path))
    assert outcome.ran is False and "simulated" in outcome.reason


def test_type_coverage_states_emitting_and_silent_declared_types_as_numbers():
    cov = problem_type_coverage(
        {"code_smell_duplicate_enum": 3, "code_smell_symbol_fork": 0, "debug_code": 9, "code_smell_god_class": 1}
    )
    assert cov.emitted_nonzero == 3
    assert "code_smell_symbol_fork" in cov.declared_silent, "a zero count is silent, not emitting"
    assert "code_smell_duplicate_enum" not in cov.declared_silent
    assert cov.emitted_undeclared == ("debug_code",)
    assert cov.declared_emitted == 2 and cov.emitted_nonzero == 3
    assert cov.declared == cov.declared_emitted + len(cov.declared_silent)


_TWIN_CLASSES = """
class Alpha:
    def one(self): ...
    def two(self): ...
    def three(self): ...

class Beta:
    def one(self): ...
    def two(self): ...
    def three(self): ...

class Gamma:
    def unrelated(self): ...
    def other(self): ...
    def more(self): ...
"""


def _abstraction_rows(tmp_path: Path, source: str) -> list:
    from code_intelligence.anti_pattern_detection.analyzer import AntiPatternSuiteAnalyzer

    target = tmp_path / "mod.py"
    target.write_text(source, encoding="utf-8")
    result = AntiPatternSuiteAnalyzer().analyze_file(str(target))
    return [p for p in result["anti_patterns"] if p["pattern_type"] == "duplicate_abstraction"]


def test_duplicate_abstraction_is_emitted_by_the_per_file_analysis(tmp_path):
    """Verdict for `duplicate_abstraction`: its detector was never called (#18067).

    `DispensableDetector.detect_duplicate_classes` existed and no analyzer ran
    it, so the type could not emit a row however many twins the tree held.
    Known answer: Alpha/Beta are twins and are reported; Gamma shares nothing
    and must not be.
    """
    rows = _abstraction_rows(tmp_path, _TWIN_CLASSES)
    assert len(rows) == 1
    assert "Alpha" in rows[0]["entity_name"] and "Beta" in rows[0]["entity_name"]
    assert "Gamma" not in rows[0]["entity_name"]


def test_distinct_classes_produce_no_duplicate_abstraction(tmp_path):
    source = _TWIN_CLASSES.replace(
        "class Beta:\n    def one(self): ...\n    def two(self): ...\n    def three(self): ...\n", ""
    )
    assert "class Beta" not in source
    assert _abstraction_rows(tmp_path, source) == []
