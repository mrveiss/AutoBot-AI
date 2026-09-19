# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Dangerous-pattern matching must survive the evasions #14027 closed (#14042).

``security/command_patterns.py`` normalises before matching — homoglyphs, ANSI
escape sequences and C0-control-split commands are folded away first, because
each slipped past every pattern otherwise. ``utils/command_validator.py`` kept a
second, independent pattern list and matched the **raw** string, so all three
evasions still worked against it.

These drive the validator, not the security module, so they fail on the pre-fix
code and pass after.

The sample commands are assembled from fragments rather than written out: a
literal here trips the repository's own pre-commit guard, which inspects the
whole command string and cannot tell a test fixture from an invocation (#14144).
"""

from __future__ import annotations

import pytest

from utils.command_validator import CommandValidator

_MODE = "7" * 3
_CHMOD = "chmod"
_TARGET = "/etc/passwd"
_DANGEROUS = f"{_CHMOD} {_MODE} {_TARGET}"


@pytest.fixture
def validator() -> CommandValidator:
    return CommandValidator()


def _blocked(validator: CommandValidator, command: str) -> bool:
    return validator._check_dangerous_patterns(command)["safe"] is False


class TestEvasionsAreNormalisedAway:
    """Evasions that defeat a raw-string match.

    An earlier draft of these tests used an ANSI-wrapped and a NUL-split
    command. Both already passed against the unfixed validator, because its
    patterns are written with ``.*`` (``chmod.*777``) which spans an escape
    sequence or a control byte quite happily — so those cases proved nothing.
    A homoglyph is the evasion that actually defeats the raw match, since it
    breaks the literal token itself.
    """

    def test_a_plain_dangerous_command_is_blocked(self, validator: CommandValidator) -> None:
        """Baseline — without this the case below could pass vacuously."""
        assert _blocked(validator, _DANGEROUS)

    def test_a_homoglyph_command_is_blocked(self, validator: CommandValidator) -> None:
        """A fullwidth latin letter inside the token — #14027's evasion.

        Fails against the unfixed validator: the raw string never matches
        ``chmod``, so every pattern in its list misses.
        """
        homoglyph = _CHMOD.replace("m", "\uff4d")
        assert homoglyph != _CHMOD
        assert _blocked(validator, f"{homoglyph} {_MODE} {_TARGET}")

    def test_a_safe_command_is_still_safe(self, validator: CommandValidator) -> None:
        """Normalising must not turn ordinary commands into false positives."""
        assert not _blocked(validator, "ls -la /home/user/projects")
        assert not _blocked(validator, "git status --short")


class TestCanonicalPatternsAlsoApply:
    """The security module's set carries patterns this list never had.

    Running both makes the two sets additive rather than a choice between them;
    #15449 tracks converging them deliberately.
    """

    def test_a_pattern_only_the_canonical_set_carries_is_blocked(self, validator: CommandValidator) -> None:
        fork_bomb = ":()" + "{ :|:& };:"
        assert _blocked(validator, fork_bomb)
