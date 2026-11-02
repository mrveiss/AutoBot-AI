# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Detector for a test file that builds a git repo without the isolated env (#18940).

A file-level rule, because the call-level shape varies too much to follow: a literal
``["git", "init"]`` argv, a ``_git(repo, "commit")`` helper, a ``bash -c "git init"`` string.
A file BUILDS a repo when it imports ``subprocess``, names ``init`` or ``commit`` in the same
argv/call as ``git`` (an argv led by ``git``, a ``*git*`` helper call, or ``git`` among the
call's arguments). It is COMPLIANT when it imports from ``autobot_shared.isolated_git``.

A file that imports the helper is checked at call level by ``tools/lint/check_git_write_env_scrubbed.py``
(#15246): a literal ``["git", "commit"]`` argv or a ``["git", "-C", p, *args]`` helper with no scrubbed
``env=`` is reported there (pinned in ``isolated_git_env_guard_18940_test.py``). That gate cannot see a
git write inside a shell string, so here a helper-importing file that runs ``bash -c "git init|commit"``
without ever naming ``isolated_git_env`` also offends.

KNOWN GAP: argv built through a variable (``cmd = ["git", "commit"]; subprocess.run(cmd)``) and a
``bash -c`` script whose file names ``isolated_git_env`` elsewhere are accepted in a helper-importing file.
"""

from __future__ import annotations

import ast
import re
from pathlib import PurePosixPath

HELPER_MODULE = "autobot_shared.isolated_git"
_VERBS = frozenset({"init", "commit"})
_SHELL_GIT = re.compile(r"\bgit\s+(?:-\S+\s+)*(?:init|commit)\b")
_SKIP_PARTS = frozenset({"node_modules", ".git", ".worktrees", "__pycache__"})


def is_test_file(rel: str) -> bool:
    """A test module or conftest, by repo-relative name."""
    name = PurePosixPath(rel).name
    return name.endswith("_test.py") or name.startswith("test_") or name == "conftest.py"


def is_skipped(rel: str) -> bool:
    """True when a repo-RELATIVE path part is a skipped directory (#18972)."""
    return bool(_SKIP_PARTS & set(PurePosixPath(rel).parts[:-1]))


def _strings(elements: list[ast.expr]) -> set[str]:
    return {e.value for e in elements if isinstance(e, ast.Constant) and isinstance(e.value, str)}


def _is_git_word(node: ast.expr) -> bool:
    """A string constant that is the ``git`` executable: ``"git"`` or a path ending in ``/git``."""
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.rsplit("/", 1)[-1] == "git"


def _callee_name(call: ast.Call) -> str:
    func = call.func
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""


def _names_verb(tree: ast.Module) -> bool:
    """A verb tied to a git invocation in the SAME expression.

    Either an argv list led by ``git`` (element 0 or 1), or a call that names git itself: a
    ``*git*`` callee (``_git(repo, "commit")``) or ``git`` among its own string arguments.
    ``session.add("commit")`` in a file that mentions git elsewhere is neither.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.List) and any(_is_git_word(e) for e in node.elts[:2]) and _VERBS & _strings(node.elts):
            return True
        if isinstance(node, ast.Call) and _VERBS & _strings(node.args):
            if "git" in _callee_name(node).lower() or any(_is_git_word(a) for a in node.args):
                return True
    return False


def _shell_builds_repo(tree: ast.Module) -> bool:
    """``["bash", "-c", "git init ..."]``: the script string right after a ``-c`` argv element."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.List):
            continue
        for flag, script in zip(node.elts, node.elts[1:]):
            if _is_str(flag, "-c") and isinstance(script, ast.Constant) and isinstance(script.value, str):
                if _SHELL_GIT.search(script.value):
                    return True
    return False


def _is_str(node: ast.expr, value: str) -> bool:
    return isinstance(node, ast.Constant) and node.value == value


def _imports_subprocess(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name == "subprocess" for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            return True
    return False


def builds_git_repo(tree: ast.Module) -> bool:
    """True when *tree* spawns processes and names ``init``/``commit`` as a git argument."""
    if not _imports_subprocess(tree):
        return False
    return _names_verb(tree) or _shell_builds_repo(tree)


def imports_helper(tree: ast.Module) -> bool:
    """True when *tree* imports :data:`HELPER_MODULE`: ``from`` it, ``import`` it, or with an alias."""
    parent, _, leaf = HELPER_MODULE.rpartition(".")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == HELPER_MODULE:
            return True
        if isinstance(node, ast.ImportFrom) and node.module == parent and any(a.name == leaf for a in node.names):
            return True
        if isinstance(node, ast.Import) and any(a.name == HELPER_MODULE for a in node.names):
            return True
    return False


def _names_env_helper(tree: ast.Module) -> bool:
    return any(
        (isinstance(n, ast.Name) and n.id == "isolated_git_env")
        or (isinstance(n, ast.Attribute) and n.attr == "isolated_git_env")
        for n in ast.walk(tree)
    )


def offends(source: str) -> bool:
    """True for a repo-building test file that does not use the isolated helper, or that imports it
    but runs a shell-string git write without ever naming ``isolated_git_env``."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    if not imports_helper(tree):
        return builds_git_repo(tree)
    return _imports_subprocess(tree) and _shell_builds_repo(tree) and not _names_env_helper(tree)
