#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One set of ANSI patterns, two documented policies (#18093).

Four implementations of "strip ANSI" existed in the backend. Consolidating them onto
one function would have been wrong: the canonical ``strip_ansi_codes`` also removes two
patterns that carry no ESC byte, which corrupts any text containing ``[h``, ``[H``,
``[J`` or ``]0;`` — a markdown link, a git ref, a man page. So the escape-only half is
now ``strip_ansi_escapes`` and the three forks call that; ``strip_ansi_codes`` keeps its
terminal-output behaviour for the PTY callers that need it.

These tests pin both policies and the boundary between them, so a later "simplification"
that merges them again fails here rather than silently eating link text.
"""

import pathlib
import re
import warnings

import pytest

from utils.encoding_utils import strip_ansi_codes, strip_ansi_escapes

_ESC = "\x1b"
_REPO = pathlib.Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# strip_ansi_escapes: safe on arbitrary text
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "raw,expected",
    [
        (f"{_ESC}[31mRed{_ESC}[0m Text", "Red Text"),
        (f"{_ESC}[1;32mbold green{_ESC}[m", "bold green"),
        # Beyond SGR: the forks matched only `m` or `[mGKHF]`, so these survived them.
        (f"before{_ESC}[2Jafter", "beforeafter"),
        (f"before{_ESC}[HAfter", "beforeAfter"),
        (f"{_ESC}]0;window title\x07prompt", "prompt"),
        (f"{_ESC}(Bplain", "plain"),
        (f"{_ESC}=app mode", "app mode"),
    ],
)
def test_escape_sequences_are_removed(raw: str, expected: str) -> None:
    assert strip_ansi_escapes(raw) == expected


@pytest.mark.parametrize(
    "text",
    [
        "see [home](docs/home.md)",
        "[HEAD] detached",
        "a [1] footnote and a [list] item",
        "]0; not a title because no ESC",
        "[?2004h",
        "  leading and trailing  ",
    ],
)
def test_ordinary_text_is_returned_unchanged(text: str) -> None:
    """No pattern may match without the ESC byte — including the whitespace it keeps."""
    assert strip_ansi_escapes(text) == text


# --------------------------------------------------------------------------- #
# strip_ansi_codes: the terminal policy, and why it is separate
# --------------------------------------------------------------------------- #


def test_terminal_policy_still_strips_esc_less_artifacts() -> None:
    """The behaviour the PTY callers depend on, pinned by the existing doctest."""
    assert strip_ansi_codes("[?2004h]0;Title\x07Prompt$") == "Prompt$"
    assert strip_ansi_codes(f"{_ESC}[31mRed{_ESC}[0m Text") == "Red Text"


@pytest.mark.parametrize(
    "text,corrupted",
    [
        ("see [home](docs/home.md)", "see ome](docs/home.md)"),
        ("[HEAD] detached", "EAD] detached"),
    ],
)
def test_terminal_policy_is_destructive_on_prose(text: str, corrupted: str) -> None:
    """Pins *why* the split exists, so merging the two functions fails loudly.

    If someone later points a text-processing call site at strip_ansi_codes, this is the
    damage. Asserting it is deliberate: the day this stops being true, the split can be
    revisited, and until then the assertion is the argument.
    """
    assert strip_ansi_codes(text) == corrupted
    assert strip_ansi_escapes(text) == text


def test_terminal_policy_is_the_escape_policy_plus_two_patterns() -> None:
    """One implementation of the escape patterns, not two."""
    only_escapes = f"{_ESC}[31mRed{_ESC}[0m Text"
    assert strip_ansi_codes(only_escapes) == strip_ansi_escapes(only_escapes).strip()


# --------------------------------------------------------------------------- #
# The forks are gone and cannot come back unnoticed
# --------------------------------------------------------------------------- #

_CONSOLIDATED = (
    "autobot-backend/api/knowledge_population.py",
    "autobot-backend/services/tool_output_filter.py",
)
_ESC_PATTERN_LITERAL = re.compile(r"re\.compile\(\s*r?[\"'][^\"']*(?:\\x1[bB]|\\033|\\e\[)")


@pytest.mark.parametrize("relpath", _CONSOLIDATED)
def test_consolidated_sites_hold_no_ansi_regex(relpath: str) -> None:
    source = (_REPO / relpath).read_text(encoding="utf-8")
    found = _ESC_PATTERN_LITERAL.findall(source)
    assert not found, f"{relpath} compiles its own ANSI pattern again: {found}"


def test_a_double_escaped_ansi_pattern_would_be_a_no_op() -> None:
    """Pins the control string, because without it a dead stripper looks like a clean one.

    ``r'\\x1B'`` is a raw string holding a doubled backslash, so the regex engine sees an
    escaped backslash followed by ``x1B``: it matches the literal four-character text
    ``\x1b`` and never the ESC byte. Such a pattern strips nothing, and an input without a
    real ESC byte cannot tell the difference — which is why one survived review inside
    ``code_analysis/scripts/analyze_duplicates.py``'s code-generation template (#18093; the
    template is string data, not an executed path, and is tracked separately).
    """
    with warnings.catch_warnings():
        # The pattern's `[[0-?]` trips a nested-set FutureWarning. Reproducing it verbatim
        # is the point of this test, so the warning is expected, not a finding.
        warnings.simplefilter("ignore", FutureWarning)
        broken = re.compile(r"\\x1B(?:[@-Z\\\\-_]|\\[[0-?]*[ -/]*[@-~])")

    control = f"{_ESC}[31mRed{_ESC}[0m"
    assert broken.sub("", control) == control, "control: the no-op pattern leaves ESC input untouched"
    # What it *does* match is the five literal characters ``\x1B`` followed by one char
    # from ``[@-Z\\-_]``. Not a real escape — and not even the literal spelling of one,
    # since the second branch needs a literal backslash before the bracket.
    assert broken.sub("", r"\x1BA") == "", "it matches the literal text, not the ESC byte"
    assert broken.sub("", r"\x1B[31m") == r"\x1B[31m", "not even the literal spelling of a CSI sequence"
    assert strip_ansi_escapes(control) == "Red", "the canonical actually strips the ESC byte"


#: Source snippets `_ESC_PATTERN_LITERAL` must flag, and must not. Without the second
#: half, a detector that matches nothing produces exactly the same green as a clean
#: tree -- and the assertion above is `not found`, so a dead regex reads as success.
_MUST_FLAG = (
    r're.compile(r"\x1b\[[0-9;]*m")',
    r"re.compile('\033\[[0-9;]*m')",
    # `\e[` with a literal bracket -- the shell/`sed` spelling the detector's third
    # alternative targets; `\e\[` is a different string and genuinely does not match.
    r're.compile(r"\e[0m")',
    r're.compile(  r"\x1B[@-Z]")',
)
_MUST_NOT_FLAG = (
    r're.compile(r"[0-9;]*m")',
    r're.compile(r"^---[ \t]*$")',
    r'ANSI = "\x1b[0m"',
    r're.compile(r"%s")',
)


def test_the_consolidation_detector_has_a_contrast_pair() -> None:
    """The detector must flag a re-introduced ANSI pattern and ignore everything else.

    `test_consolidated_sites_hold_no_ansi_regex` asserts an EMPTY result, so a detector
    that stopped matching would keep it green forever. These synthetic snippets are what
    tells the two apart, and they localise the fault to the detector rather than to some
    file in the tree.
    """
    for snippet in _MUST_FLAG:
        assert _ESC_PATTERN_LITERAL.findall(snippet), f"detector missed a real ANSI pattern: {snippet!r}"
    for snippet in _MUST_NOT_FLAG:
        assert not _ESC_PATTERN_LITERAL.findall(snippet), f"detector falsely flagged: {snippet!r}"


def test_the_detectors_blind_spot_is_recorded() -> None:
    """Stated, not implied: this detector only sees `re.compile`.

    An inline `re.sub` with the same pattern re-introduces the concept without compiling
    it and is NOT caught here. Recorded as a test so a clean run is read as "no compiled
    pattern" rather than as "no ANSI handling", which is a different claim (#18093). The
    tree-wide guard that does cover call sites is
    `repo_tests/regex_concept_fork_guard_18093_test.py`, which reads the pattern argument
    of every `re.*` entry point.
    """
    inline = r're.sub(r"\x1b\[[0-9;]*m", "", text)'
    assert not _ESC_PATTERN_LITERAL.findall(inline), (
        "if this now matches, the detector grew to cover call sites -- widen "
        "_MUST_FLAG and delete this blind-spot record"
    )
