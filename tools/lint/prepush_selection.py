# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which tests a push must run, and why (#16711).

``tools/git-hooks/pre-push`` used to decide what was a test with ``*_test.py`` alone.
pytest's ``python_files`` also collects ``test_*.py`` (the ``tests/`` convention across
both backends), so a changed ``tests/test_x.py`` was treated as production code, got
no sibling, and never ran before the push. #16700 paid a CI cycle for it.

The patterns now come from ``pytest.ini`` itself. The hook pipes the changed paths in
and gets back one ``path<TAB>reason`` line per test, so the push log says why each test
runs.
"""

from __future__ import annotations

import ast
import fnmatch
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Callable, Dict, Mapping, Sequence

#: Where the glob-declared guard inputs are recorded (#15900).
#:
#: The record moved out of `glob_declared_reads_15900_test.py` when that file
#: reached the 600-line ceiling (#14781), and this constant did not follow it --
#: the parse then found the name absent and returned `{}`, which
#: `prepush_selection_test.py` caught because it asserts the parse found
#: SOMETHING rather than iterating whatever came back. Without that assertion
#: pre-push selection would have silently stopped consulting the record and
#: every glob-declared guard would have dropped out of selection with nothing
#: failing to say so.
#:
#: Still read as DATA via `ast` rather than imported, but the reason changed
#: with the move and the old one is no longer true. The record's new home
#: imports nothing but `__future__`, so there is no pytest to pull into the hook
#: and no cycle to close. What remains is that a git hook must not depend on
#: `repo_tests` being importable -- a missing `__init__`, a broken sibling or an
#: interpreter without pytest would take the hook down with it, and the hook's
#: job is to run when the tree is in a bad state.
GLOB_RECORD = "repo_tests/_glob_declared_uncovered.py"
_RECORD_NAME = "GLOB_DECLARED_UNCOVERED"

#: Guards that police the guards. They enumerate every tracked file, so a NEW
#: guard is checked by them and co-located with neither, which is why adding one
#: passed pre-push and failed CI twice on #17241.
#:
#: Named rather than sniffed: 45 guards import `tracked_paths` and running all of
#: them on every push costs most of a shard, while the heuristics that narrow
#: that set do not cleanly isolate these two. A short list with a reason is
#: honest about being a list; `exists()` below drops an entry that is renamed
#: away, so it fails open rather than blocking a push on its own staleness.
GUARDS_POLICING_GUARDS = {
    "repo_tests/glob_declared_reads_15900_test.py": "a new guard must record the globs it declares",
    "repo_tests/one_repo_root_spelling_15925_test.py": "a new guard must call repo_root(), not re-derive it",
}


def glob_declared_guards(record_text: str) -> Dict[str, frozenset]:
    """``glob -> the guards that declare it``, parsed out of the #15900 record.

    A guard that scans the tree by glob is co-located with nothing, so the
    co-location rule below never selects it however much you change. Every red
    on #17241 was one of these: the convention was real, the guard was real, and
    the push could not see either until CI ran ten minutes later.
    """
    try:
        module = ast.parse(record_text)
    except (SyntaxError, ValueError):
        # ValueError, not only SyntaxError: a null byte in the record makes
        # ast.parse raise ValueError, which would propagate out of main() and
        # fail EVERY push -- the opposite of this helper's contract.
        return {}
    for node in module.body:
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
        if target != _RECORD_NAME or node.value is None:
            continue
        try:
            recorded = ast.literal_eval(node.value)
        except (ValueError, TypeError, SyntaxError):
            return {}
        # Valid Python of the WRONG SHAPE parses fine and then explodes on
        # .items() or the tuple unpack, which would abort the hook rather than
        # degrade -- this helper exists to fail open, and a record that changes
        # shape must cost a selection, never a push.
        if not isinstance(recorded, dict):
            return {}
        declared: Dict[str, frozenset] = {}
        for glob, value in recorded.items():
            if not isinstance(glob, str) or not isinstance(value, (tuple, list)) or not value:
                continue
            guards = value[0]
            if isinstance(guards, (set, frozenset, tuple, list)):
                declared[glob] = frozenset(str(g) for g in guards)
        return declared
    return {}


def _guards_reading(path: str, declared: Mapping[str, frozenset]) -> list:
    """Guards whose declared glob matches *path*, by basename or by full path."""
    name = PurePosixPath(path).name
    matched: set = set()
    for glob, guards in declared.items():
        if fnmatch.fnmatchcase(name, glob) or fnmatch.fnmatchcase(path, glob):
            matched |= set(guards)
    return sorted(matched)


def pytest_settings(ini_text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(python_files patterns, --ignore prefixes)`` from the text of ``pytest.ini``."""
    found = re.search(r"(?m)^python_files\s*=\s*(.+?)\s*$", ini_text)
    patterns = tuple(found.group(1).split()) if found else ("test_*.py", "*_test.py")
    return patterns, tuple(re.findall(r"(?m)^\s*--ignore=(\S+)", ini_text))


def pytest_testpaths(ini_text: str) -> tuple[str, ...]:
    """The ``testpaths`` roots from the text of ``pytest.ini``: where CI and a bare pytest collect (#18288).

    A ``test_*.py`` outside them (the live probes under ``shared/scripts/analysis``) is never
    collected, so running it as a push gate runs a live probe against the developer's machine.
    """
    block = re.search(r"(?ms)^testpaths\s*=\s*(.*?)(?=^\S)", ini_text)
    if not block:
        return ()
    lines = (line.split("#", 1)[0].strip() for line in block.group(1).splitlines())
    return tuple(line for line in lines if line)


def is_test(path: str, patterns: Sequence[str]) -> bool:
    """Whether pytest collects *path*: its basename matches a ``python_files`` pattern."""
    return any(fnmatch.fnmatchcase(PurePosixPath(path).name, pattern) for pattern in patterns)


#: Cheap whole-tree guards run on EVERY push (#18808, #16715). Each fires on the tree's shape, so
#: the change that trips it is rarely its sibling or a recorded glob -- trains 30-33 surfaced nine
#: such trips only at train time. Kept to guards measured cheap in .test_durations (about 85s
#: serial in all, 2026-10-23); a costly whole-tree guard is reached through its declared scan
#: roots instead (see declared_roots).
ALWAYS_RUN = {
    "repo_tests/isolated_git_env_guard_18940_test.py": "whole-tree: test git-repo fixtures (#18940)",
    "repo_tests/python_file_size_ratchet_test.py": "whole-tree: python file-size ceilings",
    "repo_tests/shell_file_size_ratchet_test.py": "whole-tree: shell file-size ceilings",
    "repo_tests/frontend_file_size_ratchet_test.py": "whole-tree: frontend file-size ceilings",
    "repo_tests/python_filter_covers_its_guards_test.py": "whole-tree: the python filter covers every guard input",
    "repo_tests/filters_moved_intact_18208_test.py": "whole-tree: the change filters moved intact into ci.yml (#18208)",
    "repo_tests/secrets_baseline_reasons_guard_test.py": "whole-tree: every secrets-baseline entry has a reason",
    "repo_tests/reach_scope_claim_17844_test.py": "whole-tree: reach declarations match their scopes",
    "repo_tests/guard_reach_meta_test.py": "whole-tree: every tree-scanning guard has a reach floor",
    "repo_tests/one_git_enumeration_15926_test.py": "whole-tree: one git enumeration (#18808: #18802)",
    "repo_tests/regex_concept_fork_guard_18093_test.py": "whole-tree: regex concept forks (#18808: #18802)",
    "repo_tests/frontend_api_contract_ratchet_test.py": "whole-tree: frontend API contract (#18808: #18755)",
    "repo_tests/raw_palette_class_ratchet_14580_test.py": "whole-tree: raw palette classes (#18808: #18797)",
    "repo_tests/docstring_restatement_guard_17165_test.py": "whole-tree: docstring restatement (#18808: #18742)",
    "repo_tests/remote_command_quoting_18359_test.py": "whole-tree: remote command quoting (#18808: #18782)",
    "repo_tests/env_var_bare_cast_test.py": "whole-tree: bare env-var casts and their baseline",
    "repo_tests/symbol_fork_ratchet_17312_test.py": "whole-tree: symbol forks and their baseline",
    "pipeline-scripts/check_baseline_no_growth_test.py": "the baseline no-growth check",
}


REACH_ROOTS_RECORD = "repo_tests/_reach_roots_record.py"


def declared_roots(record_text: str) -> Dict[str, tuple]:
    """``{guard: roots}`` from the text of REACH_ROOTS_RECORD, read as DATA, never imported.

    The hook must not depend on repo_tests being importable (see GLOB_RECORD). The record is
    computed from the live registry (repo_tests/_reach_roots.py), because a parse of the
    ``declare(`` calls missed every ``roots=`` written as a constant (#19312 review). An
    unparseable record selects nothing extra, the same degradation as the glob record.
    """
    try:
        tree = ast.parse(record_text)
    except SyntaxError:
        return {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "REACH_ROOTS" for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except ValueError:
                return {}
            return {str(k): tuple(v) for k, v in value.items()}
    return {}


def _under_root(path: str, roots: Sequence[str]) -> bool:
    """Whether *path* falls under a declared root. Roots are raw prefixes, the way
    ``_reach_scope.scope_complaint`` checks them, so ``autobot-`` covers every ``autobot-*`` tree."""
    return any(path.startswith(root) for root in roots)


def _under(path: str, prefixes: Sequence[str]) -> bool:
    """Whether *path* is one of *prefixes* or lies below one."""
    return any(path == p.rstrip("/") or path.startswith(p.rstrip("/") + "/") for p in prefixes)


def select(
    changed: Sequence[str],
    *,
    patterns: Sequence[str],
    ignores: Sequence[str],
    exists: Callable[[str], bool],
    declared_globs: Mapping[str, frozenset] | None = None,
    testpaths: Sequence[str] = (),
    roots: Mapping[str, tuple] | None = None,
    references: Mapping[str, Sequence[str]] | None = None,
    always: Mapping[str, str] | None = None,
) -> Dict[str, str]:
    """The tests to run for *changed*, each mapped to the reason it was chosen.

    A changed test runs itself; a changed module runs its co-located ``foo_test.py``.
    A test that no longer exists is never selected, because pytest treats a vanished path as
    a collection error (#15751). Neither is one that pytest.ini ignores, because pytest
    collects a path named on its command line even when ``--ignore`` covers it (#16019).

    A changed path ALSO runs every guard that declares a glob matching it. Those guards
    are co-located with nothing, so the two rules above never reach them: they scan the
    tree and fire on its shape. That is the whole class #17241 burned four CI cycles on.

    When *testpaths* is given, a test outside every root is never selected: pytest would not
    collect it (#18288), so the push would run a file no CI shard runs.
    """
    chosen: Dict[str, str] = {}
    declared = declared_globs or {}

    def add(test: str, why: str) -> None:
        if test not in chosen and exists(test) and not _under(test, ignores):
            chosen[test] = why

    if changed:
        for guard, why in (always or {}).items():
            add(guard, why)
    for guard, scanned in (roots or {}).items():
        hit = next((p for p in changed if _under_root(p, scanned)), None)
        if hit:
            add(guard, f"scans {', '.join(scanned)}; {hit} changed")
    for path, tests in (references or {}).items():
        for test in tests:
            add(test, f"names {path}")
    if any(p.startswith("repo_tests/") and p.endswith(".py") for p in changed):
        for guard, why in GUARDS_POLICING_GUARDS.items():
            add(guard, f"a repo_tests file changed; {why}")
    for path in changed:
        for guard in _guards_reading(path, declared):
            add(guard, f"declares a glob matching {path}")
    for path in changed:
        if is_test(path, patterns):
            test, reason = path, "changed"
        elif path.endswith(".py"):
            test, reason = f"{path[:-3]}_test.py", f"co-located with {path}"
        else:
            continue
        collected = not testpaths or _under(test, testpaths)
        if test not in chosen and collected and exists(test) and not _under(test, ignores):
            chosen[test] = reason
    return chosen


def tests_naming(root: Path, changed: Sequence[str], patterns: Sequence[str]) -> Dict[str, list]:
    """``{changed path: [test files that name it]}`` (#16715 AC1).

    A test that slices a template or reads a YAML file names it by its repo path, or by its
    basename when that basename is unique in the tree (``main.yml`` is not; a template's name
    usually is). Python paths too: ``frontmatter_test`` lists the modules it polices by path, and
    #18790 changed one of them (#18808). One ``git grep -F`` per changed path, over test files.
    """
    from autobot_shared.paths import scrubbed_git_env  # noqa: PLC0415 - hook-time only
    from tools.lint._scan_helpers import tracked_paths  # noqa: PLC0415 - hook-time only

    targets = list(changed)
    if not targets:
        return {}
    # An empty enumeration raises (EmptyEnumeration) instead of returning {}: selecting fewer
    # tests in silence is the failure this function exists to prevent (#19312 review). main()
    # turns the raise into a failed selection, which blocks the push.
    tracked = tracked_paths(root)
    basenames: Dict[str, int] = {}
    for rel in tracked:
        name = rel.rsplit("/", 1)[-1]
        basenames[name] = basenames.get(name, 0) + 1
    specs = [f":(glob)**/{pattern}" for pattern in patterns]
    found: Dict[str, list] = {}
    for path in targets:
        name = path.rsplit("/", 1)[-1]
        needles = [path] + ([name] if basenames.get(name) == 1 and name != path else [])
        args = ["git", "-C", str(root), "grep", "-l", "-F"]
        for needle in needles:
            args += ["-e", needle]
        out = subprocess.run([*args, "--", *specs], capture_output=True, text=True, timeout=60, env=scrubbed_git_env())
        if out.returncode not in (0, 1):  # 1 is "no match"; anything else is a failed search
            raise RuntimeError(f"git grep for {path!r} failed (exit {out.returncode}): {out.stderr.strip()}")
        hits = [line for line in out.stdout.splitlines() if line and line != path]
        if hits:
            found[path] = hits
    return found


def format_selection(chosen: Mapping[str, str]) -> str:
    """One ``test<TAB>reason`` line per selected test: the hook's input and its log."""
    return "".join(f"{test}\t{reason}\n" for test, reason in chosen.items())


def main() -> int:
    """Read the changed paths on stdin and print the tests to run, run from the repo root."""
    root = Path.cwd()
    ini_text = (root / "pytest.ini").read_text(encoding="utf-8")
    patterns, ignores = pytest_settings(ini_text)
    changed = [line.strip() for line in sys.stdin if line.strip()]
    record = root / GLOB_RECORD
    try:
        declared = glob_declared_guards(record.read_text(encoding="utf-8")) if record.is_file() else {}
    except (OSError, UnicodeDecodeError):
        # An unreadable or undecodable record costs a selection, never a push.
        declared = {}
    # A missing record is a failed selection, not an empty one (#19312 review): without it no
    # guard is reached through its scan roots, and that must not pass as "nothing to run".
    roots_text = (root / REACH_ROOTS_RECORD).read_text(encoding="utf-8")
    chosen = select(
        changed,
        patterns=patterns,
        ignores=ignores,
        exists=lambda rel: (root / rel).is_file(),
        declared_globs=declared,
        testpaths=pytest_testpaths(ini_text),
        roots=declared_roots(roots_text),
        references=tests_naming(root, changed, patterns),
        always=ALWAYS_RUN,
    )
    sys.stdout.write(format_selection(chosen))
    return 0


if __name__ == "__main__":
    sys.exit(main())
