# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""No commit may track a cache or log file (#20892, log patterns from #20894).

BOUNDARY: every path in `git ls-files`. A tracked path matching a pattern below is a test or tool
run's output committed by accident. `logs/` and `*.log` are here because a test run once left
`logs/backend.log` in 72 base checkouts (#20894). ONE pattern list: add to `FORBIDDEN_PATTERNS`.
"""

from __future__ import annotations

import fnmatch
import subprocess

from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

REPO_ROOT = repo_root()

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


def _tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, check=True, env=scrubbed_git_env()
    ).stdout.decode("utf-8")
    return [p for p in out.split("\0") if p]


def test_no_tracked_cache_or_log_file() -> None:
    found = violations(_tracked())
    assert not found, f"tracked cache/log files (remove them; add to .gitignore): {found[:20]}"


def test_control_logs_and_log_files_are_caught() -> None:
    """The list must fire on the #20894 cases, else the guard above proves nothing."""
    hits = {p for p, _ in violations(["logs/backend.log", "a/b/x.log", "svc/logs/app.txt", "ok/readme.md"])}
    assert hits == {"logs/backend.log", "a/b/x.log", "svc/logs/app.txt"}
