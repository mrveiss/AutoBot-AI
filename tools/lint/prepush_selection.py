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
import sys
from pathlib import Path, PurePosixPath
from typing import Callable, Dict, Mapping, Sequence

#: Where the glob-declared guard inputs are recorded (#15900). Read as DATA via
#: `ast`, never imported: that module imports pytest and imports from this
#: package, so importing it here would both pull pytest into the hook and close
#: a cycle.
GLOB_RECORD = "repo_tests/glob_declared_reads_15900_test.py"
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
    except SyntaxError:
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


def is_test(path: str, patterns: Sequence[str]) -> bool:
    """Whether pytest collects *path*: its basename matches a ``python_files`` pattern."""
    return any(fnmatch.fnmatchcase(PurePosixPath(path).name, pattern) for pattern in patterns)


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
) -> Dict[str, str]:
    """The tests to run for *changed*, each mapped to the reason it was chosen.

    A changed test runs itself; a changed module runs its co-located ``foo_test.py``.
    A test that no longer exists is never selected, because pytest treats a vanished path as
    a collection error (#15751). Neither is one that pytest.ini ignores, because pytest
    collects a path named on its command line even when ``--ignore`` covers it (#16019).

    A changed path ALSO runs every guard that declares a glob matching it. Those guards
    are co-located with nothing, so the two rules above never reach them: they scan the
    tree and fire on its shape. That is the whole class #17241 burned four CI cycles on.
    """
    chosen: Dict[str, str] = {}
    declared = declared_globs or {}
    if any(p.startswith("repo_tests/") and p.endswith(".py") for p in changed):
        for guard, why in GUARDS_POLICING_GUARDS.items():
            if guard not in chosen and exists(guard) and not _under(guard, ignores):
                chosen[guard] = f"a repo_tests file changed; {why}"
    for path in changed:
        for guard in _guards_reading(path, declared):
            if guard not in chosen and exists(guard) and not _under(guard, ignores):
                chosen[guard] = f"declares a glob matching {path}"
    for path in changed:
        if is_test(path, patterns):
            test, reason = path, "changed"
        elif path.endswith(".py"):
            test, reason = f"{path[:-3]}_test.py", f"co-located with {path}"
        else:
            continue
        if test not in chosen and exists(test) and not _under(test, ignores):
            chosen[test] = reason
    return chosen


def format_selection(chosen: Mapping[str, str]) -> str:
    """One ``test<TAB>reason`` line per selected test: the hook's input and its log."""
    return "".join(f"{test}\t{reason}\n" for test, reason in chosen.items())


def main() -> int:
    """Read the changed paths on stdin and print the tests to run, run from the repo root."""
    root = Path.cwd()
    patterns, ignores = pytest_settings((root / "pytest.ini").read_text(encoding="utf-8"))
    changed = [line.strip() for line in sys.stdin if line.strip()]
    record = root / GLOB_RECORD
    declared = glob_declared_guards(record.read_text(encoding="utf-8")) if record.is_file() else {}
    chosen = select(
        changed,
        patterns=patterns,
        ignores=ignores,
        exists=lambda rel: (root / rel).is_file(),
        declared_globs=declared,
    )
    sys.stdout.write(format_selection(chosen))
    return 0


if __name__ == "__main__":
    sys.exit(main())
