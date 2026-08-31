# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No hook test suite may invoke a shell builtin through ``subprocess`` (#14884).

``pre-commit-worktree-branch-guard_test.py`` resolved git with
``subprocess.run(["command", "-v", "git"])``. ``command`` is a POSIX shell
*builtin*, not a program, so ``subprocess`` — which never involves a shell when
given a list — raised ``FileNotFoundError`` on any machine with no ``command``
binary on PATH. The test that died was the fail-closed proof that a
``git worktree list`` failure is not reported as a clean tree, so that property
was unverified for as long as the idiom stood.

The class is worth a guard rather than a one-line fix because the failure is
environment-dependent: on a machine that happens to ship a ``command``
executable the same code passes, so review cannot see it and a green local run
does not disprove it. The Python suite is not a required check here, so nothing
else was ever going to notice.

Checked by parsing, not by grepping for the word: a string in a docstring or an
error message is not a call, and this guard has to survive both. Reach floors
are asserted, because an AST walk that stops matching finds no offenders and
reads exactly like a clean tree.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HOOKS = _REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts" / "hooks"

# Callables that hand argv straight to execve, so a builtin can never be found.
_SPAWNERS = {"run", "Popen", "call", "check_call", "check_output"}

# POSIX shell builtins with no binary counterpart guaranteed on PATH. `command`
# is the one that bit us; the rest are the same mistake wearing another name.
_BUILTINS = {
    "alias",
    "cd",
    "command",
    "eval",
    "exec",
    "export",
    "hash",
    "set",
    "source",
    "type",
    "unalias",
    "unset",
}


class _Call:
    """One ``subprocess`` spawn whose argv is a list literal."""

    def __init__(self, rel: str, lineno: int, program: str | None):
        self.rel = rel
        self.lineno = lineno
        self.program = program  # None when argv[0] is not a string literal

    def __repr__(self) -> str:  # pragma: no cover - failure output only
        return f"{self.rel}:{self.lineno}"


def _spawn_calls() -> tuple[list[_Call], int]:
    """Every list-argv spawn in the hook suites, and the modules parsed."""
    calls: list[_Call] = []
    modules = 0
    for module in sorted(_HOOKS.rglob("*_test.py")):
        modules += 1
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        rel = str(module.relative_to(_REPO_ROOT))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name not in _SPAWNERS:
                continue
            argv = node.args[0]
            if not isinstance(argv, ast.List) or not argv.elts:
                continue
            head = argv.elts[0]
            literal = head.value if isinstance(head, ast.Constant) and isinstance(head.value, str) else None
            calls.append(_Call(rel, node.lineno, literal))
    return calls, modules


_CALLS, _MODULES = _spawn_calls()


def test_the_sweep_actually_parsed_the_hook_suites() -> None:
    """Discovery floor. An AST walk that matches nothing reads as clean.

    Three floors: the module count catches the directory moving, the call count
    catches ``_SPAWNERS`` or the ``ast.List`` shape no longer matching, and the
    literal count catches a reader that returns ``None`` for every argv[0] —
    which would make the offender check below vacuously empty.
    """
    assert _HOOKS.is_dir(), f"{_HOOKS} does not exist — this guard has no subject"
    assert _MODULES >= 18, f"only parsed {_MODULES} hook test modules"
    assert len(_CALLS) >= 67, (
        f"only found {len(_CALLS)} subprocess spawns — the AST matcher has regressed"
    )
    literals = [call for call in _CALLS if call.program is not None]
    assert len(literals) >= 67, (
        f"only {len(literals)} spawns name their program as a string literal — "
        "argv[0] is no longer being read, so no builtin could ever be detected"
    )


def test_no_hook_suite_spawns_a_shell_builtin() -> None:
    """The #14884 class: ``subprocess`` with a list never involves a shell.

    Whatever the suite wanted from the builtin has an in-process answer
    (``shutil.which`` for ``command -v``, ``os.chdir``/``cwd=`` for ``cd``); if
    it genuinely needs shell semantics it must say so with an explicit
    ``["bash", "-c", ...]``, which this check reads as ``bash`` and allows.
    """
    offenders = sorted(
        f"{call.rel}:{call.lineno} spawns `{call.program}`"
        for call in _CALLS
        if call.program in _BUILTINS
    )
    assert not offenders, (
        "these call sites hand a shell BUILTIN to subprocess, which execs argv[0] "
        "directly and raises FileNotFoundError wherever no binary of that name "
        "happens to exist. The failure is environment-dependent, so a green run "
        "here does not clear it (#14884):\n  " + "\n  ".join(offenders)
    )


def test_the_two_repaired_suites_are_still_covered() -> None:
    """The suites #14884 named, pinned so the sweep cannot drift off them."""
    covered = {call.rel for call in _CALLS}
    for rel in (
        "autobot-infrastructure/shared/scripts/hooks/pre-commit-worktree-branch-guard_test.py",
        "autobot-infrastructure/shared/scripts/hooks/pre-commit-no-tag-pinned-action_test.py",
    ):
        assert rel in covered, f"{rel} is no longer reached by the sweep (#14884)"
