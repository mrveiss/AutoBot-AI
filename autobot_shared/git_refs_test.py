#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The accept and reject sets for git revisions reaching argv (#18125).

Nine allow-lists existed and every one accepted a leading-dash git flag, so the reject
set here is the finding, not a formality. Each rejected input below is one that at least
one of the nine patterns accepted.
"""

import pytest

from autobot_shared.git_refs import is_safe_range, is_safe_ref, is_safe_rev_pathspec

# Flags the old patterns accepted. `--output` and `-O` are the load-bearing ones: with
# the string-splitting call site in code_review_engine they composed into
# `git diff --output /tmp/evil HEAD`, an arbitrary file write.
_FLAGS = [
    "--output",
    "-O",
    "-O/etc/passwd",
    "--no-index",
    "--ext-diff",
    "--exec",
    "--upload-pack",
    "--receive-pack",
    "--file",
    "--global",
    "--system",
    "-x",
    "-u",
    "-f",
    "--cached",
]

_TRAVERSALS = ["..", "../..", "../../etc/passwd", "a/../../b", "..main"]


@pytest.mark.parametrize(
    "value",
    [
        "main",
        "HEAD",
        "HEAD~1",
        "HEAD~10",
        "HEAD^",
        "HEAD^^",
        "HEAD@{1}",
        "origin/main",
        "feature/my-branch",
        "v1.2.3",
        "release-2026.10",
        "0123456789abcdef0123456789abcdef01234567",  # pragma: allowlist secret  # a git SHA
        "0123abc",
        "refs/heads/main",
    ],
)
def test_ordinary_revisions_are_accepted(value: str) -> None:
    assert is_safe_ref(value)
    assert is_safe_range(value), "a bare revision is also a valid range argument"
    assert is_safe_rev_pathspec(value)


@pytest.mark.parametrize("value", _FLAGS)
def test_no_flag_is_ever_a_revision(value: str) -> None:
    """The whole point. `-` is legal inside a branch name, so only a leading-dash guard
    can refuse these — a character class cannot."""
    assert not is_safe_ref(value)
    assert not is_safe_range(value)
    assert not is_safe_rev_pathspec(value)


@pytest.mark.parametrize("value", _TRAVERSALS)
def test_no_traversal_is_ever_a_revision(value: str) -> None:
    assert not is_safe_ref(value)
    assert not is_safe_rev_pathspec(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "main\n",
        "main\r\n",
        "\nmain",
        "a b",
        "a;b",
        "$(whoami)",
        "`id`",
        "a|b",
        "a&b",
        "main:path",
        "a" * 129,
    ],
)
def test_rejected_single_revisions(value: str) -> None:
    assert not is_safe_ref(value)


def test_a_trailing_newline_is_rejected() -> None:
    """All nine old patterns accepted `"main\\n"`.

    They anchored with `$` and used `.match()`; in Python `$` also matches before one
    trailing newline. Not injection — `"main\\nrm -rf /"` was correctly rejected — but a
    newline rode into argv on every path. `fullmatch` plus `\\Z` is what closes it.
    """
    assert is_safe_ref("main")
    assert not is_safe_ref("main\n")
    assert not is_safe_range("main..feature\n")
    assert not is_safe_rev_pathspec("main:path/to/file\n")


@pytest.mark.parametrize(
    "value",
    ["main..feature", "main...feature", "HEAD~1..HEAD", "HEAD~1...HEAD", "origin/main..HEAD"],
)
def test_ranges_are_accepted(value: str) -> None:
    assert is_safe_range(value)
    assert not is_safe_ref(value), "a range is not a single revision"


@pytest.mark.parametrize(
    "value",
    [
        "main..--output",
        "--output..main",
        "main..-O/etc/passwd",
        "main..../../etc/passwd",
        "a..b..c",
        "a...b...c",
        "..main",
        "main..",
        "....",
    ],
)
def test_rejected_ranges(value: str) -> None:
    """Each side is validated as a revision in its own right.

    A global `(?!.*\\.\\.)` guard cannot work here — the separator *is* `..` — so the
    guard is applied per side. That is also what refuses `a..b..c`, which a single
    whole-string pattern accepted.
    """
    assert not is_safe_range(value)


@pytest.mark.parametrize("value", ["main:path/to/file", "HEAD:README.md", "v1.0:src/a.py"])
def test_pathspecs_are_accepted_only_by_the_pathspec_predicate(value: str) -> None:
    assert is_safe_rev_pathspec(value)
    assert not is_safe_ref(value), "the colon form belongs to `git show`, not `git diff <range>`"


@pytest.mark.parametrize("value", ["main:../../etc/passwd", "main:-O", "-O:path", "a:b:c", "main:", ":path"])
def test_rejected_pathspecs(value: str) -> None:
    assert not is_safe_rev_pathspec(value)


def test_the_sha_only_validator_is_not_replaced_by_these() -> None:
    """`services/knowledge/code_indexer.py:1012` keeps its own `^[0-9a-f]{7,40}$`.

    It validates stored provenance rather than argv and is deliberately stricter; these
    predicates accept any branch name, which would be a widening there. Recorded as a
    test so the next consolidation pass does not absorb it.
    """
    assert is_safe_ref("main")
    assert is_safe_ref("feature/x")
