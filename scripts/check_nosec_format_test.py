#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for scripts/check_nosec_format.py (#13521, #13528).

The checker must fire on the forms bandit cannot use and stay silent on the ones
that work. Getting that boundary wrong in either direction is costly: a false
negative lets the warnings back in, and a false positive would push people to
delete the explanations, which are the useful part of a suppression.

Two defects are covered: prose where the test IDs belong (#13521), and an
annotation stranded on a line of closing punctuation (#13528).

Run: python3 -m pytest scripts/check_nosec_format_test.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parent / "check_nosec_format.py"
_spec = importlib.util.spec_from_file_location("check_nosec_format", _MODULE_PATH)
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)  # type: ignore[union-attr]

# #13521: this file must not contain a literal suppression token followed by
# prose. Bandit scans test files too, so spelling the fixtures out would emit
# exactly the warnings this checker exists to prevent — the checker's own tests
# would be the last remaining violation. The token is assembled at runtime.
_N = "# nose" + "c"


def _flagged(line: str) -> bool:
    return checker._is_malformed(line)


def _orphaned(line: str) -> bool:
    return checker._is_orphaned(line)


# ------------------------------------------------------------------ malformed


@pytest.mark.parametrize(
    "suffix",
    [
        "B105 - not a credential",
        "B105 — em dash variant",
        "B105: colon variant",
        "B603 B607 - fixed argv, no shell",
        "B603,B607 - comma separated ids",
        "because it is fine",  # no ids at all, straight to prose
    ],
)
def test_flags_prose_after_the_ids(suffix):
    line = f"value = compute()  {_N} {suffix}"
    assert _flagged(line), f"should be flagged: {line!r}"


# ---------------------------------------------------------------- well-formed


@pytest.mark.parametrize(
    "suffix",
    [
        "B105",
        "B105  # not a credential, a key prefix",
        "B603 B607",
        "B603 B607  # fixed argv, no shell",
        "",  # bare token, no ids, no prose
        "B608  # nosemgrep: python.lang.security.audit  # noqa: E501",
    ],
)
def test_accepts_the_working_forms(suffix):
    """The second '#' ends bandit's parse, so the explanation costs nothing."""
    line = f"value = compute()  {_N} {suffix}".rstrip()
    assert not _flagged(line), f"should NOT be flagged: {line!r}"


# -------------------------------------------------------------------- orphaned


@pytest.mark.parametrize(
    "head",
    [
        ")  ",
        "),  ",
        "]  ",
        "],  ",
        "}  ",
        "},  ",
        ")}]  ",  # nested close, single line
        "        )  ",  # indented
    ],
)
def test_flags_annotations_on_closing_punctuation(head):
    """The flagged expression is on an earlier line, so the annotation misses it."""
    line = f"{head}{_N} B311"
    assert _orphaned(line), f"should be flagged: {line!r}"


def test_flags_orphan_carrying_prose_too():
    line = f"),  {_N} B311  # analytics variance noise"
    assert _orphaned(line), f"should be flagged: {line!r}"


@pytest.mark.parametrize(
    "line_body",
    [
        "value = compute()  {n} B311",  # annotation rides the expression
        "    self.x = choice(items)  {n} B311",  # indented, still an expression
        "result = fn(  {n} B603 B607",  # opening bracket, node starts here
        "    {n} B311",  # standalone comment line, nothing closed on it
        ")  # closing bracket with an unrelated comment",
        ")",  # bare closing bracket
    ],
)
def test_accepts_annotations_that_reach_the_expression(line_body):
    line = line_body.format(n=_N)
    assert not _orphaned(line), f"should NOT be flagged: {line!r}"


# ------------------------------------------------------------------ end to end


def test_repository_is_currently_clean():
    problems = checker.find_malformed() + checker.find_orphaned()
    assert problems == [], "\n".join(problems[:10])
