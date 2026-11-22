#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Two validators for git revisions reaching argv (#18125).

Nine separate allow-lists existed, and **every one of them accepted a leading-dash git
flag**. Measured, with each pattern copied verbatim:

    pattern                       '--output'  '--no-index'  '-O'      '../../etc/passwd'
    git_mcp:81  _COMMIT_REF_RE    ACCEPT      ACCEPT        ACCEPT    ACCEPT
    git_mcp:82  _FULL_REF_RE      ACCEPT      ACCEPT        ACCEPT    ACCEPT
    schemas_code:2451             ACCEPT      ACCEPT        ACCEPT    ACCEPT
    analytics_code_review:63      ACCEPT      ACCEPT        ACCEPT    ACCEPT
    code_review_engine:45         ACCEPT      ACCEPT        ACCEPT    ACCEPT
    plugin_install:39             reject      reject        reject    reject

The exposure is **argument injection, not shell injection**: every call path uses
list-argv with no shell, and `$(whoami)`, `` ` ``, `;`, `|` and `&` were rejected
everywhere. What got through was `git diff --output <path>` and friends — a flag, not a
command.

Only `plugin_install.py:39` was safe, because it guards with positive lookaheads rather
than hoping a character class excludes flags. Those lookaheads are what this module
keeps. It does **not** keep that pattern wholesale: it also rejected `HEAD~1`,
`HEAD^` and `main..feature`, the ordinary documented syntax the range callers need.
Hence two validators rather than one, so neither caller has to widen the other's rule.

A denylist is the alternative this deliberately avoids. `git_mcp.sanitize_git_args`
takes that approach and is missing `--output`, `-O`, `--ext-diff` and `--no-index`
today — a denylist has to track git's whole flag surface forever, and an allow-list
anchored against a leading dash does not.
"""

from __future__ import annotations

import re

__all__ = ["is_safe_ref", "is_safe_range", "is_safe_rev_pathspec", "REF_CHARS"]

#: Characters a revision may contain. `^ ~ @ { }` are here because `HEAD~1`, `HEAD^` and
#: `HEAD@{1}` are ordinary revisions. `:` is absent on purpose — `main:path/to/file` is a
#: pathspec, not a revision, and only two of the nine old patterns accepted it.
REF_CHARS = r"A-Za-z0-9._/@{}^~-"

# `(?!-)` is the whole point: it is what refuses `-O`, `--output`, `--ext-diff` and
# `--upload-pack`, none of which any character class can exclude while `-` is a legal
# character inside a branch name.
#
# `(?!.*\.\.)` refuses `..` anywhere, which covers `../../etc/passwd` as well as the
# bare `..` range operator — a single revision never needs either.
#
# `\Z` and not `$`: in Python `$` also matches before one trailing newline, so every one
# of the nine old patterns accepted `"main\n"` and let it ride into argv.
_SAFE_REF_RE = re.compile(rf"(?!-)(?!.*\.\.)[{REF_CHARS}]{{1,128}}\Z")

# A range is two revisions joined by `..` or `...`. The `..` guard cannot be global here
# — the separator is literally `..` — so each side is validated as a revision in its own
# right, which is also what stops `a..b..c` and `..main`.
_RANGE_SPLIT_RE = re.compile(r"\.{2,3}")


def is_safe_ref(value: str) -> bool:
    """True when ``value`` is a single git revision safe to pass as argv.

    Accepts: ``main``, ``HEAD``, ``HEAD~1``, ``HEAD^``, ``HEAD@{1}``, ``origin/main``,
    ``feature/my-branch``, ``v1.2.3``, and abbreviated or full SHAs.

    Rejects: anything starting with ``-`` (argument injection), anything containing
    ``..`` (traversal and the range operator), the empty string, a trailing newline, and
    anything over 128 characters.

    Examples:
        >>> is_safe_ref("HEAD~1")
        True
        >>> is_safe_ref("--output")
        False
        >>> is_safe_ref("../../etc/passwd")
        False
        >>> is_safe_ref("main\\n")
        False
    """
    return bool(_SAFE_REF_RE.fullmatch(value))


def is_safe_range(value: str) -> bool:
    """True when ``value`` is a single revision or a ``..``/``...`` range of two.

    Each side is validated by :func:`is_safe_ref`, so a flag or a traversal on either
    side is refused and ``a..b..c`` cannot pass by satisfying the pattern as a whole.

    Examples:
        >>> is_safe_range("main..feature")
        True
        >>> is_safe_range("HEAD~1...HEAD")
        True
        >>> is_safe_range("HEAD")
        True
        >>> is_safe_range("main..--output")
        False
        >>> is_safe_range("a..b..c")
        False
    """
    if is_safe_ref(value):
        return True
    parts = _RANGE_SPLIT_RE.split(value)
    return len(parts) == 2 and all(is_safe_ref(part) for part in parts)


def is_safe_rev_pathspec(value: str) -> bool:
    """True for a revision, or a ``rev:path`` pathspec as ``git show`` accepts.

    Separate from :func:`is_safe_ref` rather than a flag on it, because the colon form
    is only valid for the handful of commands that take a pathspec — `git show` and
    `git cat-file`, not `git diff <range>`. Of the nine old patterns, exactly two
    accepted a colon, and the same string was therefore valid for `git show` and
    invalid for `git diff`. Keeping the two accept sets as two named predicates is what
    makes that difference visible at the call site instead of implied by a character
    class.

    Both halves are validated as revisions, so a flag or a traversal in the path half is
    refused.

    Examples:
        >>> is_safe_rev_pathspec("HEAD")
        True
        >>> is_safe_rev_pathspec("main:path/to/file")
        True
        >>> is_safe_rev_pathspec("main:../../etc/passwd")
        False
        >>> is_safe_rev_pathspec("main:-O")
        False
        >>> is_safe_rev_pathspec("a:b:c")
        False
    """
    if is_safe_ref(value):
        return True
    parts = value.split(":")
    return len(parts) == 2 and all(is_safe_ref(part) for part in parts)
