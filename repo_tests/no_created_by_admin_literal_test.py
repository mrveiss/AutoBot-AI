# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No backend write path records an audit trail as `created_by="admin"` (#16541).

`api/settings.py` (#16278/#16501) and `api/agent_config.py` (#16547) both
carried this defect: a route gated by `check_admin_permission` admits either
an admin session or the internal-service key, discards which one, then writes
the literal string `"admin"` into a `ConfigRevisionService.create_revision(...)`
call -- an audit trail that cannot distinguish two different admins, or an
admin from the internal-service key, for any change. Both are fixed now; this
keeps a third from landing the same way.

Parsed, not grepped: a regex over `created_by="admin"` cannot tell a real
keyword argument from this file's own docstring describing the defect (which
would then flag itself), and it would also fire in an unrelated string that
happens to contain the same substring.
"""

from __future__ import annotations

import ast
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.paths import scrubbed_git_env

REPO_ROOT = repo_root()

#: The two backend services this guard scopes to -- both are Python service
#: trees where a ConfigRevisionService-style audit write could occur.
_SCOPED_DIRS = ("autobot-backend", "autobot-slm-backend")


def _created_by_admin_literals(source: str) -> list[int]:
    """Line numbers of every ``created_by="admin"`` keyword argument in *source*.

    Returns ``[]`` (not ``None``) for source that fails to parse -- a
    syntactically broken tracked ``.py`` file is a different problem this
    guard does not own, and `_tracked_backend_python_files` already excludes
    nothing conditionally, so no offender can hide behind a parse failure.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "created_by" and isinstance(kw.value, ast.Constant) and kw.value.value == "admin":
                hits.append(kw.value.lineno)
    return hits


def _tracked_backend_python_files(root: Path = REPO_ROOT) -> list[Path]:
    """Tracked ``.py`` files under the scoped backend dirs, tests excluded.

    Takes a root so the declaration below can be driven against an empty
    directory by ``reach_declarations_test`` (#15826) -- without that, nothing
    can prove the floor fires.
    """
    result = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "--", *(f"{d}/*.py" for d in _SCOPED_DIRS)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env=scrubbed_git_env(),
    )
    return [root / line for line in result.stdout.splitlines() if line and not line.endswith("_test.py")]


#: Ratcheted well below the live population (3514 non-test files under the two
#: scoped dirs as of #16541) so ordinary churn never trips it, while still
#: catching a narrowed glob, a moved directory, or a broken git env -- the
#: failure this mechanism exists to distinguish from "genuinely found nothing"
#: (#15826).
REACH = declare(
    "no-created-by-admin-literal",
    discover=_tracked_backend_python_files,
    floor=3000,
    growth=300,
    what="tracked backend python files (tests excluded)",
)


def test_no_created_by_admin_literal_exists():
    files = _tracked_backend_python_files()
    assert files, "discovered zero backend python files -- a broken git env or moved directory, not a clean repo"

    offenders: dict[str, list[int]] = {}
    for path in files:
        hits = _created_by_admin_literals(path.read_text(encoding="utf-8"))
        if hits:
            offenders[str(path.relative_to(REPO_ROOT))] = hits

    assert not offenders, (
        f'created_by="admin" literal(s) found: {offenders} -- record the actual authenticated actor '
        "(see api/settings_config.py::require_settings_admin) instead of a privileged literal"
    )
