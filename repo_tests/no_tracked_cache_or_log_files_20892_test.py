# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""No commit may track a cache or log file (#20892, log patterns from #20894).

BOUNDARY: every path in `git ls-files`. A tracked path matching a pattern below is a test or tool
run's output committed by accident. `logs/` and `*.log` are here because a test run once left
`logs/backend.log` in 72 base checkouts (#20894). ONE pattern list: add to `FORBIDDEN_PATTERNS`.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import tracked_paths

REPO_ROOT = repo_root()


def _every_tracked_path(root: Path) -> list[str]:
    return tracked_paths(root)


REACH = declare(
    "no-tracked-cache-or-log-files-20892",
    discover=_every_tracked_path,
    floor=13500,  # mid-window pin (#17356): 14044 tracked paths when measured, growth tolerates tree movement
    growth=1000,
    what="tracked paths",
)

#: (label, fnmatch pattern on the full tracked path). A directory pattern matches at any depth.
FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    ("python bytecode dir", "*/__pycache__/*"),
    ("python bytecode dir", "__pycache__/*"),
    ("python bytecode", "*.pyc"),
    ("tool cache dir", "*/.pytest_cache/*"),
    ("tool cache dir", ".pytest_cache/*"),
    ("tool cache dir", "*/.mypy_cache/*"),
    ("tool cache dir", ".mypy_cache/*"),
    ("tool cache dir", "*/.ruff_cache/*"),
    ("tool cache dir", ".ruff_cache/*"),
    ("log directory (#20894)", "logs/*"),
    ("log directory (#20894)", "*/logs/*"),
    ("log file (#20894)", "*.log"),
)


def violations(paths: list[str]) -> list[tuple[str, str]]:
    return [(p, label) for p in paths for label, pat in FORBIDDEN_PATTERNS if fnmatch.fnmatchcase(p, pat)]


def test_no_tracked_cache_or_log_file() -> None:
    found = violations(list(REACH.examined(REPO_ROOT)))
    assert not found, f"tracked cache/log files (remove them; add to .gitignore): {found[:20]}"


def test_control_logs_and_log_files_are_caught() -> None:
    """The list must fire on the #20894 cases, else the guard above proves nothing."""
    hits = {p for p, _ in violations(["logs/example.log", "a/b/x.log", "svc/logs/app.txt", "ok/readme.md"])}
    assert hits == {"logs/example.log", "a/b/x.log", "svc/logs/app.txt"}
