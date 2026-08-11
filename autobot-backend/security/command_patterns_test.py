# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for un-normalized-input bypasses of the dangerous-command gate (#14027).

`is_dangerous_substring()` and `check_dangerous_patterns()` used to match
directly against the raw command string. A homoglyph, an ANSI-wrapped
command, or a command with an embedded C0 control byte all resolve to the
same destructive `rm -rf /` once a shell or terminal renderer normalizes
them, but none of those raw forms matched any pattern in
`DANGEROUS_SUBSTRINGS` or `DANGEROUS_REGEX_PATTERNS`.

Every bypass test below is paired with a "still works" test in the same
class, per the issue's acceptance criteria: a predicate-only test suite
would stay green while the gate became either too loose (bypass) or too
strict (legitimate command rejected / rewritten before execution).
"""

from security.command_patterns import (
    check_dangerous_patterns,
    is_dangerous_command,
    is_dangerous_substring,
)
from utils.encoding_utils import strip_ansi_codes

# U+FF4D FULLWIDTH LATIN SMALL LETTER M — NFKC-folds to ASCII 'm'.
_FULLWIDTH_M = "ｍ"

# ANSI SGR: red-on, reset.
_ANSI_RED = "\x1b[31m"
_ANSI_RESET = "\x1b[0m"

# NUL byte.
_NUL = "\x00"


class TestHomoglyphBypass:
    """A fullwidth 'm' is a distinct codepoint; `.lower()` alone does not fold it."""

    def test_fullwidth_m_variant_is_classified_dangerous(self):
        command = "r" + _FULLWIDTH_M + " -rf /"
        is_dangerous, reason = is_dangerous_command(command)
        assert is_dangerous is True
        assert reason is not None

    def test_fullwidth_m_variant_caught_by_substring_check_directly(self):
        matched, pattern = is_dangerous_substring("r" + _FULLWIDTH_M + " -rf /")
        assert matched is True
        assert pattern == "rm -rf /"

    def test_legitimate_fullwidth_character_in_filename_still_executes(self):
        """A filename may legitimately contain fullwidth characters (#14027 AC).

        The gate must not flag it, and the string handed to the caller for
        execution must remain byte-identical to what was typed — normalization
        is for matching only, never for the string that gets executed.
        """
        command = "cat report_" + _FULLWIDTH_M + "arker.txt"
        original = command
        is_dangerous, reason = is_dangerous_command(command)
        assert is_dangerous is False
        assert reason is None
        # No mutation: the caller's string is untouched by the matching call.
        assert command == original
        assert command is original


class TestAnsiWrappedBypass:
    """ANSI SGR bytes break a leading `\\b` word-boundary regex assertion apart.

    `rm -rf /` itself is a poor probe for this: it is ALSO a literal entry in
    `DANGEROUS_SUBSTRINGS`, so `is_dangerous_command` catches an ANSI-wrapped
    `rm -rf /` via the substring path even with zero normalization — the SGR
    bytes sit *outside* the substring, not inside it, so wrapping alone never
    breaks that particular check. `kill -9 -1` has no substring-list entry and
    is regex-only (`\\bkill\\s+-9\\s+-1\\b`), so it isolates the real gap: an
    SGR sequence like `\\x1b[31m` ends in the letter `m`, a word character,
    which glues directly onto the following `kill` (`...31mkill...`) and
    removes the `\\b` boundary the regex requires — verified to bypass
    `is_dangerous_command` entirely pre-fix (`(False, None)`).
    """

    def test_ansi_wrapped_kill_all_processes_is_classified_dangerous(self):
        command = _ANSI_RED + "kill -9 -1" + _ANSI_RESET
        is_dangerous, reason = is_dangerous_command(command)
        assert is_dangerous is True
        assert reason is not None

    def test_ansi_wrapped_caught_by_regex_check_directly(self):
        command = _ANSI_RED + "kill -9 -1" + _ANSI_RESET
        matches = check_dangerous_patterns(command)
        assert any(severity == "critical" for _, severity, _ in matches)

    def test_legitimate_ansi_colored_safe_command_still_passes(self):
        """A benign command wrapped in color codes (e.g. from a colored shell
        prompt/log capture) must not become dangerous merely by being colored."""
        command = _ANSI_RED + "ls -la /home/user" + _ANSI_RESET
        is_dangerous, reason = is_dangerous_command(command)
        assert is_dangerous is False
        assert reason is None


class TestNulEmbeddedBypass:
    """An embedded C0 control (NUL) splits the substring match apart."""

    def test_nul_embedded_rm_rf_is_classified_dangerous(self):
        command = "rm" + _NUL + " -rf /"
        is_dangerous, reason = is_dangerous_command(command)
        assert is_dangerous is True
        assert reason is not None

    def test_nul_used_as_the_only_separator_is_still_caught(self):
        """NUL replacing the space entirely (no separator survives at all)
        must still be caught — the normalizer must not just delete the
        control byte and leave two tokens glued together."""
        command = "rm" + _NUL + "-rf" + _NUL + "/"
        is_dangerous, reason = is_dangerous_command(command)
        assert is_dangerous is True
        assert reason is not None

    def test_legitimate_command_with_ordinary_whitespace_still_works(self):
        """A safe command with normal (even repeated) whitespace must keep
        being classified as not dangerous."""
        command = "ls    -la   /tmp"
        is_dangerous, reason = is_dangerous_command(command)
        assert is_dangerous is False
        assert reason is None


class TestPlainDangerousCommandsStillCaught:
    """Baseline regression: the un-obfuscated form must still be caught."""

    def test_plain_rm_rf_root_is_dangerous(self):
        is_dangerous, reason = is_dangerous_command("rm -rf /")
        assert is_dangerous is True
        assert reason is not None

    def test_plain_safe_command_is_not_dangerous(self):
        is_dangerous, reason = is_dangerous_command("ls -la")
        assert is_dangerous is False
        assert reason is None


class TestAnUnterminatedOscMustNotSwallowTheCommand:
    """Review of #14027 found the normalization *weakened* the gate here.

    ``strip_ansi_codes``' OSC pattern had an OPTIONAL terminator, so a bare
    introducer consumed up to 1024 following characters. Normalizing before
    matching then deleted a plain, unobfuscated dangerous command from the text
    the matchers saw — a payload that was caught BEFORE the normalization fix
    became "safe" after it. Strictly worse than the baseline, which is the one
    outcome a security fix must never produce.

    Built from parts so this file contains no destructive literal.
    """

    OSC = "\x1b]"
    BEL = "\x07"
    KILL = "kill" + " -9 " + "-1"

    def test_content_after_an_unterminated_osc_is_still_examined(self):
        payload = "echo hi" + self.OSC + "0;AAAAA;" + self.KILL

        flagged, _reason = is_dangerous_command(payload)

        assert flagged is True, "an unterminated OSC must not hide the rest of the command"

    def test_the_introducer_is_removed_but_the_text_survives(self):
        stripped = strip_ansi_codes("echo hi" + self.OSC + "tail")

        assert "tail" in stripped, "only the introducer may be dropped, never the content"
        assert "\x1b" not in stripped

    def test_a_properly_terminated_osc_is_still_stripped_whole(self):
        """The legitimate case must keep working — this is a real terminal sequence."""
        stripped = strip_ansi_codes("a" + self.OSC + "0;window title" + self.BEL + "b")

        assert stripped == "ab"

    def test_a_bare_introducer_alone_does_not_flag_a_benign_command(self):
        flagged, _reason = is_dangerous_command("echo hi" + self.OSC + "0;title")

        assert flagged is False
