# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A guard that walks the repo root must enumerate through git (#15955).

This repository keeps git worktrees **inside** the working copy —
`.worktrees/<name>/` and `.claude/worktrees/<name>/`. A `REPO_ROOT.rglob(...)`
therefore reaches other checkouts of this same repository, at revisions nobody
chose, and counts their files as if they were the tree under test.

**Three guards were affected, in two different shapes:**

* `systemd_heredoc_expansion_test.py` and `slm_frontend_publish_contract_test.py`
  carried a hand-written prune list that named `.worktrees/` and not
  `.claude/worktrees/` — an *incomplete* list;
* `test_updater_reconciles_credentials_12907.py` had **no prune list at all**.

So a check keyed on "does the prune list look complete?" would have missed the
third. **This keys on the walk instead**: an enumeration rooted at the repository root
must either come from `git ls-files` — which cannot enter another checkout,
because it reads an index rather than a filesystem — or exclude **both** nested
roots. Naming one is the defect; naming neither is the other defect; the check
does not care which.

WHY NINE OTHER GUARDS ARE FINE, AND WHY THAT IS THE ARGUMENT. Nine files in this
repository independently contain the same four-element list —
`{"node_modules", ".worktrees", ".claude", ".git"}` — typed in one at a time. It
is correct in those nine *because people keep retyping it*, and wrong in exactly
the two where the copy was not finished. A rule that has to be re-entered by
hand at every site is not a rule; this test is the alternative.

CI WAS NEVER AFFECTED, and that is the point rather than a mitigation. CI checks
out clean, so the walk and the index agree there; in a clean worktree
`rglob("*.sh")` returns exactly the 216 tracked files. **The failure appears only
on a developer machine, which is where nobody is looking** — a guard that answers
differently depending on who runs it is the one thing a reach floor cannot
tolerate.
"""

from __future__ import annotations

import ast
from typing import List, Tuple

from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

REPO_ROOT = repo_root()

#: Names a walk is rooted at when it is rooted at the repository itself. A walk
#: from a SUBDIRECTORY cannot reach the nested checkouts and is not in scope.
#: #15926: `repo_root` was missing, and it is the name #15925 made canonical --
#: so this detector's blind spot GREW as that migration landed. It hid a real
#: one: `check_git_toplevel_env_scrubbed.iter_shell_files` did
#: `repo_root.rglob("*.sh")` and read 219 files from other checkouts. Keying on
#: how a root is NAMED is the defect #15925 exists to remove, committed here by
#: the guard against it; the name list is a stopgap until the population comes
#: from `repo_root()` itself.
_ROOT_NAMES = {"REPO_ROOT", "_REPO_ROOT", "ROOT", "_ROOT", "repo_root"}

#: ``glob`` is here for the ``glob("**/…")`` form only -- the branch below
#: requires a literal ``**`` pattern, so a single-level glob is still ignored.
#: It had to be added: an earlier `attr not in _WALK_ATTRS` filter dropped every
#: `glob` call BEFORE the branch that handles it, so the detector named the
#: shape and could not reach it. Second time in this file.
#:
#: Recursive enumerations only. A single-level ``glob("autobot-*/x")`` cannot
#: descend into a nested checkout, and flagging it produced three false
#: positives on guards that are correct -- `deployed_workspace_packages`,
#: `ambient_git_vars_mirror` and `comment_line_number_citations` all glob an
#: anchored pattern. A detector with false positives gets muted, so the
#: narrowing is the point rather than a concession.
_WALK_ATTRS = {"rglob", "iterdir", "walk", "glob"}

#: Directories whose Python is not repository tooling.
_SKIP_TREES = ("autobot-frontend/", "autobot-slm-frontend/", ".worktrees/", ".claude/")

#: Below this the sweep collapsed rather than the tree being clean. Bound to
#: files parsed, never to violations found.
_MIN_FILES_PARSED = 300

Finding = Tuple[str, int, str]


def _tooling_files() -> List[str]:
    names = tracked_paths(REPO_ROOT, "repo_tests/*.py", "tools/*.py", "scripts/*.py", "pipeline-scripts/*.py")
    return [n for n in names if not n.startswith(_SKIP_TREES)]


def root_walks_in(source: str) -> List[Tuple[int, str]]:
    """``(line, expression)`` for every enumeration rooted at the repo root."""
    try:
        return root_walks_in_node(ast.parse(source))
    except SyntaxError:
        return []


def root_walks_in_node(tree) -> List[Tuple[int, str]]:
    """The same, over an already-parsed node (a function body, say)."""
    found: List[Tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in _WALK_ATTRS:
            continue
        base = node.func.value
        # Two shapes, and the detector missed the second until review caught it:
        #
        #   REPO_ROOT.rglob(...)   receiver IS the root
        #   os.walk(REPO_ROOT)     receiver is `os`, the root is an ARGUMENT
        #
        # `walk` was in `_WALK_ATTRS` from the first draft, so this detector
        # named a call shape it could not see -- the same defect it exists to
        # find, in itself.
        # `glob` is deliberately excluded here: it is recursive only with a `**`
        # pattern, handled below. Letting the receiver branch claim it flagged
        # three guards that glob an ANCHORED pattern and cannot descend.
        if node.func.attr != "glob" and isinstance(base, ast.Name) and base.id in _ROOT_NAMES:
            found.append((node.lineno, ast.unparse(node)[:90]))
            continue
        if node.func.attr == "walk" and any(
            isinstance(a, ast.Name) and a.id in _ROOT_NAMES
            # `os.walk(top=REPO_ROOT)`: `node.args` excludes keyword arguments,
            # so the keyword form was invisible.
            for a in list(node.args) + [k.value for k in node.keywords if k.arg in (None, "top")]
        ):
            found.append((node.lineno, ast.unparse(node)[:90]))
            continue
        # `root.glob("**/…")` recurses without being `rglob`, and the receiver is
        # often a PARAMETER named `root` defaulting to the repository root.
        # `check_ci_system_package_provisioning._test_files` is exactly that and
        # reached 4,644 test files of which 3,251 -- 70% -- were another
        # checkout's. Only `**` patterns: a plain `glob("*.py")` sees one level.
        if node.func.attr == "glob" and isinstance(base, ast.Name) and base.id in _ROOT_NAMES | {"root", "base"}:
            # `pattern` is positional-or-keyword, so `root.glob(pattern="**/*.py")`
            # recurses identically and was invisible while only `args[0]` was read.
            kw = next((k.value for k in node.keywords if k.arg == "pattern"), None)
            first = node.args[0] if node.args else kw
            if isinstance(first, ast.Constant) and isinstance(first.value, str) and "**" in first.value:
                found.append((node.lineno, ast.unparse(node)[:90]))
    return found


#: Both nested-checkout roots. A prune naming only one is the defect that broke
#: two guards, so a file must exclude BOTH to be safe without git.
_NESTED_ROOTS = (".worktrees", ".claude")

#: The structural test: a nested checkout's ``.git`` is a FILE holding a
#: ``gitdir:`` pointer, where the primary checkout's is a directory. A guard that
#: must walk the filesystem -- `no_duplicate_dict_keys_test.py` derives its tree
#: list from a walk ON PURPOSE, so that git and the filesystem can disagree --
#: uses this instead of a name list.
_STRUCTURAL_DETECTOR = "is_file()"  # matched together with ".git" below


def _pruned_names(tree) -> set:
    """String constants appearing inside collection literals in *tree*.

    Read from the literals rather than from the file text, because a substring
    check over the source is satisfied by a **comment**. The first version of
    this function did `all(root in source ...)` and both mutations survived: I
    reverted a guard to a bare `rglob` and the file still mentioned `.claude` in
    prose, so it was still called safe. A detector keyed on text is not a
    classification (#15955).
    """
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
            names |= {e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return names


def _detects_nested_checkout(tree) -> bool:
    """Whether *tree* contains a real call testing whether some ``.git`` is a file.

    An AST check, not a text one. My first two attempts matched strings anywhere
    in the source — `"git ls-files" in source`, then `'".git"' in source and
    "is_file()" in source` — and **both mutations survived**, because this file's
    own docstrings contain those words and the guards' own unrelated
    `entry.is_file()` calls contain the other. A detector keyed on text is
    satisfied by prose about the detector.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "attr", None) or getattr(func, "id", None)
        if name not in {"is_file", "isfile"}:
            continue
        rendered = ast.unparse(node)
        if '".git"' in rendered or "'.git'" in rendered:
            return True
    return False


def _is_safe(func, module) -> bool:
    """Whether a file may walk the repo root. Two ways.

    A third used to sit above these: "the function also calls ``git ls-files``".
    It was wrong in a way that is easy to miss -- a git call proves the function
    enumerates through git SOMEWHERE, not that THIS walk does. A function that
    reads the index and then separately does ``REPO_ROOT.rglob(...)`` was exempted
    whole, and the rglob still entered every nested checkout. Presence of the
    right call is not absence of the wrong one. Removing it flagged nothing new,
    so it was protecting no guard while covering that hole.

    * detect nested checkouts structurally (a worktree's ``.git`` is a FILE);
    * prune **both** nested roots by name, *in an actual collection literal*.
      Nine guards do this correctly and rewriting them would be churn for no
      behaviour change, so it is accepted rather than required to change.

    Naming one root is not safe: that was the state of two of the guards this
    issue fixes, and a third named neither.
    """
    # LITERALS are checked against the module, because a prune set is a
    # module-level constant by convention and requiring it inside the function
    # would flag nine correct guards.
    # Structural detection is checked against the MODULE, like the literals: a
    # guard may factor it into a helper (`_inside_nested_checkout(path)`), and
    # requiring the call inside the walking function flagged one that does
    # exactly that.
    if _detects_nested_checkout(module):
        return True
    pruned = _pruned_names(module)
    return any(".worktrees" in n for n in pruned) and any(".claude" in n for n in pruned)


def _sweep() -> Tuple[List[Finding], int]:
    findings: List[Finding] = []
    seen: set = set()
    parsed = 0
    for name in _tooling_files():
        try:
            source = (REPO_ROOT / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        parsed += 1
        # PER FUNCTION, not per file. A file-level check exempted
        # `no_duplicate_dict_keys_test.py`, which calls `git ls-files` in one
        # function and walks the filesystem in another -- deliberately, so the
        # two enumerations can disagree. Asking "does this file mention git?"
        # passed its walk on the strength of an unrelated function.
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
                continue
            walks = root_walks_in_node(func)
            if not walks or _is_safe(func, tree):
                continue
            # De-duplicated: `ast.walk(Module)` already descends into every
            # function, so each finding is seen once at module level and again
            # in its own function.
            findings += [(name, line, expr) for line, expr in walks if (name, line) not in seen]
            seen |= {(name, line) for line, _ in walks}
    return findings, parsed


_FINDINGS, _PARSED = _sweep()


def test_the_sweep_parsed_the_tooling() -> None:
    """Runs first: an empty sweep finds no violation either."""
    assert _PARSED >= _MIN_FILES_PARSED, (
        f"parsed only {_PARSED} tooling file(s) (floor {_MIN_FILES_PARSED}) — the sweep "
        "broke, so a clean result below asserts nothing."
    )


def test_no_guard_walks_the_repo_root_without_git() -> None:
    assert not _FINDINGS, (
        f"enumerations rooted at the repository root, not sourced from git "
        f"({_PARSED} tooling files parsed):\n"
        + "\n".join(f"  {name}:{line}  {expr}" for name, line, expr in _FINDINGS)
        + "\n\nThis repository keeps git worktrees INSIDE the working copy, so such a walk "
        "reaches other checkouts of itself. Use `git ls-files` under `scrubbed_git_env()` "
        "— it reads an index, not a filesystem, and cannot enter another checkout (#15955)."
    )


def test_the_detector_reports_a_bare_root_walk() -> None:
    """The fixture that SHOULD trip it — the shape with no prune list at all."""
    assert root_walks_in('for p in REPO_ROOT.rglob("*.yml"):\n    pass\n') == [(1, "REPO_ROOT.rglob('*.yml')")]


def test_the_detector_reports_a_walk_with_an_incomplete_prune() -> None:
    """The other shape. A prune list does not make the walk safe, so the
    detector must not treat one as an excuse — both affected guards had one."""
    source = 'EX = {".worktrees"}\nfor p in _REPO_ROOT.rglob("*.sh"):\n    pass\n'

    assert root_walks_in(source) == [(2, "_REPO_ROOT.rglob('*.sh')")]


def test_a_subdirectory_walk_is_not_reported() -> None:
    """The contrast case. `_ANSIBLE_ROOT.rglob(...)` cannot reach the nested
    checkouts, and flagging it would make this guard unfixable noise —
    ~30 such walks exist and all are correct."""
    assert root_walks_in('for p in _ANSIBLE_ROOT.rglob("*.yml"):\n    pass\n') == []


def test_a_git_sourced_enumeration_is_not_reported() -> None:
    """The other contrast: the fix itself must not trip the guard."""
    findings, _ = _sweep()
    offenders = {name for name, _, _ in findings}

    assert "repo_tests/repo_root_walks_use_git_15955_test.py" not in offenders


def test_the_detector_reports_os_walk_with_the_root_as_an_argument() -> None:
    """The shape the first draft named in `_WALK_ATTRS` and could not see.

    `os.walk(REPO_ROOT)` puts the root in an ARGUMENT, not in the receiver, so a
    check keyed on the receiver misses it entirely — a detector blind to a call
    shape it lists.
    """
    assert root_walks_in("for a, b, c in os.walk(REPO_ROOT):\n    pass\n") == [(1, "os.walk(REPO_ROOT)")]


def test_the_detector_ignores_os_walk_of_a_subdirectory() -> None:
    """The contrast: `os.walk(_ANSIBLE_ROOT)` cannot reach a nested checkout."""
    assert root_walks_in("for a, b, c in os.walk(_ANSIBLE_ROOT):\n    pass\n") == []


def test_the_detector_reports_os_walk_with_a_top_keyword() -> None:
    """`node.args` excludes keywords, so `os.walk(top=REPO_ROOT)` was invisible."""
    assert root_walks_in("for a, b, c in os.walk(top=REPO_ROOT):\n    pass\n") == [(1, "os.walk(top=REPO_ROOT)")]


def test_the_detector_reports_a_recursive_glob_on_a_root_parameter() -> None:
    """`root.glob("**/x")` recurses without being `rglob`, and `root` is commonly
    a parameter defaulting to the repository root."""
    assert root_walks_in('for p in root.glob("**/*_test.py"):\n    pass\n') == [(1, "root.glob('**/*_test.py')")]


def test_the_detector_ignores_a_single_level_glob() -> None:
    """The contrast: `glob("*.py")` sees one level and cannot enter a checkout.

    Without this, adding `glob` to `_WALK_ATTRS` would flag every anchored glob
    in the tree -- which is what made me exclude `glob` entirely in an earlier
    draft, and is why the `**` restriction is the point rather than a detail.
    """
    assert root_walks_in('for p in root.glob("*.py"):\n    pass\n') == []


def test_the_detector_ignores_os_walk_of_a_subdirectory_keyword() -> None:
    """The contrast for the keyword form."""
    assert root_walks_in("for a, b, c in os.walk(top=_ANSIBLE_ROOT):\n    pass\n") == []


def test_the_detector_reports_a_recursive_glob_with_a_pattern_keyword() -> None:
    """`Path.glob`'s `pattern` is positional-or-keyword; both forms recurse.

    Reading only `node.args[0]` saw the positional form and missed this one --
    the same keyword blind spot already fixed for `os.walk(top=...)`, left in
    place one branch below it. Writing the fix for one call shape and not its
    neighbour is the miss, not the shape itself.
    """
    src = 'for p in root.glob(pattern="**/*_test.py"):\n    pass\n'
    assert root_walks_in(src) == [(1, "root.glob(pattern='**/*_test.py')")]


def test_the_detector_ignores_a_single_level_glob_by_keyword() -> None:
    """Contrast: the keyword branch must keep the `**` restriction, not bypass it.

    Without this, "handle the keyword form" could be satisfied by reporting
    every keyword glob regardless of pattern -- passing the test above while
    flagging anchored single-level globs across the tree.
    """
    assert root_walks_in('for p in root.glob(pattern="*.py"):\n    pass\n') == []


def _safety_of(source: str) -> bool:
    """`_is_safe` for the first function in *source* — the layer the rule lives at.

    `root_walks_in` finds walks; `_is_safe` decides which are excused. A contrast
    written against the finder cannot see an exemption change at all: my first
    attempt at the test below passed identically with and without the exemption
    restored, because it never reached this function.
    """
    tree = ast.parse(source)
    func = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    return _is_safe(func, tree)


def test_a_git_call_does_not_exempt_a_separate_walk_in_the_same_function() -> None:
    """The contrast for the removed exemption (#15962 review).

    Reading the index and walking the tree are different acts. A function may do
    both, and the walk is exactly as dangerous as it would be alone. Keyed on
    "does this function invoke git", the rglob below was excused.
    """
    src = (
        "def collect():\n"
        "    tracked = subprocess.run(['git', 'ls-files', '*.py'], cwd=REPO_ROOT)\n"
        "    extra = list(REPO_ROOT.rglob('*.py'))\n"
        "    return tracked, extra\n"
    )
    assert root_walks_in(src) == [(3, "REPO_ROOT.rglob('*.py')")]
    assert not _safety_of(src), (
        "a `git ls-files` call in the same function excused a separate rglob of the "
        "repository root. Presence of the right call is not absence of the wrong one."
    )


def test_a_module_that_prunes_both_nested_roots_is_still_excused() -> None:
    """The other half: removing the exemption must not start flagging correct guards.

    Without this, "remove the exemption" is satisfied by excusing nothing, which
    would flag the nine guards that prune by name and were deliberately accepted.
    """
    src = "_PRUNED = {'.worktrees', '.claude'}\n" "def collect():\n" "    return [p for p in REPO_ROOT.rglob('*.py')]\n"
    assert root_walks_in(src), "fixture must contain a walk for this to mean anything"
    assert _safety_of(src)


def test_the_detector_sees_the_canonical_lowercase_root_name() -> None:
    """`repo_root` is what #15925 standardised, so it must be detected.

    An uppercase-only name list got blinder as that migration landed: every
    guard moving to `repo_root()` moved toward a spelling this detector did not
    recognise.
    """
    assert root_walks_in('for p in repo_root.rglob("*.sh"):\n    pass\n') == [(1, "repo_root.rglob('*.sh')")]
    assert root_walks_in("for e in repo_root.iterdir():\n    pass\n") == [(1, "repo_root.iterdir()")]


def test_a_subdirectory_named_root_is_still_not_reported() -> None:
    """Contrast: the loop variable of `os.walk` is conventionally `root`.

    Without this, widening the name set is satisfied by flagging every
    `for root, dirs, files in os.walk(subdir)` body in the tree.
    """
    assert root_walks_in("for root, dirs, files in os.walk(SUBDIR):\n    p = root\n") == []
