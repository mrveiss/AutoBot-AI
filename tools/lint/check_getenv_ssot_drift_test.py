#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Discrimination + integration tests for the #13264 getenv/ssot_config
drift guard.

Unit fixtures assert the comparison logic in isolation (string vs bool,
falsy-equivalence, the exemption marker); the integration test runs the
guard against the real tree, the way CI does.
"""

from __future__ import annotations

from pathlib import Path

from tools.lint.check_getenv_ssot_drift import (
    FIELD_DEFAULT_FLOOR,
    GETENV_CALL_FLOOR,
    extract_field_defaults,
    extract_getenv_defaults,
    find_drift,
    values_disagree,
)

FIELD_SOURCE = """
class MiscConfig(BaseSettings):
    cache_size: int = Field(default=128, alias="AUTOBOT_CACHE_SIZE")
    cache_enabled: bool = Field(default=True, alias="AUTOBOT_CACHE_ENABLED")
    lazy_path: str = Field(default_factory=lambda: "/x", alias="AUTOBOT_LAZY_PATH")
    computed: int = Field(default=SOME_CONSTANT, alias="AUTOBOT_COMPUTED")
    trailing_str: str = Field(default="", alias="AUTOBOT_TRAILING")
"""


def test_extract_field_defaults_reads_literal_defaults_only() -> None:
    fields = extract_field_defaults(FIELD_SOURCE)
    assert fields["AUTOBOT_CACHE_SIZE"] == 128
    assert fields["AUTOBOT_CACHE_ENABLED"] is True
    assert "AUTOBOT_LAZY_PATH" not in fields, "default_factory is lazy/computed, not comparable"
    assert "AUTOBOT_COMPUTED" not in fields, "a Name reference is not a literal"


def test_extract_getenv_defaults_finds_both_spellings() -> None:
    source = (
        "import os\n"
        'a = os.getenv("AUTOBOT_CACHE_SIZE", "128")\n'
        'b = os.environ.get("AUTOBOT_CACHE_ENABLED", "true")\n'
        'c = os.getenv("AUTOBOT_ONE_ARG")\n'  # no default -- not comparable
    )
    calls = extract_getenv_defaults(source)
    names = {name for name, _default, _lineno in calls}
    assert names == {"AUTOBOT_CACHE_SIZE", "AUTOBOT_CACHE_ENABLED"}


def test_extract_getenv_defaults_honors_the_exempt_marker() -> None:
    source = 'import os\nos.getenv("AUTOBOT_CACHE_SIZE", "999")  # ssot-config-exempt: deliberate\n'
    assert extract_getenv_defaults(source) == []


def test_values_disagree_treats_bool_string_as_equivalent() -> None:
    assert not values_disagree("true", True)
    assert not values_disagree("FALSE", False)
    assert values_disagree("true", False)


def test_values_disagree_treats_falsy_spellings_as_equivalent() -> None:
    """A str-typed call site and a bool-typed field frequently agree on
    "off" while disagreeing on spelling — "" and False are not a real
    drift, only a type migration the guard should not flag."""
    assert not values_disagree("", False)
    assert not values_disagree("0", 0.0)
    assert not values_disagree("", 0)


def test_values_disagree_catches_a_real_numeric_regression() -> None:
    """The #13264 shape itself: '1000' (pre-#7437) vs 0 (post-#7437)."""
    assert values_disagree("1000", 0)


def test_values_disagree_catches_a_real_string_regression() -> None:
    assert values_disagree("https://api.anthropic.com/v1", "")


def test_the_reach_floors_are_populated() -> None:
    """Guards against both floors sliding to zero unnoticed, mirroring
    check_field_defaults_test.py's population-floor pattern."""
    assert FIELD_DEFAULT_FLOOR >= 100
    assert GETENV_CALL_FLOOR >= 5


def test_no_drift_between_live_getenv_defaults_and_ssot_config() -> None:
    """Integration: run the real guard against the real tree.

    Two call sites are permanently exempt (see their own
    ``ssot-config-exempt`` comments): both are deliberate, documented
    divergences predating #13264, not migration casualties.
    """
    repo_root = Path(__file__).resolve().parents[2]
    offenders, calls_examined = find_drift(repo_root)
    assert calls_examined >= GETENV_CALL_FLOOR, (
        f"the sweep matched only {calls_examined} call site(s) against a known "
        "ssot_config alias — it broke, or scope narrowed unexpectedly"
    )
    assert offenders == [], "\n".join(offenders)
