# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The man-page indexer is where the refresh task looks for it (#15853).

`knowledge_tasks._run_indexing_subprocess` shelled out to
`"scripts/utilities/index_all_man_pages.py"` -- relative to the process working
directory, and there is no `scripts/utilities/` at the repository root at all.
The script is real; it lives under `autobot-infrastructure/shared/`. So the
refresh returned its `failed` dict on every run, with the subprocess's stderr
truncated into a generic message, and system knowledge was presumably never
refreshed by this task.

Same defect class as #15845, whose hook pointed at an indexer that was never
created: a wired path that resolves nowhere, degrading quietly instead of
failing loudly.

**The path is read out of the module under test, never restated here.** A test
carrying its own copy of the path passes when the module's copy moves alone,
which is precisely the failure it exists to catch.
"""

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_TASKS = REPO_ROOT / "autobot-backend/tasks/knowledge_tasks.py"


def _module_source() -> str:
    """The module's code, with comment lines removed.

    The module documents the old cwd-relative path in a comment directly above
    the constant that replaced it. Matching raw text, "the bad literal is gone"
    is then false while the code is correct -- the explanation of the fix sits
    nearer to the fix than anything else does, and it is made of the very string
    the check looks for. Same reason the #15724 publish-contract guard strips
    comments before matching.
    """
    text = _TASKS.read_text(encoding="utf-8")
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _indexer_path_expression() -> str:
    """The right-hand side of MAN_PAGE_INDEXER, as written in the module."""
    tree = ast.parse(_module_source())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "MAN_PAGE_INDEXER" for t in node.targets
        ):
            return ast.unparse(node.value)
    raise AssertionError("MAN_PAGE_INDEXER is not defined -- this test would prove nothing")


def _resolved_indexer() -> Path:
    """Resolve the module's expression to a real path, without importing the backend.

    Importing `knowledge_tasks` pulls in Celery and the whole task graph. The
    expression is a chain of `/` operands, so the string literals in it are the
    path segments -- read them from the AST instead.
    """
    expression = _indexer_path_expression()
    assert "PATH.PROJECT_ROOT" in expression, f"MAN_PAGE_INDEXER is not anchored to the project root: {expression}"
    segments = re.findall(r"'([^']+)'|\"([^\"]+)\"", expression)
    parts = [a or b for a, b in segments]
    assert parts, f"no path segments found in {expression}"
    return REPO_ROOT.joinpath(*parts)


def test_the_indexer_path_is_anchored_to_the_repo_root_not_the_cwd():
    """A cwd-relative path resolves differently under Celery, systemd and pytest."""
    expression = _indexer_path_expression()

    assert "PATH.PROJECT_ROOT" in expression, expression
    assert not re.search(
        r"^['\"]scripts/", expression
    ), "the indexer is addressed relative to the process working directory"


def test_the_indexer_exists_where_the_task_looks_for_it():
    """The defect itself, with the path read from the caller rather than restated."""
    indexer = _resolved_indexer()

    assert indexer.is_file(), (
        f"knowledge_tasks resolves the man-page indexer to {indexer.relative_to(REPO_ROOT)}, " "which does not exist"
    )


def test_a_missing_indexer_is_reported_by_path():
    """Absence must be distinguishable from a run that failed.

    The old code returned the subprocess's truncated stderr, so "the indexer is
    not where we looked" and "the indexer ran and failed" produced the same
    message.
    """
    source = _module_source()

    assert "MAN_PAGE_INDEXER.is_file()" in source, "nothing checks whether the indexer exists before shelling out to it"
    assert re.search(
        r"not found at \{MAN_PAGE_INDEXER\}", source
    ), "the not-found message does not name the path it looked for"


def test_the_subprocess_invokes_the_anchored_path():
    """The constant must be what is executed.

    Defining an anchored constant and then passing a literal to `subprocess.run`
    would satisfy every assertion above while changing nothing.
    """
    source = _module_source()

    assert "[sys.executable, str(MAN_PAGE_INDEXER)]" in source, "the subprocess does not execute MAN_PAGE_INDEXER"
    assert (
        "scripts/utilities/index_all_man_pages.py" not in source
    ), "the cwd-relative literal is still present in the module"
