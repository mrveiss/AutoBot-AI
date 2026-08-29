#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A test that writes with `git` must scrub the environment first (#15246).

A git hook run in a **worktree** — this repository's entire workflow — is
handed ``GIT_DIR=<main>/.git/worktrees/<name>`` and no ``GIT_WORK_TREE``. A
test fixture that then runs ``git init``/``git add``/``git commit`` in a
``tmp_path`` throwaway repo, with ``subprocess.run``'s default of inheriting
``os.environ``, does not write to that throwaway repo at all: it writes to
whatever ``GIT_DIR`` names, which under the pre-push hook is the pushing
worktree's own git directory. ``autobot_shared/paths_test.py`` did exactly
that under pre-push and dropped 86 tracked files from the live index; the
identical bug then recurred in
``autobot-infrastructure/shared/scripts/hooks/pre-commit-hardcoded-values_test.py``
(#15202/#15282). Both are fixed with
``autobot_shared.paths.scrubbed_git_env()`` (#15243); this hook is the
durable guard against a third recurrence.

SCOPE
-----
* **Test files only** — a path ending ``_test.py`` or whose basename starts
  ``test_``. Production code shelling out to git is a different review (and
  a different fix, since it is not spawned under this repository's own
  pre-push hook the way its own test suite is).
* **Write verbs only.** ``git ls-files`` / ``rev-parse`` / ``diff`` /
  ``log`` etc. against a deliberately real repository root are common and
  correct (``repo_tests/*_anchoring_test.py`` and siblings enumerate the
  tracked tree on purpose); gating every unscrubbed git call would force an
  allowlist entry onto each of them. :data:`WRITE_VERBS` is the verb list a
  sweep of this repository's test suite actually found doing a write
  ambient-env: the issue's own eight (``add``, ``commit``, ``reset``,
  ``checkout``, ``push``, ``rm``, ``mv``, ``stash``) plus ``init`` and
  ``config`` (present in nearly every fixture this sweep fixed — an
  unscrubbed ``git init``/``git config`` in a hook environment reinitializes
  or reconfigures the REAL repository, not the throwaway one) and
  ``worktree``/``merge``/``cherry-pick``/``tag``/``branch``/``update-index``
  (each found live in ``scripts/verify_done_test.py`` or
  ``repo_tests/git_hooks_installer_test.py``).
* **An unresolvable verb is treated as a write.** ``_git(repo, *args)`` —
  the dominant helper shape this sweep found — carries no verb literal at
  its own call site; the caller decides. Refusing to guess safe means every
  call through such a helper is reported unless scrubbed, which is also
  simply true of every site this sweep fixed. A dynamic value elsewhere in
  the argv (``git -C str(root) ls-files "*.py"``) does not trigger this: the
  verb itself is still a literal at a known position, only its *position* has
  to be found by walking past any ``-C``/``-c`` pairs first.
* **A hand-built ``env={"PATH": ..., ...}`` dict with no ``**`` unpacking is
  accepted without calling a recognized helper at all** — it cannot carry an
  ambient variable it was never given, so scrubbing it would verify nothing.

KNOWN GAPS — WHAT THIS DOES **NOT** CATCH
-----------------------------------------
* **A git write embedded in a shell string**, e.g.
  ``subprocess.run(["bash", "-c", "git add . && git commit ..."])``
  (``autobot-infrastructure/shared/scripts/hooks/lib/_common_test.py``'s
  ``_run_in_subshell``, ``repo_tests/release_range_test.py``'s
  ``_run_range_logic``). The verb is inside a string literal, not an argv
  element; both known instances were found and fixed by hand in #15246 --
  this scan does not reach them, and its own test suite pins the gap rather
  than claiming otherwise.
* **Argv built through an intermediate variable**, e.g.
  ``cmd = ["git", "commit", ...]; subprocess.run(cmd)`` — mirrors the same
  documented gap in ``check_git_toplevel_env_scrubbed.py``.
* **A shadowed scrub helper.** ``env=`` is accepted when its value's call
  graph, walked within the same file, contains a call literally named
  ``scrubbed_git_env`` or ``hermetic_git_env`` (the two canonical helpers
  this codebase has today — see ``autobot_shared/paths.py`` and
  ``autobot-backend/code_intelligence/co_change_test.py``). A same-named
  local function that does not actually scrub would satisfy it.

Exit code:
  0 — every git write this scan reached scrubs its environment
  1 — at least one does not, or the full-repo walk reached suspiciously few
      test files (a broken walk reporting zero findings is indistinguishable
      from a clean tree unless reach is checked too)
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import List, Set, Tuple

# tools/lint/ is not a Python package; ensure sibling helpers are importable
# regardless of invocation mode (script / importlib from tests).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_git_toplevel_env_scrubbed import subprocess_names  # noqa: E402
from _scan_helpers import iter_python_files  # noqa: E402

#: The two scrub helpers this codebase has today. See the module docstring's
#: "shadowed scrub helper" gap for what recognising them by name does not
#: verify.
RECOGNIZED_SCRUB_NAMES = frozenset({"scrubbed_git_env", "hermetic_git_env"})

#: `subprocess` entry points that start a process.
_SUBPROCESS_CALLS = frozenset({"run", "Popen", "call", "check_call", "check_output"})

#: See the module docstring's SCOPE section for how each verb earned its
#: place here.
WRITE_VERBS = frozenset(
    {
        "add",
        "commit",
        "reset",
        "checkout",
        "push",
        "rm",
        "mv",
        "stash",
        "init",
        "config",
        "worktree",
        "merge",
        "cherry-pick",
        "tag",
        "branch",
        "update-index",
    }
)

#: Files allowed to run an unscrubbed git write, POSIX-relative to the repo
#: root. Each entry needs the real reason recorded, not just the path.
ALLOWLIST: frozenset[str] = frozenset(
    {
        # An operational CLI tool (argparse, `if __name__ == "__main__":`, no
        # `def test_*` anywhere in it) that deliberately creates real worktrees
        # off `origin/Dev_new_gui` and pushes real branches -- the opposite of
        # a throwaway fixture. Named `test_first_remediation.py` for pytest's
        # own `test_*.py` collection glob, which is exactly why it also
        # matches this guard's naming heuristic; scrubbing it would break the
        # tool it is.
        "scripts/test_first_remediation.py",
    }
)

#: 2063 tracked test files (`*_test.py` / `test_*.py`) measured the day this
#: guard was written. A walk that reaches far fewer has stopped covering the
#: tree, not found a clean one -- see #15184/#15192's TRACKED_PY_FLOOR for
#: the same reasoning applied to a different enumeration.
TEST_FILE_FLOOR = 1500


def _is_test_file(rel_posix: str) -> bool:
    return rel_posix.endswith("_test.py") or Path(rel_posix).name.startswith("test_")


def _is_subprocess_call(node: ast.Call, modules: Set[str], functions: Set[str]) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in _SUBPROCESS_CALLS:
        return isinstance(func.value, ast.Name) and func.value.id in modules
    if isinstance(func, ast.Name):
        return func.id in functions
    return False


#: One slot per argv element: its literal string if the element is a plain
#: string constant, otherwise ``None`` (a dynamic value at a KNOWN position,
#: e.g. ``str(repo)``) -- except a `Starred` element, which is a run-time
#: expansion of unknown length and makes every position after it unknown too.
_STARRED = object()


def _argv_slots(argv: ast.List) -> List[object]:
    slots: List[object] = []
    for element in argv.elts:
        if isinstance(element, ast.Starred):
            slots.append(_STARRED)
        elif isinstance(element, ast.Constant) and isinstance(element.value, str):
            slots.append(element.value)
        else:
            slots.append(None)
    return slots


def _is_git_write(node: ast.Call) -> bool:
    """True when *node*'s first arg is a `git` argv naming a write verb, or
    the verb itself is not statically knowable (see module docstring).

    A dynamic value elsewhere in the argv -- ``git -C str(root) ls-files
    "*.py"`` is the common shape -- does not make the call unresolvable: the
    verb is still the literal at a known position. Only a dynamic or starred
    element AT the verb's position does.
    """
    if not node.args or not isinstance(node.args[0], ast.List):
        return False
    slots = _argv_slots(node.args[0])
    if not slots or slots[0] != "git":
        return False
    index = 1
    while index < len(slots) - 1 and slots[index] in ("-C", "-c"):
        index += 2
    if index >= len(slots):
        return False
    verb = slots[index]
    return verb is None or verb is _STARRED or verb in WRITE_VERBS


def _mentions_scrub_helper(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in RECOGNIZED_SCRUB_NAMES:
                return True
    return False


def _resolved_call_name(value: ast.AST) -> str | None:
    if not isinstance(value, ast.Call):
        return None
    func = value.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)


def trusted_names(tree: ast.Module) -> Set[str]:
    """Local function/variable names that resolve to a recognized scrub
    helper, so `env=<name>` or `env=<name>()` at a call site is accepted
    without re-deriving the call graph there.

    Two passes: a name can be trusted because its OWN body/value mentions
    the helper directly (``def _test_git_env(): return scrubbed_git_env()``),
    or because it is a variable holding the result of a call to an
    ALREADY-trusted local name (``env = _test_git_env()``) -- the shape
    ``pre-commit-hardcoded-values_test.py`` actually uses. One pass over
    Assign nodes cannot see the second kind before the first pass has run.
    """
    trusted: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and _mentions_scrub_helper(node):
            trusted.add(node.name)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not (_mentions_scrub_helper(node.value) or _resolved_call_name(node.value) in trusted):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                trusted.add(target.id)
    return trusted


def _is_unpack_free_dict(value: ast.AST) -> bool:
    """True for `{"PATH": ..., "HOME": ...}` -- a dict literal with no `**`
    unpacking anywhere. It cannot carry an ambient variable it was never
    given, so it needs no call to a recognized helper to be safe."""
    return isinstance(value, ast.Dict) and None not in value.keys


def _env_is_scrubbed(node: ast.Call, trusted: Set[str]) -> bool:
    for keyword in node.keywords:
        if keyword.arg != "env":
            continue
        value = keyword.value
        if _mentions_scrub_helper(value) or _is_unpack_free_dict(value):
            return True
        if isinstance(value, ast.Name):
            return value.id in trusted
        return _resolved_call_name(value) in trusted
    return False


def scan(path: Path, repo_root: Path) -> List[Tuple[int, str]]:
    """Return `(line, message)` for every unscrubbed git write in *path*."""
    try:
        rel = path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        rel = path.as_posix()
    if rel in ALLOWLIST or not _is_test_file(rel):
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    if "git" not in text:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    modules, functions = subprocess_names(tree)
    trusted = trusted_names(tree)
    findings: List[Tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_subprocess_call(node, modules, functions):
            continue
        if not _is_git_write(node) or _env_is_scrubbed(node, trusted):
            continue
        findings.append(
            (
                node.lineno,
                "git write without a scrubbed environment. A hook exports GIT_DIR "
                "and no GIT_WORK_TREE, so this can write to the real repository "
                "instead of the fixture's throwaway one (#15246). Pass "
                "env=scrubbed_git_env() from autobot_shared.paths.",
            )
        )
    return findings


def scan_repo(repo_root: Path) -> Tuple[int, List[Tuple[Path, int, str]]]:
    """`(test files reached, findings)` across the whole tracked tree."""
    reached = 0
    findings: List[Tuple[Path, int, str]] = []
    for path in iter_python_files([], repo_root):
        try:
            rel = path.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            rel = path.as_posix()
        if not _is_test_file(rel):
            continue
        reached += 1
        for line_no, message in scan(path, repo_root):
            findings.append((path, line_no, message))
    return reached, findings


def main(argv: List[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    repo_root = Path(__file__).resolve().parents[2]

    if args:
        total = 0
        for arg in args:
            path = Path(arg)
            for line_no, message in scan(path, repo_root):
                _report(path, repo_root, line_no, message)
                total += 1
        return 1 if total else 0

    reached, findings = scan_repo(repo_root)
    if reached < TEST_FILE_FLOOR:
        print(
            f"[git-write-env-scrubbed] only reached {reached} test files, floor is "
            f"{TEST_FILE_FLOOR} -- the walk is broken, not the tree clean",
            file=sys.stderr,
        )
        return 1
    for path, line_no, message in findings:
        _report(path, repo_root, line_no, message)
    if findings:
        print(  # noqa: print
            f"\n[git-write-env-scrubbed] {len(findings)} unscrubbed git write(s). "
            "Pass env=scrubbed_git_env() (#15246).",
            file=sys.stderr,
        )
        return 1
    return 0


def _report(path: Path, repo_root: Path, line_no: int, message: str) -> None:
    try:
        rel = path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        rel = path.as_posix()
    print(f"[git-write-env-scrubbed] {rel}:{line_no}: {message}", file=sys.stderr)  # noqa: print


if __name__ == "__main__":
    sys.exit(main())
