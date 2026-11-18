# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AST predicates for "is this call starting a process, and is it git?" (#14896).

``check_git_toplevel_env_scrubbed`` and ``check_git_write_env_scrubbed`` each
carried their own copy of the subprocess-call matcher, and the second had
already drifted from the first (no async variant). One definition here.
"""

from __future__ import annotations

import ast
from typing import Set

#: ``subprocess`` entry points that start a process.
_SUBPROCESS_CALLS = frozenset({"run", "Popen", "call", "check_call", "check_output"})

#: ``asyncio``'s process starters. Added by #15783 after the fourth recurrence
#: landed in one: a delete guard's ``asyncio.create_subprocess_exec("git",
#: "status", ...)`` inherited ``GIT_DIR`` and reported another repository's
#: 9890 uncommitted changes. An async call site carries the identical defect
#: and was invisible to a scanner that only knew ``subprocess``.
_ASYNC_SUBPROCESS_CALLS = frozenset({"create_subprocess_exec", "create_subprocess_shell"})


def _is_subprocess_call(node: ast.Call, modules: Set[str], functions: Set[str]) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in _SUBPROCESS_CALLS:
        return isinstance(func.value, ast.Name) and func.value.id in modules
    if isinstance(func, ast.Name):
        return func.id in functions
    return False


def _is_async_subprocess_call(node: ast.Call, modules: Set[str], functions: Set[str]) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in _ASYNC_SUBPROCESS_CALLS:
        return isinstance(func.value, ast.Name) and func.value.id in modules
    if isinstance(func, ast.Name):
        return func.id in functions
    return False


def _is_git_argv(node: ast.Call) -> bool:
    """True when the call's first argument names ``git`` as argv[0].

    Covers the three spellings that reach a process: a list/tuple
    (``subprocess.run(["git", ...])``), a bare positional
    (``asyncio.create_subprocess_exec("git", ...)``), and a command string
    (``subprocess.run("git status", shell=True)``). Argv built through a
    variable stays invisible -- the same documented gap as the token scan.
    """
    arguments = _command_arguments(node)
    if not arguments:
        return False
    first = arguments[0]
    if isinstance(first, (ast.List, ast.Tuple)) and first.elts:
        head = first.elts[0]
        return isinstance(head, ast.Constant) and isinstance(head.value, str) and _names_git(head.value)
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return _names_git(first.value.split()[0] if first.value.split() else "")
    return False


def _names_git(argv0: str) -> bool:
    return argv0 == "git" or argv0.endswith("/git")


def _command_arguments(node: ast.Call) -> list[ast.expr]:
    """Positional arguments plus a literal ``args=`` keyword.

    ``subprocess.run(args=["git", "status"])`` is an ordinary spelling, and
    reading only ``node.args`` meant such a call was neither gated nor counted
    toward the discovery floor -- a blind spot in the matcher rather than in the
    enumeration, which the reach floor cannot detect (#15783 review).
    """
    keyword_args = [kw.value for kw in node.keywords if kw.arg == "args"]
    return list(node.args) + keyword_args
