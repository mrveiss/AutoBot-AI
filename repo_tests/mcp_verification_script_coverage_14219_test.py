# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The checks two removed root scripts performed still run somewhere (#14219).

`check_syntax.py` and `check_mcp_imports.py` sat at the repository root with
zero inbound references — no workflow, no pre-commit entry, no caller. Both were
tracked mode 100644 despite carrying a `#!` line, so even an invocation by path
would have needed an explicit interpreter. They had never run.

An unreferenced checker is normally unfinished wiring rather than debris, and
the rule is to finish it. These two are the other case: every check they
described is already performed, repo-wide and blocking, by something that does
run. Writing them into `tools/lint/` would have forked a check rather than
completing one.

This module is the receipt. Each removal is only safe while its covering check
exists, and a covering check can be narrowed, renamed or deleted by a change
that has no idea it is load-bearing — the failure mode where a citation quietly
stops pointing at anything. So the citations are asserted, not merely written
down in a pull request that nobody will read again:

* `check_syntax.py` byte-compiled four named files. **`black --check` alone**
  guarantees that coverage. A linter has to parse Python before it can judge it,
  so a syntax error fails black with exit 123, and `.github/workflows/code-quality.yml`
  runs it over `autobot-backend/` and `autobot_shared/` with no exclusions.

  `flake8` does **not** cover three of the four. Its `.flake8` `exclude =` list
  carries the bare name `monitoring`, and flake8 prunes a bare name at *any*
  depth rather than only at the repository root, so everything under
  `autobot_shared/monitoring/` is skipped silently — in CI and in pre-commit
  alike, since both read the same config. The first draft of this module claimed
  otherwise and asserted only that the tool name and the tree name appear on one
  line of the workflow, which is true and proves nothing. The wider problem
  (1328 of 4938 tracked `.py` files pruned this way, including three production
  packages named `monitoring`) is #14419 and is not fixed here.

  So the assertions below measure *reach*: for each file, which linters actually
  arrive at it after their own exclude rules are applied. Reach must be
  non-empty, and it must match what was measured — the second half is what fails
  if black's excludes are ever "aligned with flake8's for consistency", which
  would silently remove the only coverage these three files have.

* `check_mcp_imports.py` imported three modules and read one attribute from
  each. Every one of those attributes is imported or patched by a colocated
  test that pytest collects, which both imports the module and resolves the
  attribute — the same question, asked where it is answered on every run.
"""

from __future__ import annotations

import ast
import configparser
import fnmatch
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_WORKFLOW = _REPO / ".github" / "workflows" / "code-quality.yml"

#: The files `check_syntax.py` byte-compiled. Something must still parse each.
_GUARDED_FILES = (
    "autobot_shared/monitoring/metrics/mcp_worker.py",
    "autobot_shared/monitoring/metrics/__init__.py",
    "autobot_shared/monitoring/prometheus_metrics.py",
    "autobot-backend/services/mcp_isolated_runtime.py",
)

#: Which CI linters reach each file, as measured rather than as assumed. black
#: reaches all four; flake8 reaches only the last, because `.flake8` prunes the
#: bare component `monitoring` at any depth (#14419). Update this map when that
#: is fixed — a change here is a real change in what guards these files.
_MEASURED_REACH: dict[str, set[str]] = {
    "autobot_shared/monitoring/metrics/mcp_worker.py": {"black"},
    "autobot_shared/monitoring/metrics/__init__.py": {"black"},
    "autobot_shared/monitoring/prometheus_metrics.py": {"black"},
    "autobot-backend/services/mcp_isolated_runtime.py": {"black", "flake8"},
}

#: The attribute checks, each paired with the collected test that performs it.
#: `(dotted module, attribute, covering test file)`.
_IMPORT_CHECKS = (
    (
        "autobot_shared.monitoring.metrics.mcp_worker",
        "MCPWorkerMetricsRecorder",
        "autobot-backend/services/mcp_worker_metrics_test.py",
    ),
    (
        "autobot_shared.monitoring.prometheus_metrics",
        "get_metrics_manager",
        "autobot-backend/llm_shared/base_provider_metrics_test.py",
    ),
    (
        "services.mcp_isolated_runtime",
        "IsolatedBridgeClient",
        "autobot-backend/services/mcp_run_jwt_propagation_test.py",
    ),
)


def _references(source: str, module: str, attribute: str) -> bool:
    """Whether *source* names *attribute*, by import, by use, or by patch target.

    Read from the AST rather than by substring so a mention inside a comment or
    a prose docstring does not count as coverage — the citation has to point at
    code that actually resolves the attribute.

    The patch-target match ends on a word boundary. A plain substring test
    accepts `…get_metrics_managerRenamed` as evidence for `get_metrics_manager`,
    so renaming the very symbol the citation covers would leave the guard green.
    """
    tree = ast.parse(source)
    dotted = re.compile(rf"{re.escape(module)}\.{re.escape(attribute)}(?!\w)")
    for node in ast.walk(tree):
        if isinstance(node, ast.alias) and node.name == attribute:
            return True
        if isinstance(node, ast.Name) and node.id == attribute:
            return True
        if isinstance(node, ast.Attribute) and node.attr == attribute:
            return True
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and dotted.search(node.value):
            return True
    return False


def test_the_removed_scripts_have_not_returned_unwired():
    """The front door stays clear of checkers nothing invokes.

    Not a rule about the filename — the root legitimately holds `main.py`,
    `conftest.py` and `install.sh`. These two specifically are covered work, and
    re-adding either would restore a second copy of a check that already runs.
    """
    for name in ("check_syntax.py", "check_mcp_imports.py"):
        assert not (_REPO / name).exists(), f"{name} is back at the repository root; its check already runs (#14219)"


def _flake8_exclude_patterns(config_text: str | None = None) -> list[str]:
    """`.flake8`'s `exclude =` entries, as fnmatch patterns.

    flake8 matches each entry against every *component* of a path it walks, not
    against the path as a whole, which is what makes a bare `monitoring` prune
    `autobot_shared/monitoring/` (#14419).
    """
    parser = configparser.ConfigParser()
    parser.read_string(config_text if config_text is not None else (_REPO / ".flake8").read_text(encoding="utf-8"))
    raw = parser["flake8"].get("exclude", "")
    entries = (entry.strip() for line in raw.splitlines() for entry in line.split(","))
    return [entry for entry in entries if entry and not entry.startswith("#")]


def _invocation(workflow_text: str, tool: str) -> str | None:
    """The line in code-quality.yml that actually runs *tool*, if any."""
    for line in workflow_text.splitlines():
        if f"-m {tool}" in line and "pip install" not in line:
            return line
    return None


def _reach(rel: str, workflow_text: str | None = None, flake8_text: str | None = None) -> set[str]:
    """Which CI linters arrive at *rel* once their own exclusions are applied.

    Invocation alone is not reach. A tool named on a line that also names the
    tree still skips the file if its config prunes a component of the path, and
    that is exactly how three of these four files came to be uncovered by flake8
    while a workflow grep said otherwise.
    """
    workflow = workflow_text if workflow_text is not None else _WORKFLOW.read_text(encoding="utf-8")
    reaching = set()

    black = _invocation(workflow, "black")
    if black and any(rel.startswith(tree) for tree in re.findall(r"\S+/", black)):
        # black takes no exclusion in this invocation, and `[tool.black]` in
        # pyproject.toml declares none either. Both are asserted below.
        if not re.search(r"--(extend-|force-)?exclude", black):
            reaching.add("black")

    flake8 = _invocation(workflow, "flake8")
    if flake8 and any(rel.startswith(tree) for tree in re.findall(r"\S+/", flake8)):
        patterns = _flake8_exclude_patterns(flake8_text)
        pruned = any(fnmatch.fnmatch(part, pattern) for part in Path(rel).parts for pattern in patterns)
        if not pruned:
            reaching.add("flake8")

    return reaching


@pytest.mark.parametrize("rel", _GUARDED_FILES)
def test_a_syntax_error_in_the_file_is_still_caught_by_some_ci_linter(rel):
    """`check_syntax.py`'s replacement, measured at the file rather than the tree.

    This is the assertion the removal depends on: a linter that parses this
    exact file still runs in CI. Nothing here cares which one — only that the
    set is not empty, because an empty set is the state in which deleting the
    script silently lost the check.
    """
    assert _reach(rel), f"no CI linter reaches {rel}; removing check_syntax.py lost its coverage (#14219)"


@pytest.mark.parametrize("rel", _GUARDED_FILES)
def test_the_measured_reach_has_not_changed(rel):
    """The drift detector for the assertion above.

    Coverage can shrink without reaching zero, and the shrink that matters here
    is black's: it is the only linter reaching three of these files, so widening
    its excludes — "aligning them with flake8's for consistency" is the obvious
    way — would take the coverage away one file at a time. Widening flake8's
    fails here too, and #14419 narrowing them will as well, which is the point:
    a change in what guards these files should not pass silently.
    """
    assert _reach(rel) == _MEASURED_REACH[rel], (
        f"the linters reaching {rel} changed: {sorted(_reach(rel))}, "
        f"recorded {sorted(_MEASURED_REACH[rel])}. Re-measure before updating the map (#14219, #14419)."
    )


def test_black_declares_no_exclusions_of_its_own():
    """`_reach` reads the invocation; `[tool.black]` could override it silently.

    An `exclude` / `extend-exclude` / `force-exclude` key added to pyproject.toml
    applies wherever black runs, so it would remove the coverage above without
    touching the workflow line this module inspects.
    """
    pyproject = (_REPO / "pyproject.toml").read_text(encoding="utf-8")
    section = re.search(r"^\[tool\.black\]$(.*?)(?=^\[)", pyproject, re.MULTILINE | re.DOTALL)

    assert section, "[tool.black] is gone from pyproject.toml — re-check what black actually formats (#14219)"
    assert not re.search(
        r"^\s*(extend-|force-)?exclude\s*=", section.group(1), re.MULTILINE
    ), "black now declares an exclusion; re-measure which linters reach the files check_syntax.py compiled (#14219)"


@pytest.mark.parametrize("tool", ["black", "flake8"])
def test_the_same_tools_still_run_before_a_commit(tool):
    """The local half of the same coverage.

    CI is the gate, but the removed script was a developer's pre-commit habit,
    and pre-commit is where that habit now lives. flake8's reach here is the
    same subset as in CI — the hook reads the identical `.flake8`.
    """
    config = (_REPO / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    assert re.search(rf"^\s*-\s*id:\s*{tool}\b", config, re.MULTILINE), f"the {tool} pre-commit hook is gone (#14219)"


@pytest.mark.parametrize("module,attribute,covering_test", _IMPORT_CHECKS)
def test_each_mcp_import_check_is_performed_by_a_collected_test(module, attribute, covering_test):
    """`check_mcp_imports.py`'s replacement, one citation at a time.

    Importing a module and reading one attribute off it is exactly what a test
    that imports or patches that attribute does, except that a test runs. If the
    cited file is renamed or stops touching the attribute, this fails here
    instead of leaving a removal justified by a citation that points nowhere.
    """
    path = _REPO / covering_test

    assert path.is_file(), f"the test covering {module}.{attribute} is gone: {covering_test} (#14219)"
    assert _references(
        path.read_text(encoding="utf-8"), module, attribute
    ), f"{covering_test} no longer resolves {module}.{attribute} — nothing checks it imports (#14219)"
