# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18221: no mask reveals the start of a key; docs/developer/REDACTION_BOUNDARY.md has the masks to use."""

import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

REPO_ROOT = repo_root()
_TREES = ("autobot_shared", "autobot-backend", "autobot-slm-backend")
_TEST = re.compile(r"(_test|^test_.*)\.py$")
_PARTIAL_MASK = re.compile(
    r"""\b(?!\w*_id\[)\w*(?:key|secret|token|password|credential|value)\w*\[:\d\]\s*(?:\+\s*["\']|\})\.\.\.""",
    re.IGNORECASE,
)


def _sources(root: Path) -> list[Path]:
    return [
        path
        for tree in _TREES
        for path in (root / tree).rglob("*.py")
        if not _TEST.search(path.name) and "node_modules" not in path.parts
    ]


SOURCES_REACH = declare(
    "no_partial_key_mask_18221.sources",
    discover=_sources,
    what="Python sources a key mask could live in",
    roots=_TREES,
    floor=3290,  # mid-window; repinned by scripts/repin_reach_floors.py
    growth=400,
)


def test_no_mask_reveals_the_start_of_a_key() -> None:
    found = [
        f"{path.relative_to(REPO_ROOT).as_posix()}:{number}"
        for path in SOURCES_REACH.examined(REPO_ROOT)
        for number, line in enumerate(path.read_text("utf-8", errors="replace").splitlines(), 1)
        if _PARTIAL_MASK.search(line)
    ]
    assert not found, f"use REDACTED_PLACEHOLDER from autobot_shared.secret_redaction: {found}"


@pytest.mark.parametrize(
    ("source", "flagged"),
    [
        ('f"{api_key[:4]}...{api_key[-4:]}"', True),
        ('masked_secret=secret[:4] + "..."', True),
        ('f"{value[:4]}...{value[-4:]}"', True),
        ('f"{session_id[:8]}..."', False),
        ('"secret_id": secret_id[:8] + "..."', False),
        ("it used to reveal ``value[:4]...value[-4:]``", False),
        ('preview = text[:100] + "..."', False),
        ("masked_secret=REDACTED_PLACEHOLDER", False),
    ],
)
def test_the_detector_has_both_sides(source: str, flagged: bool) -> None:
    assert bool(_PARTIAL_MASK.search(source)) is flagged
