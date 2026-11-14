# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A `*` beside a `**` stays inside one path segment in the filter matcher (#21555).

`_is_covered` rewrote a `*` that follows a leading `**/` or a mid-pattern `**` into something
`fnmatch` lets cross `/`, so `**/requirements*.txt` "covered" `a/b/requirements/c.txt` and
`a/**/b/*.md` "covered" `a/q/b/r/x.md`. Target reading: `*` and `?` never cross `/`, `**/` spans
zero or more directories, and only a trailing `/**` covers a whole subtree.

Literal fixtures only: every "misses" row sits beside a "covers" row on the same pattern, so a
matcher answering the same for every path fails on one side of the pair.
"""

from __future__ import annotations

import pytest
from repo_tests.python_filter_covers_its_guards_test import _is_covered


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        pytest.param(
            "**/requirements*.txt", "a/b/requirements/c.txt", False, id="leading-misses-dir-named-requirements"
        ),
        pytest.param("**/requirements*.txt", "a/requirements/x/y.txt", False, id="leading-misses-nested-under-dir"),
        pytest.param("**/requirements*.txt", "requirements.txt", True, id="leading-covers-root-file"),
        pytest.param("**/requirements*.txt", "a/requirements-dev.txt", True, id="leading-covers-nested-file"),
        pytest.param("a/**/b/*.md", "a/q/b/r/x.md", False, id="mid-misses-star-crossing-slash"),
        pytest.param("a/**/b/*.md", "a/b/x.md", True, id="mid-covers-zero-directories"),
        pytest.param("a/**/b/*.md", "a/q/b/x.md", True, id="mid-covers-one-directory"),
        pytest.param("a/**", "ab/x", False, id="trailing-misses-sibling-prefix"),
        pytest.param("a/**", "a/x/y", True, id="trailing-covers-subtree"),
        pytest.param("repo_tests/**", "other/baseline.txt", False, id="tree-misses-other-tree"),
        pytest.param("repo_tests/**", "repo_tests/baseline.txt", True, id="tree-covers-own-file"),
    ],
)
def test_a_star_beside_a_double_star_stays_inside_one_segment(pattern: str, path: str, expected: bool) -> None:
    assert _is_covered(path, [pattern]) is expected, f"{pattern} vs {path}"
