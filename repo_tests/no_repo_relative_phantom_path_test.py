# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No executable code names a retired component directory by a repo-relative path (#15193).

`autobot-user-backend/` was renamed to `autobot-backend/`. The rename left 196
mentions of the old name across 39 tracked files, and the ones that mattered
were not the prose: they were the executable ones, which kept running and kept
reporting success while addressing a directory that is in no commit.

Measured on the parent of this commit:

* five ``sys.path.insert(..., parents[4] / "autobot-user-backend")`` calls under
  the infrastructure migration scripts -- a sys.path entry pointing at nothing
* ``scripts/hooks/post-checkout`` set ``BACKEND_DIR="$GIT_ROOT/autobot-user-backend"``
  and then gated its repair block on ``[ -d "$BACKEND_DIR" ]``, so the block
  had not run since the rename
* ``activate-mcp-bridges.sh`` probed ``autobot-user-backend/api/<bridge>.py``,
  so it reported every one of the five bridges absent

None of those raised. That is the shape this guard exists for: a wrong path is
only loud when something insists the target be there, and each of these sites
asked politely.

The key: repo-relative versus absolute
======================================
The same name legitimately appears in *absolute* paths -- the deploy host
really does serve the component out of a directory of that name, and the
systemd unit, the ansible playbooks and the recovery scripts must keep naming
it. `autobot-backend/utils/paths_manager.py` carries the reason those absolute
paths are correct and must not be "fixed".

So this guard keys on the leading character of the path token, not on the name:
a token beginning with ``/`` (or ``~``) addresses the deploy host and is
exempt; anything else is resolved against the repository and is a defect. A
check that flagged both would have flagged roughly ten ansible playbooks and
the service template, all correct, and would have been suppressed within a
week.

Scope: executable content only
==============================
Only Python string literals that are not docstrings, and non-comment lines of
shell scripts and git hooks, are scanned. A rename has to stay describable:
`CHANGELOG.md`, `docs/archives/`, the comment at
`autobot-infrastructure/shared/tests/conftest.py` and the docstring at
`pipeline-scripts/pytest_root_collection_floor.py` all name the old directory
on purpose, to say it is gone. Prose that mentions a path is not code that
resolves one.

Adding to the registry
======================
When a component directory is renamed, add its old name to
:data:`RETIRED_COMPONENT_DIRS`. The guard then fails on any executable
repo-relative reference that survived the rename.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path
from typing import Iterable, Iterator, List, Tuple

import pytest

from autobot_shared.paths import scrubbed_git_env

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Component directories that no commit contains. See "Adding to the registry".
RETIRED_COMPONENT_DIRS: Tuple[str, ...] = ("autobot-user-backend",)

#: A maximal run of path characters. Deliberately excludes ``=``, ``:`` and the
#: quote characters so that ``PYTHONPATH=/opt/a:/opt/b`` yields two tokens, each
#: keeping the leading ``/`` that marks it absolute.
_PATHISH = re.compile(r"[\w./${}*~-]+")

#: ``cd autobot-user-backend && uvicorn main:app`` names the directory as a
#: path without ever writing a slash, so :data:`_PATHISH` cannot see it. It was
#: the form five of `main.py`'s references took. Anchored on ``cd`` because that
#: is what makes the bare name a directory, and a retired name is never a
#: legitimate ``cd`` target.
_CD_INTO = tuple(
    (re.compile(r"\bcd\s+(?:\./)?" + re.escape(retired) + r"(?![\w./-])"), retired)
    for retired in RETIRED_COMPONENT_DIRS
)

#: Excluded by path, not by a cleverer pattern: this module quotes the defect in
#: its docstring and again in the contrast cases, so it matches itself.
_SELF = Path(__file__).resolve()

#: Below this, the sweep collapsed rather than the tree being clean.
_MIN_SOURCE_FILES = 4000

Offender = Tuple[str, int, str]


def _tracked_sources() -> List[str]:
    """Repo-relative paths of every tracked Python, shell and git-hook file."""
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    )
    kept: List[str] = []
    for name in completed.stdout.split("\0"):
        # Relative, never absolute: an absolute prefix does not match inside a
        # worktree, which is where this suite actually runs (#14484).
        if not name or name.startswith(".worktrees/"):
            continue
        if name.endswith((".py", ".sh")) or "scripts/hooks/" in f"/{name}":
            kept.append(name)
    return kept


def is_repo_relative(token: str) -> bool:
    """True when *token* resolves against the repository rather than the host."""
    return not token.startswith(("/", "~"))


def names_retired_dir(token: str) -> bool:
    """True when a whole path segment of *token* is a retired component dir."""
    return any(segment in RETIRED_COMPONENT_DIRS for segment in token.split("/"))


def phantom_path_tokens(text: str) -> Iterator[str]:
    """Repo-relative path tokens in *text* that address a retired component dir."""
    for match in _PATHISH.finditer(text):
        token = match.group(0)
        if "/" not in token or not names_retired_dir(token):
            continue
        if is_repo_relative(token):
            yield token


def phantom_cd_targets(text: str) -> Iterator[str]:
    """``cd <retired>`` in *text* -- a path use that carries no slash of its own."""
    for pattern, name in _CD_INTO:
        if pattern.search(text):
            yield f"cd {name}"


def phantom_references(text: str) -> List[str]:
    """Every executable repo-relative reference to a retired dir in *text*."""
    return list(phantom_path_tokens(text)) + list(phantom_cd_targets(text))


def _docstring_ids(tree: ast.AST) -> set:
    """Object ids of every module/class/function docstring node in *tree*."""
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        body = getattr(node, "body", None)
        first = body[0] if body else None
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                found.add(id(first.value))
    return found


def _joined_bare_names(tree: ast.AST) -> Iterator[ast.Constant]:
    """Bare ``"<retired>"`` literals used as a path component.

    ``parents[4] / "autobot-user-backend"`` carries no slash of its own, so
    :func:`phantom_path_tokens` cannot see it. The join operator is what makes
    it a path, so the join is what this matches -- which also spares an
    identically-spelled *service* name (``SERVICE_NAME="autobot-user-backend"``
    in the deploy templates), where no join takes place.
    """
    for node in ast.walk(tree):
        operands: Iterable[ast.expr] = ()
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            operands = (node.left, node.right)
        elif isinstance(node, ast.Call):
            operands = node.args
        for operand in operands:
            if isinstance(operand, ast.Constant) and operand.value in RETIRED_COMPONENT_DIRS:
                yield operand


def _python_offenders(name: str, text: str) -> List[Offender]:
    """Offending non-docstring string literals in the Python source *text*."""
    try:
        tree = ast.parse(text)
    except SyntaxError:  # pragma: no cover - a tracked file that will not parse
        return []
    skip = _docstring_ids(tree)
    found: List[Offender] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in skip:
            continue
        for token in phantom_references(node.value):
            found.append((name, node.lineno, token))
    for node in _joined_bare_names(tree):
        if id(node) not in skip:
            found.append((name, node.lineno, str(node.value)))
    return found


def _shell_offenders(name: str, text: str) -> List[Offender]:
    """Offending tokens on non-comment lines of the shell source *text*."""
    found: List[Offender] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        for token in phantom_references(line):
            found.append((name, number, token))
    return found


def _offenders() -> List[Offender]:
    """Every executable repo-relative reference to a retired component dir."""
    found: List[Offender] = []
    for name in _SOURCES:
        path = REPO_ROOT / name
        if path.resolve() == _SELF:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # pragma: no cover - unreadable
            continue
        if not any(retired in text for retired in RETIRED_COMPONENT_DIRS):
            continue
        if name.endswith(".py"):
            found.extend(_python_offenders(name, text))
        else:
            found.extend(_shell_offenders(name, text))
    return found


_SOURCES = _tracked_sources()


def test_the_sweep_reached_the_tree() -> None:
    """Runs first: an empty file list would pass the assertion below vacuously."""
    assert len(_SOURCES) >= _MIN_SOURCE_FILES, (
        f"only {len(_SOURCES)} tracked Python/shell/hook files found, floor is "
        f"{_MIN_SOURCE_FILES}. FIX THE SWEEP -- a guard that reads nothing "
        "reports clean over anything."
    )


def test_no_executable_repo_relative_reference_to_a_retired_dir() -> None:
    offenders = _offenders()

    assert not offenders, (
        "executable code addressing a retired component directory by a "
        "repo-relative path (absolute deploy-host paths are exempt -- see "
        "autobot-backend/utils/paths_manager.py):\n"
        + "\n".join(f"  {name}:{number}: {token}" for name, number, token in offenders)
    )


@pytest.mark.parametrize(
    "line,should_flag",
    [
        # Class A -- repo-relative, resolves against a directory that is absent.
        ('FILE="autobot-user-backend/api/${bridge}.py"', True),
        ('BACKEND_DIR="$GIT_ROOT/autobot-user-backend"', True),
        ("cd autobot-user-backend && uvicorn main:app", True),
        # Class B -- absolute, addresses the deploy host, must NOT be flagged.
        ("WorkingDirectory=/opt/autobot/autobot-user-backend", False),
        ('Environment="PYTHONPATH=/opt/autobot:/opt/autobot/autobot-user-backend"', False),
        ("EnvironmentFile=/opt/autobot/autobot-user-backend/.env", False),
        ("ExecStart=/opt/autobot/autobot-user-backend/venv/bin/uvicorn main:app", False),
        # Not a path: a systemd unit name, and the template file named after it.
        ('SERVICE_NAME="autobot-user-backend"', False),
        ("autobot-infrastructure/autobot-backend/templates/autobot-user-backend.service", False),
        # The current name is not retired.
        ('FILE="autobot-backend/api/mcp_registry.py"', False),
    ],
)
def test_the_absolute_versus_repo_relative_key(line: str, should_flag: bool) -> None:
    """The contrast that makes the guard shippable rather than suppressed."""
    assert bool(phantom_references(line)) is should_flag


@pytest.mark.parametrize(
    "source,should_flag",
    [
        ('sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "autobot-user-backend"))', True),
        ('backend = os.path.join(os.path.dirname(__file__), "..", "autobot-user-backend")', True),
        ('SERVICE_NAME = "autobot-user-backend"', False),
        ('"""The backend used to live in autobot-user-backend/."""', False),
        ('DEPLOYED = "/opt/autobot/autobot-user-backend"', False),
    ],
)
def test_python_join_and_docstring_handling(source: str, should_flag: bool) -> None:
    """A bare name is a path only where it is joined onto one."""
    assert bool(_python_offenders("probe.py", source)) is should_flag
