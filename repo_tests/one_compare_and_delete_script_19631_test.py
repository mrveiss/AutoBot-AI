#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One owner-checked release and renew (#19631): their home is ``autobot_shared/redis_utils.py``.

Matches the script's shape, not a name: a Lua body that compares a key's value and then deletes or
expires it is a private copy whatever it is called. Compare-and-set and JSON-decoding scripts are
different operations and do not match.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

HOME = "autobot_shared/redis_utils.py"
ROOTS = ("autobot-backend", "autobot_shared", "autobot-slm-backend")
COPY = re.compile(
    r"redis\.call\(\s*['\"]get['\"],\s*KEYS\[1\]\s*\)\s*==\s*ARGV\[1\]\s*then\s*"
    r"return\s+redis\.call\(\s*['\"](del|expire|pexpire)['\"]",
    re.IGNORECASE,
)
SHAPES_IN_HOME = 2


def _python_files(root: Path) -> list[str]:
    """Tracked python files under ``ROOTS``; empty on an empty tree."""
    try:
        return [path for path in tracked_paths(root, *ROOTS) if path.endswith(".py")]
    except EmptyEnumeration:
        return []


REACH = declare(
    "one-compare-and-delete-script",
    discover=_python_files,
    floor=6202,  # mid-window: population 6402, growth 400
    growth=400,
    what="tracked python files under the backends and autobot_shared",
)


def _copies() -> dict[str, int]:
    root = repo_root()
    paths = _python_files(root)
    REACH.completed(len(paths))
    found: dict[str, int] = {}
    for rel in paths:
        path = root / rel
        if path.is_file():
            hits = len(COPY.findall(path.read_text(encoding="utf-8", errors="replace")))
            if hits:
                found[rel] = hits
    return found


def test_only_the_home_defines_the_scripts():
    copies = _copies()
    assert copies.pop(HOME, 0) == SHAPES_IN_HOME, "the home's scripts are not seen: the pattern broke"
    assert not copies, f"use delete_if_value / expire_if_value from {HOME}: {copies}"


def test_the_pattern_matches_a_copy_in_either_case_and_spacing():
    assert COPY.search("if redis.call('get', KEYS[1]) == ARGV[1] then\n    return redis.call('del', KEYS[1])")
    assert COPY.search('if redis.call("GET",KEYS[1])==ARGV[1] then return redis.call("PEXPIRE", KEYS[1], ARGV[2])')
    assert not COPY.search("if redis.call('GET', KEYS[1]) == ARGV[1] then\n  redis.call('SET', KEYS[1], ARGV[2])")
