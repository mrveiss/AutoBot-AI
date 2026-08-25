# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Discrimination tests for the #14070 Field-default guard.

Each spelling below is one the regex this replaced could not see, or one it
wrongly fired on. Both directions are asserted: a guard that only got stricter
would trade the misses for false positives on prose.

Every fixture assembles the banned path from ``LIVE`` rather than quoting it, so
this file does not trip the repository's hardcoded-value rule and needs no
exemption entry -- the same discipline as
``check_no_shell_placeholder_paths_test.py``. Most of these spellings embed a
``Field(`` that happens to satisfy that rule's skip context, but not all do
(``module-constant-not-a-field`` deliberately has none), and a fixture that is
only accidentally compliant is one reformatting away from failing CI.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from tools.lint.check_field_defaults import (
    FIELD_CALL_FLOOR,
    LIVE_INSTALL_PREFIX,
    field_call_count,
    live_install_field_defaults,
)

#: The banned prefix, never written out in one piece in this file.
LIVE = LIVE_INSTALL_PREFIX

#: Every spelling of a frozen live-install default. The regex
#: ``default(?:_factory)?\s*=\s*"[^"]*/opt/autobot[^"]*"`` caught only the first.
OFFENDING_SPELLINGS = (
    pytest.param(f'x: str = Field(default="{LIVE}/logs/a.log")', id="double-quoted"),
    pytest.param(f"x: str = Field(default='{LIVE}/logs/a.log')", id="single-quoted"),
    pytest.param(f'x: str = Field(default_factory=lambda: "{LIVE}/logs/a.log")', id="lambda-body"),
    pytest.param(f"x: str = Field(default_factory=lambda: '{LIVE}/x')", id="lambda-single-quoted"),
    pytest.param('x: str = Field(default=f"' + LIVE + '/{name}.log")', id="f-string"),
    pytest.param(f'x: str = Field(default="/opt/" + "{LIVE[len("/opt/"):]}/logs/a.log")', id="concatenation"),
    pytest.param(f'x: str = Field(default_factory=lambda: str(Path("{LIVE}") / "l"))', id="nested-call"),
)

#: Text that mentions the path but is not a frozen default. The regex fired on
#: the first two, because it scanned raw file text.
BENIGN_SPELLINGS = (
    pytest.param(f'# a comment mentioning default="{LIVE}/logs/a.log"', id="comment"),
    pytest.param(f'"""A docstring mentioning default="{LIVE}/x"."""', id="docstring"),
    pytest.param('x: str = Field(default="/var/lib/autobot/x")', id="different-prefix"),
    pytest.param(f'x: str = Field(description="was {LIVE} before #14050")', id="non-default-kwarg"),
    pytest.param(f'LEGACY = "{LIVE}/logs/a.log"', id="module-constant-not-a-field"),
)


def test_the_offending_population_is_not_empty() -> None:
    """Floor for the parametrised sweeps below, asserted before their contents.

    An empty tuple collects zero cases, and a parametrised assertion that never
    runs passes. Each population is floored separately: a shared floor is
    satisfied by whichever tuple is still populated, which is how a guard here
    passed for years on one of two pathspecs matching nothing.
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
    from autobot_shared import ssot_config

    source = pathlib.Path(ssot_config.__file__).read_text(encoding="utf-8")
    assert field_call_count(source) >= FIELD_CALL_FLOOR


#: The shape ``scripts/lib/hardcoded-value-rules.sh`` detector 3 actually bans:
#: an AutoBot path opening a string literal. Replicated here rather than
#: approximated, so the self-guard below enforces exactly what CI enforces --
#: a stricter local rule would fail on prose *describing* the defect, which is
#: the AC4 false-positive this whole guard exists to avoid, turned inward.
_QUOTED_LIVE_PATH = re.compile(f"[\"']{re.escape(LIVE_INSTALL_PREFIX)}")

#: Detector 3's complete skip set, transcribed from ``_HV_PATH_SKIP_RE`` in
#: ``scripts/lib/hardcoded-value-rules.sh``. Transcribed in full, not trimmed to
#: the ones that happen to matter here: a self-guard looser than the rule passes
#: lines CI rejects. The two regex arms are matched as patterns, the rest as
#: substrings. Note detector 3 excludes ``*_test.py`` outright, so for this file
#: the check is deliberately stricter than CI -- a fixture that only survives
#: because tests are exempt is one file-rename away from reddening the build.
_RULE_SKIP_SUBSTRINGS = ("AUTOBOT_BASE_DIR", "PathConfig", "PathConstants", "Field(")
_RULE_SKIP_PATTERNS = (
    re.compile(r"default=[^,]*opt/autobot"),
    re.compile(r"\$\{[A-Z_]+:-/opt/autobot"),
)


def _rule_skips(line: str) -> bool:
    """True when detector 3 would skip *line* regardless of what it contains."""
    return any(s in line for s in _RULE_SKIP_SUBSTRINGS) or any(p.search(line) for p in _RULE_SKIP_PATTERNS)


@pytest.mark.parametrize(
    "module_name",
    ["tools/lint/check_field_defaults.py", "tools/lint/check_field_defaults_test.py"],
)
def test_neither_this_guard_nor_its_tests_carry_an_unskipped_literal(module_name: str) -> None:
    """Self-guard: no line may open a string with the banned path unskipped.

    Without this, a later edit reintroduces the literal, the hardcoded-value rule
    reds CI, and the tempting fix is an exemption entry rather than a fragment --
    and the guard's own source is where an exemption would be least visible.
    """
    root = pathlib.Path(__file__).resolve().parents[2]
    lines = (root / module_name).read_text(encoding="utf-8").splitlines()

    offenders = [
        f"{module_name}:{n}: {line.strip()[:100]}"
        for n, line in enumerate(lines, 1)
        if _QUOTED_LIVE_PATH.search(line) and not _rule_skips(line)
    ]

    assert offenders == [], (
        "quoted live-install path(s) with no skip context — detector 3 will fail CI:\n"
        + "\n".join(offenders)
        + "\n\nAssemble the path from fragments (see LIVE_INSTALL_PREFIX), not an exemption."
    )


def test_the_self_guard_can_actually_fail() -> None:
    """A self-guard that cannot fire is decoration.

    Uses the same detection the test above uses, on a synthetic line, so a
    refactor that neuters the regex fails here rather than passing quietly.
    """
    unskipped = f'LEGACY = "{LIVE_INSTALL_PREFIX}/logs/a.log"'
    assert _QUOTED_LIVE_PATH.search(unskipped)
    assert not _rule_skips(unskipped)

    prose = f"a docstring mentioning [^x]*{LIVE_INSTALL_PREFIX} in a regex"
    assert not _QUOTED_LIVE_PATH.search(prose), "the self-guard must not fire on prose"
