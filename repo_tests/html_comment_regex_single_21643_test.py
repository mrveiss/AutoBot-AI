# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The HTML-comment pattern ``<!--.*?-->`` is defined once, in ``tools/lint/_comment_syntax.py`` (#21643).

Detected: the literal pattern text in a tracked ``.py`` under ``repo_tests`` or ``tools``, outside the
shared helper (and this guard). NOT detected: an equivalent pattern spelled differently.
"""

from __future__ import annotations

from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

PATTERN = "<!--" + ".*?" + "-->"
OWNER = "tools/lint/_comment_syntax.py"
SELF = "repo_tests/html_comment_regex_single_21643_test.py"


def _flag(files: dict[str, str]) -> list[str]:
    """The paths of *files* (path -> text) that define the pattern outside the owner and this guard."""
    return [p for p, text in files.items() if p not in (OWNER, SELF) and PATTERN in text]


def _offenders() -> list[str]:
    root = repo_root()
    paths = [p for p in tracked_paths(root, "repo_tests", "tools") if p.endswith(".py")]
    assert paths, "no tracked python under repo_tests/tools; the scan would pass vacuously"
    return _flag({p: (root / p).read_text(encoding="utf-8") for p in paths})


def test_no_second_html_comment_pattern():
    assert _offenders() == []


def test_a_second_definition_in_another_file_is_flagged():
    files = {"repo_tests/other_test.py": f"X = re.compile({PATTERN!r})\n"}
    assert _flag(files) == ["repo_tests/other_test.py"]


def test_a_clean_file_and_the_owner_and_self_paths_are_not_flagged():
    files = {"repo_tests/clean_test.py": "X = 1\n", OWNER: PATTERN, SELF: PATTERN}
    assert _flag(files) == []


def test_the_owner_still_defines_it():
    assert PATTERN in (repo_root() / OWNER).read_text(encoding="utf-8")
