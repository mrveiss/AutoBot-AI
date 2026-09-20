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

import fnmatch
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Callable, Dict, Mapping, Sequence


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
) -> Dict[str, str]:
    """The tests to run for *changed*, each mapped to the reason it was chosen.

    A changed test runs itself; a changed module runs its co-located ``foo_test.py``.
    A test that no longer exists is never selected, because pytest treats a vanished path as
    a collection error (#15751). Neither is one that pytest.ini ignores, because pytest
    collects a path named on its command line even when ``--ignore`` covers it (#16019).
    """
    chosen: Dict[str, str] = {}
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
    chosen = select(changed, patterns=patterns, ignores=ignores, exists=lambda rel: (root / rel).is_file())
    sys.stdout.write(format_selection(chosen))
    return 0


if __name__ == "__main__":
    sys.exit(main())
