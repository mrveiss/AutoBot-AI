# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A new code path that drops an index or flushes a database must be classified (#21383, #17038).

Knowledge-base deletes go through the approval gate (``services/kb_wipe_action.py``). This guard fails
when a tracked, non-test source file names ``FT.DROPINDEX``, ``dropindex``, ``flushdb`` or ``flushall`` and
is not in ``kb_destructive_paths_allowlist_21383.ALLOWLIST``, and when an allowlist entry no longer matches.
"""

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.kb_destructive_paths_allowlist_21383 import ALLOWLIST

from autobot_shared.testfile_names import is_test_filename
from tools.lint._scan_helpers import tracked_paths

_DESTRUCTIVE = re.compile(r"dropindex|flushdb|flushall", re.IGNORECASE)
_SUFFIXES = (".py", ".sh")
_SKIP_PREFIXES = ("repo_tests/", "docs/", "tools/")
#: Files that only NAME the verbs as data (a permission map, a docstring list), never run them.
_NAMES_ONLY = ("autobot_shared/auth/mcp_tool_permissions.py", "autobot-backend/services/mcp_dispatch.py")


def _discover(root: Path) -> list[str]:
    return tracked_paths(Path(root), "*.py", "*.sh")


#: Non-vacuity: the sweep must have read a real tree (a pin computed from this base, #19676).
REACH = declare("kb-destructive-paths", discover=_discover, floor=8800, growth=400, what="tracked .py/.sh files")


def _candidates() -> list[str]:
    paths = _discover(repo_root())
    REACH.completed(paths, repo_root())
    return [
        p
        for p in paths
        if p.endswith(_SUFFIXES)
        and not p.startswith(_SKIP_PREFIXES)
        and "/tests/" not in p
        and p not in _NAMES_ONLY
        and not is_test_filename(p)
    ]


def _destructive_files() -> set[str]:
    root = Path(repo_root())
    found = set()
    for rel in _candidates():
        try:
            if _DESTRUCTIVE.search((root / rel).read_text(encoding="utf-8")):
                found.add(rel)
        except (OSError, UnicodeDecodeError):
            continue
    return found


def test_the_sweep_is_not_vacuous():
    assert "autobot-backend/services/kb_wipe_redis.py" in _destructive_files()


def test_every_destructive_file_is_classified():
    unclassified = sorted(_destructive_files() - set(ALLOWLIST))
    assert not unclassified, (
        f"{unclassified} drop an index or flush a database. Route knowledge deletes through "
        "services.kb_wipe_action.propose_kb_wipe (#17038); classify a non-knowledge one in "
        "repo_tests/kb_destructive_paths_allowlist_21383.py"
    )


def test_no_stale_allowlist_entry():
    stale = sorted(set(ALLOWLIST) - _destructive_files())
    assert not stale, f"{stale} no longer drop an index or flush a database; remove them (the mapping only shrinks)"


def test_planted_destructive_call_is_detected():
    assert _DESTRUCTIVE.search('r.execute_command("FT.DROPINDEX", name, "DD")')
    assert _DESTRUCTIVE.search("redis_conn.flushdb()")
