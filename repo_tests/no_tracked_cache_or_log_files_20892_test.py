# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""No commit may track a cache or log file (#20892, log patterns from #20894).

BOUNDARY: every path in `git ls-files`. A tracked path matching a pattern below is a test or tool
run's output committed by accident. `logs/` and `*.log` are here because a test run once left
`logs/backend.log` in 72 base checkouts (#20894). ONE list: add to `FORBIDDEN_DIRS` / `FORBIDDEN_SUFFIXES`.
"""

from __future__ import annotations

from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

REPO_ROOT = repo_root()


def _every_tracked_path(root: Path) -> list[str]:
    try:
        return tracked_paths(root)
    except EmptyEnumeration:
        return []  # an empty tree: the min_fraction below raises the typed refusal instead


#: The whole tracked tree, so its fraction of the tracked-file count is 1.0; 0.9 fires once a
#: tenth of the tree goes unread.
REACH = declare(
    "no-tracked-cache-or-log-files-20892",
    discover=_every_tracked_path,
    min_fraction=0.9,
    what="every tracked path, swept for a committed cache or log file",
)

#: (label, directory name). A tracked path with a directory of this name at any depth is a violation.
#: Names and suffixes, not path globs: this guard reads the whole tracked tree, which no path filter can
#: name, so it declares no glob into a tree (#15900).
FORBIDDEN_DIRS: tuple[tuple[str, str], ...] = (
    ("python bytecode dir", "__pycache__"),
    ("tool cache dir", ".pytest_cache"),
    ("tool cache dir", ".mypy_cache"),
    ("tool cache dir", ".ruff_cache"),
    ("log directory (#20894)", "logs"),
)
#: (label, file suffix). A tracked path ending in one of these is a violation.
FORBIDDEN_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("python bytecode", ".pyc"),
    ("log file (#20894)", ".log"),
)


def violations(paths: list[str]) -> list[tuple[str, str]]:
    found = []
    for path in paths:
        directories = path.split("/")[:-1]
        found += [(path, label) for label, name in FORBIDDEN_DIRS if name in directories]
        found += [(path, label) for label, suffix in FORBIDDEN_SUFFIXES if path.endswith(suffix)]
    return found


def test_no_tracked_cache_or_log_file() -> None:
    found = violations(list(REACH.examined(REPO_ROOT)))
    assert not found, f"tracked cache/log files (remove them; add to .gitignore): {found[:20]}"


def test_control_logs_and_log_files_are_caught() -> None:
    """The list must fire on the #20894 cases, else the guard above proves nothing."""
    hits = {
        p for p, _ in violations(["logs/example.log", "a/b/x.log", "svc/logs/app.txt", "ok/readme.md", "docs/logs"])
    }
    assert hits == {"logs/example.log", "a/b/x.log", "svc/logs/app.txt"}
