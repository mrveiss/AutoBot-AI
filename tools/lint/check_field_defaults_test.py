# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Discrimination tests for the #14070 Field-default guard.

Each spelling below is one the regex this replaced could not see, or one it
wrongly fired on. Both directions are asserted: a guard that only got stricter
would trade the misses for false positives on prose.
"""

from __future__ import annotations

import pytest

from tools.lint.check_field_defaults import FIELD_CALL_FLOOR, field_call_count, live_install_field_defaults

#: Every spelling of a frozen live-install default. The regex
#: ``default(?:_factory)?\s*=\s*"[^"]*/opt/autobot[^"]*"`` caught only the first.
OFFENDING_SPELLINGS = (
    pytest.param('x: str = Field(default="/opt/autobot/logs/a.log")', id="double-quoted"),
    pytest.param("x: str = Field(default='/opt/autobot/logs/a.log')", id="single-quoted"),
    pytest.param('x: str = Field(default_factory=lambda: "/opt/autobot/logs/a.log")', id="lambda-body"),
    pytest.param("x: str = Field(default_factory=lambda: '/opt/autobot/x')", id="lambda-single-quoted"),
    pytest.param('x: str = Field(default=f"/opt/autobot/{name}.log")', id="f-string"),
    pytest.param('x: str = Field(default="/opt/" + "autobot/logs/a.log")', id="concatenation"),
    pytest.param('x: str = Field(default_factory=lambda: str(Path("/opt/autobot") / "l"))', id="nested-call"),
)

#: Text that mentions the path but is not a frozen default. The regex fired on
#: the first two, because it scanned raw file text.
BENIGN_SPELLINGS = (
    pytest.param('# a comment mentioning default="/opt/autobot/logs/a.log"', id="comment"),
    pytest.param('"""A docstring mentioning default="/opt/autobot/x"."""', id="docstring"),
    pytest.param('x: str = Field(default="/var/lib/autobot/x")', id="different-prefix"),
    pytest.param('x: str = Field(description="was /opt/autobot before #14050")', id="non-default-kwarg"),
    pytest.param('LEGACY = "/opt/autobot/logs/a.log"', id="module-constant-not-a-field"),
)


def test_the_offending_population_is_not_empty() -> None:
    """Floor for the parametrised sweeps below, asserted before their contents.

    An empty tuple collects zero cases, and a parametrised assertion that never
    runs passes. Each population is floored separately: a shared floor is
    satisfied by whichever tuple is still populated, which is how a guard here
    passed for years with one of two pathspecs matching nothing.
    """
    assert len(OFFENDING_SPELLINGS) >= 7
    assert len(BENIGN_SPELLINGS) >= 5


@pytest.mark.parametrize("spelling", OFFENDING_SPELLINGS)
def test_the_guard_catches_every_spelling(spelling: str) -> None:
    """#14070 AC3, including the ``default_factory=lambda:`` body."""
    assert live_install_field_defaults(spelling) != [], f"guard blind to: {spelling}"


@pytest.mark.parametrize("benign", BENIGN_SPELLINGS)
def test_the_guard_does_not_fire_on_prose_or_other_kwargs(benign: str) -> None:
    """#14070 AC4: a comment or docstring mentioning the path is not a default."""
    assert live_install_field_defaults(benign) == [], f"guard false-positived on: {benign}"


def test_the_field_count_floor_rejects_a_broken_sweep() -> None:
    """The floor must actually be capable of failing."""
    assert field_call_count("") == 0
    assert field_call_count("") < FIELD_CALL_FLOOR


def test_the_field_count_reaches_the_real_ssot_config() -> None:
    from pathlib import Path

    from autobot_shared import ssot_config

    source = Path(ssot_config.__file__).read_text(encoding="utf-8")
    assert field_call_count(source) >= FIELD_CALL_FLOOR
