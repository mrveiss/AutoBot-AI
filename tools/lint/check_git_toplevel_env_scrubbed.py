#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``git rev-parse --show-toplevel`` must run with the git environment scrubbed (#15176, #15245).

A git hook run in a **worktree** — this repository's entire workflow — is handed
``GIT_DIR=<main>/.git/worktrees/<name>`` and no ``GIT_WORK_TREE`` (measured on
git 2.34.1, for both ``pre-commit`` and ``pre-push``). Git then treats the
**current directory** as the work tree, so ``--show-toplevel`` answers with
wherever the caller happens to be standing rather than the repository root.

Git chdirs the hook itself to the top level, so the hook's own first call is
right by luck. Everything downstream of it is not: a helper passing ``cwd=``,
an imported test module, a CI step running a guard directly from elsewhere.

The answer is wrong without being an error, and that is what makes this worth a
gate rather than a code review note. Six guards in this repository shared the
pattern. #15018 hit the loud half — ``pytest.ini`` read out of ``repo_tests/``,
``FileNotFoundError``. #15176 measured the silent half: two **pre-commit hook**
entries printed their success line while having read zero of the files they
exist to inspect, one of them over a deliberately planted violation.

Five hand-rolled repeats of one four-line scrub is how that became a family, so
the rule here is not "scrub it somehow" but "go through the one helper":

    from autobot_shared.paths import git_repo_root
    root = git_repo_root()

A call is accepted when it passes ``env=scrubbed_git_env(...)`` explicitly —
that is what ``git_repo_root`` itself does, and it keeps the helper from having
to exempt itself.

SCOPE, AND WHAT IS DELIBERATELY NOT SCOPED
------------------------------------------
* **Python AND shell, two different scanners.** #15176 covered only ``.py``
  files, noting fourteen shell call sites as an unclosed gap; #15245 closed
  it. Shell has no ``ast`` module available here, so ``.sh`` files are
  scanned as text for ``rev-parse`` and ``--show-toplevel`` appearing
  together on one non-comment line (:func:`scan_shell`), rather than parsed.
  The shell fix is ``scripts/lib/git-root.sh``'s ``git_repo_root`` — the same
  shape as the Python helper, one shared function rather than sixteen inline
  scrubs.
* **The call, not the string.** Only ``subprocess`` calls are inspected in
  Python files, so
  prose that names the flag — this docstring included — is not a finding and
  needs no allowlist entry. The name ``subprocess`` is bound to is resolved
  from the file's own imports, so ``import subprocess as sp`` and
  ``from subprocess import run`` are both caught.
* **``git ls-files`` is not gated**, though the same inherited ``GIT_DIR``
  misleads it. Every current call site passes ``cwd=<root>`` from a root this
  hook already protects, so gating it would flag correct code; the sites fixed
  in #15176 pass ``env=scrubbed_git_env()`` there anyway.

KNOWN GAPS — WHAT THIS DOES **NOT** CATCH
-----------------------------------------
Stated because an unstated gap is worse than a stated one: a guard that reads
as airtight is how the next reader stops checking. Closing these needs
dataflow analysis (Python) or a real shell parse (bash), both out of
proportion to a repository-local lint rule, so they are documented and pinned
by tests rather than half-implemented.

* **Argv built through a variable.** ``cmd = ["git", "rev-parse",
  "--show-toplevel"]`` followed by ``subprocess.run(cmd)`` is not reported: the
  call node's arguments hold a ``Name``, not the string. This is the gap most
  likely to be reached by accident, since it is an ordinary refactor rather
  than an evasion.
* **Wrappers.** A helper that receives the flag from its caller —
  ``def git(*args): subprocess.run(["git", *args])`` — carries no literal at
  the call node either.
* **A shadowed scrub helper.** ``_scrubs`` accepts ``env=`` whose callee is
  *named* ``scrubbed_git_env``; it does not verify the name resolves to
  ``autobot_shared.paths``. A locally defined function of that name satisfies
  it.
* **Shell: a subcommand hidden behind a variable, or a wrapper function.**
  ``scan_shell`` matches the two tokens as literal text, so
  ``FLAG=--show-toplevel; git rev-parse "$FLAG"`` or a local ``toplevel()``
  wrapper is invisible to it — the same class of gap as the Python argv-
  through-a-variable case above, for the same reason (no evaluation of shell
  is attempted here).

The behavioural half of the guard (``repo_tests/git_repo_root_scrub_test.py``
for Python, ``scripts/lib/git-root_test.sh`` for shell) covers what static
analysis cannot: it runs the real resolver under an ambient ``GIT_DIR`` and
asserts the answer.

Exit code:
  0 — every ``--show-toplevel`` call scrubs its environment
  1 — at least one does not (commit/PR blocked)
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable, List, Set, Tuple

# tools/lint/ is not a Python package; ensure the sibling helper is importable
# regardless of invocation mode (script / importlib from tests).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan_helpers import EXCLUDED_DIR_NAMES, iter_python_files  # noqa: E402

#: The canonical scrubbing helper, ``autobot_shared.paths.scrubbed_git_env``.
SCRUB_HELPER = "scrubbed_git_env"

#: The shell-side equivalent, ``scripts/lib/git-root.sh``'s function of the
#: same shape (#15245). A ``.sh`` line naming this is read as scrubbed even
#: though ``scan_shell`` cannot verify the source line was actually reached —
#: same trust boundary as ``_scrubs`` below for the shadowed-helper gap.
SHELL_HELPER = "git_repo_root"

#: The flag whose answer depends on the work tree git thinks it has.
TOPLEVEL_FLAG = "--show-toplevel"

#: ``subprocess`` entry points that start a process.
_SUBPROCESS_CALLS = frozenset({"run", "Popen", "call", "check_call", "check_output"})

#: Files allowed to call ``--show-toplevel`` with an environment that is NOT
#: scrubbed, POSIX-relative to the repository root. Each entry is a call that
#: needs the hook environment *intact* to mean anything.
ALLOWLIST = {
    # The #15176 reproduction. It runs git with GIT_DIR deliberately exported
    # to confirm the defect still reproduces on this git version before
    # asserting that the six sites survive it; scrubbing there would make the
    # suite assert nothing and pass.
    "repo_tests/git_repo_root_scrub_test.py",
    # scripts/lib/git-root.sh IS the scrub -- its one raw call is the
    # implementation `git_repo_root` wraps, run inside a subshell with
    # GIT_ROOT_AMBIENT_VARS unset (#15245).
    "scripts/lib/git-root.sh",
    # #15246 already scrubbed this file's entire process environment
    # (`unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE` up front,
    # ahead of every git call the script makes, not only this one) and that
    # fix is covered by repo_tests/git_hooks_installer_test.py. Converging it
    # onto scripts/lib/git-root.sh would need that test's throwaway fixture
    # -- which copies only this file's bytes, not scripts/lib/ -- to seed the
    # helper too; correct today, tracked as follow-up rather than risked here.
    "scripts/install-git-hooks.sh",
    # The #15245 shell reproduction, same reasoning as the Python one above:
    # it deliberately calls git with GIT_DIR exported, unscrubbed, to prove
    # the defect still reproduces before asserting git_repo_root survives it.
    "scripts/lib/git-root_test.sh",
    # A literal command STRING passed as a test case to the branch-switch
    # guard (#15296) -- not a call this test script itself makes. The guard
    # under test is required to ALLOW exactly this shape.
    ".claude/hooks/block-dangerous-commands_test.sh",
}


def subprocess_names(tree: ast.AST) -> Tuple[Set[str], Set[str]]:
    """``(module aliases, directly imported entry points)`` bound in *tree*.

    Matching the literal ``"subprocess"`` missed two ordinary spellings —
    ``import subprocess as sp`` and ``from subprocess import run`` — so the
    binding is read from the file's own imports instead. ``ast.walk`` is used
    rather than a scan of ``tree.body`` because a ``try:``-guarded or
    function-local import is still an import.

    ``"subprocess"`` is always in the module set. Seeding it can only produce a
    finding, never suppress one, and for a guard that is the safe direction to
    be wrong in.
    """
    modules: Set[str] = {"subprocess"}
    functions: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for alias in node.names:
                if alias.name in _SUBPROCESS_CALLS:
                    functions.add(alias.asname or alias.name)
    return modules, functions


def _is_subprocess_call(node: ast.Call, modules: Set[str], functions: Set[str]) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in _SUBPROCESS_CALLS:
        return isinstance(func.value, ast.Name) and func.value.id in modules
    if isinstance(func, ast.Name):
        return func.id in functions
    return False


def _mentions_toplevel(node: ast.Call) -> bool:
    """True when any string argument of *node* carries the flag."""
    for arg in node.args:
        for child in ast.walk(arg):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                if TOPLEVEL_FLAG in child.value:
                    return True
    return False


def _scrubs(node: ast.Call) -> bool:
    """True when the call passes ``env=scrubbed_git_env(...)``."""
    for keyword in node.keywords:
        if keyword.arg != "env":
            continue
        value = keyword.value
        if isinstance(value, ast.Call):
            func = value.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            return name == SCRUB_HELPER
    return False


def scan(path: Path, repo_root: Path) -> List[Tuple[int, str]]:
    """Return ``(line, message)`` for every unscrubbed ``--show-toplevel`` call."""
    try:
        rel = path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        rel = path.as_posix()
    if rel in ALLOWLIST:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    # Cheap gate before the expensive one: full-repo mode walks every tracked
    # .py file, and AST-parsing all of them costs ~20s where a substring test
    # over the same set costs under one.
    if TOPLEVEL_FLAG not in text:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        # A file that does not parse is another hook's finding, not this one's.
        return []
    modules, functions = subprocess_names(tree)
    findings: List[Tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_subprocess_call(node, modules, functions):
            continue
        if not _mentions_toplevel(node) or _scrubs(node):
            continue
        findings.append(
            (
                node.lineno,
                f"{TOPLEVEL_FLAG} without a scrubbed git environment. A hook exports "
                "GIT_DIR and no GIT_WORK_TREE, so git calls the caller's CWD the work "
                "tree and this answers with the CWD, silently. Use "
                "`from autobot_shared.paths import git_repo_root` (#15176).",
            )
        )
    return findings


def iter_shell_files(args: List[str], repo_root: Path) -> Iterable[Path]:
    """Yield target ``.sh`` files, the same two modes as ``iter_python_files``.

    Not merged into that shared helper: it is hardcoded to the ``.py`` suffix
    and used by several other hooks, so widening it here would widen their
    scans too. A five-line local copy costs less than that blast radius.
    """
    if args:
        for a in args:
            candidate = Path(a)
            if not candidate.is_absolute():
                candidate = repo_root / candidate
            if candidate.is_file() and candidate.suffix == ".sh":
                yield candidate
        return
    for candidate in repo_root.rglob("*.sh"):
        parts = candidate.relative_to(repo_root).parts
        if any(part in EXCLUDED_DIR_NAMES for part in parts):
            continue
        yield candidate


def scan_shell(path: Path, repo_root: Path) -> List[Tuple[int, str]]:
    """Return ``(line, message)`` for every raw ``--show-toplevel`` line.

    Text-based, not a shell parse: there is no ``ast``-equivalent available
    here. A line counts as raw when it holds both ``rev-parse`` and
    ``--show-toplevel`` and is not a full-line comment or a call through
    :data:`SHELL_HELPER` -- the known gaps (a variable-hidden flag, a wrapper
    function) are recorded in this module's docstring rather than chased.
    """
    try:
        rel = path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        rel = path.as_posix()
    if rel in ALLOWLIST:
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    findings: List[Tuple[int, str]] = []
    for line_no, line in enumerate(lines, start=1):
        if line.strip().startswith("#"):
            continue
        if "rev-parse" not in line or TOPLEVEL_FLAG not in line:
            continue
        if SHELL_HELPER in line:
            continue
        findings.append(
            (
                line_no,
                f"{TOPLEVEL_FLAG} without a scrubbed git environment. Source "
                "scripts/lib/git-root.sh and call git_repo_root() (#15245).",
            )
        )
    return findings


def main(argv: List[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    repo_root = Path(__file__).resolve().parents[2]
    py_files: List[Path] = list(iter_python_files(args, repo_root))
    sh_files: List[Path] = list(iter_shell_files(args, repo_root))
    # Vacuity floor: a full-repo run that swept neither language found nothing
    # by losing reach, not by the tree being clean. Only applies in full-repo
    # mode -- pre-commit's explicit argv is legitimately empty of one language
    # on a PR that only touched the other.
    if not args and not (py_files and sh_files):
        print(  # noqa: print
            "[git-toplevel-env-scrubbed] full-repo scan found no .py or .sh files "
            "-- the sweep lost reach rather than the tree being clean.",
            file=sys.stderr,
        )
        return 1
    total = 0
    for path, scanner in [(p, scan) for p in py_files] + [(p, scan_shell) for p in sh_files]:
        for line_no, message in scanner(path, repo_root):
            try:
                rel = path.resolve().relative_to(repo_root).as_posix()
            except ValueError:
                rel = path.as_posix()
            print(f"[git-toplevel-env-scrubbed] {rel}:{line_no}: {message}", file=sys.stderr)  # noqa: print
            total += 1
    if total:
        print(  # noqa: print
            f"\n[git-toplevel-env-scrubbed] {total} unscrubbed call(s). "
            "Resolve the repository root with autobot_shared.paths.git_repo_root() (#15176).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
