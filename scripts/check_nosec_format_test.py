#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for scripts/check_nosec_format.py (#13521).

The checker must fire on the form bandit mis-parses and stay silent on the two
that work. Getting that boundary wrong in either direction is costly: a false
negative lets the warnings back in, and a false positive would push people to
delete the explanations, which are the useful part of a suppression.

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
    return bool(checker._MALFORMED.search(line) or checker._MALFORMED_BARE.search(line))


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


# ------------------------------------------------------------------ end to end


def test_repository_is_currently_clean():
    problems = checker.find_malformed()
    assert problems == [], "\n".join(problems[:10])
