# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The tree view the unconnected-code detectors share (#20512).

Every detector asks the same two things of the tree: *which files are production code* and
*what do they say*. `Tree` answers both over a path list plus a reader, so the real repository
(``git ls-files`` plus ``read_text``) and a planted control (a dict) go through identical code.
Text is read once per file and cached, because three detectors scan the same files and the guard
runs on every push.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from pathlib import Path

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

#: Directory names that mark test code wherever they sit in a path.
_TEST_DIRS = frozenset({"tests", "test", "__tests__", "fixtures", "repo_tests", "node_modules", "results", "testkit"})
_TEST_NAME = re.compile(r"(_test\.py|\.test\.[jt]sx?|\.spec\.[jt]sx?)$|^(test_.*\.py|conftest\.py)$")


def is_production(rel: str) -> bool:
    """A file that ships: not test code, not a fixture, not a recorded result."""
    parts = rel.split("/")
    return not (_TEST_DIRS.intersection(parts[:-1]) or _TEST_NAME.search(parts[-1]))


class Tree:
    """Tracked paths plus their text, read lazily and once."""

    def __init__(self, paths: Iterable[str], reader: Callable[[str], str]) -> None:
        self.paths = sorted(paths)
        self._reader = reader
        self._cache: dict[str, str] = {}

    @classmethod
    def of_repo(cls, root: Path) -> "Tree":
        try:
            paths = tracked_paths(root, ".")
        except EmptyEnumeration:
            paths = []
        return cls(paths, lambda rel: (root / rel).read_text(encoding="utf-8", errors="replace"))

    @classmethod
    def of_files(cls, files: dict[str, str]) -> "Tree":
        return cls(files, files.__getitem__)

    def text(self, rel: str) -> str:
        if rel not in self._cache:
            try:
                self._cache[rel] = self._reader(rel)
            except OSError:
                self._cache[rel] = ""
        return self._cache[rel]

    def select(self, *suffixes: str, production: bool = True, under: tuple[str, ...] = ()) -> list[str]:
        """Paths ending in one of *suffixes* (and under one of *under* if given)."""
        return [
            p
            for p in self.paths
            if p.endswith(suffixes)
            and (not production or is_production(p))
            and (not under or p.startswith(tuple(f"{u}/" for u in under)))
        ]
