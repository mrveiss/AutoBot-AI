# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Bracket SHAPE is cosmetic, and markdown is not a tool call (#18065).

Every pattern in ``tool_call_grammar`` hardcoded ``<``/``>``. A model emitting
square brackets matched none of them, which cost BOTH halves at once: the call
was never executed, and the raw markup was never stripped -- a square tag fails
``TOOL_CALL_OPENING_RE``, which is the early-return guard in
``strip_unparsed_tool_tags``. Reported live as ``[/TOOL_CALL>``.

The risk the fix has to carry is that ``[`` is markdown. These tests therefore
pin the NEGATIVE cases as hard as the positive ones: a normaliser that quietly
ate ``[the docs](url)`` would be a worse defect than the leak it fixed.
"""

from __future__ import annotations

import pytest

from chat_workflow.tool_call_grammar import (
    TOOL_CALL_PATTERN,
    normalize_tool_call_brackets,
    strip_unparsed_tool_tags,
)

#: The shape reported from a live session, plus the symmetric square form.
REPORTED = "[/TOOL_CALL>"
SQUARE_CLOSE = "[/TOOL_CALL]"

#: A square-bracket call whose params contain a JSON array. The `]` inside
#: `params` is the trap: a normaliser anchored on the first `]` cuts the JSON in
#: half and produces a tag that parses into a WRONG argument, which is worse than
#: not parsing at all.
SQUARE_WITH_JSON_LIST = '[TOOL_CALL name="run" params=\'{"a":[1,2]}\']do it[/TOOL_CALL]'


@pytest.mark.parametrize("raw", [REPORTED, SQUARE_CLOSE])
def test_a_square_close_becomes_the_angle_spelling(raw: str) -> None:
    assert normalize_tool_call_brackets(raw) == "</TOOL_CALL>"


def test_a_square_call_parses_after_normalising_and_keeps_its_json_intact() -> None:
    """The execution half: the tool must actually run, with unmangled params."""
    match = TOOL_CALL_PATTERN.search(normalize_tool_call_brackets(SQUARE_WITH_JSON_LIST))
    assert match is not None, "a square-bracket call still does not parse"
    assert match.group(1) == "run"
    # The whole JSON object, not a prefix ending at the first `]`.
    assert match.group(3) == '{"a":[1,2]}'


def test_a_mixed_bracket_call_parses() -> None:
    mixed = '[TOOL_CALL name="run" params="{}">do it</TOOL_CALL>'
    assert TOOL_CALL_PATTERN.search(normalize_tool_call_brackets(mixed)) is not None


def test_normalising_is_idempotent_on_angle_brackets() -> None:
    """CONTROL. Without this, a normaliser that rewrote everything would pass above."""
    angle = '<TOOL_CALL name="run" params="{}">do it</TOOL_CALL>'
    assert normalize_tool_call_brackets(angle) == angle
    assert normalize_tool_call_brackets(normalize_tool_call_brackets(angle)) == angle


@pytest.mark.parametrize(
    "prose",
    [
        "see [the docs](https://example.test/y) for more",
        "a reference [a list][1] and its target",
        "[THOUGHT] analysing [1, 2, 3] now",
        "the [toolbox] is fine",
        "[tool] and [call] apart are not a tag",
        "nothing bracketed here at all",
        "",
    ],
)
def test_markdown_and_prose_are_never_touched(prose: str) -> None:
    """THE negative contract. `[` is markdown first and a tool call second."""
    assert normalize_tool_call_brackets(prose) == prose


@pytest.mark.parametrize("prose", ["see [the docs](https://example.test/y)", "[THOUGHT] hi"])
def test_prose_never_becomes_a_parsable_tool_call(prose: str) -> None:
    """Stronger than 'unchanged': it must not parse even if some rewrite happened."""
    assert TOOL_CALL_PATTERN.search(normalize_tool_call_brackets(prose)) is None


@pytest.mark.parametrize("marker", ["[/TOOL_CALL>", "[/TOOL_CALL]", "</TOOL_CALL>"])
def test_a_dangling_close_with_no_open_tag_is_stripped(marker: str) -> None:
    """THE reported symptom, and the case normalising alone does not fix.

    A bare close sitting in a reply has no opening tag, so
    `strip_unparsed_tool_tags` used to hit its first early return and leave the
    marker on screen forever. Rewriting its brackets does not help: the early
    return fires before anything else can.
    """
    cleaned = strip_unparsed_tool_tags(f"Here is the answer.\n{marker}")
    assert "TOOL_CALL" not in cleaned, cleaned
    assert "[/" not in cleaned, cleaned
    assert cleaned == "Here is the answer."


def test_an_unparsable_open_tag_is_stripped_with_its_prose_kept() -> None:
    """The other leak shape: an open tag that never completed into a call.

    `strip_unparsed_tool_tags` normalises internally, because its caller in
    `manager._build_final_response_entry` is on a different path from
    `manager._normalize_tool_call_text`.
    """
    leaked = 'Checking resources.\n\n[TOOL_CALL name="run" params="{}"]'
    cleaned = strip_unparsed_tool_tags(leaked)
    assert "TOOL_CALL" not in cleaned, cleaned
    assert "Checking resources." in cleaned, "the prose around the tag was discarded"


def test_prose_with_neither_tag_is_returned_untouched() -> None:
    """CONTROL for both strip paths: no tag, no rewrite, no strip()-ing of content."""
    prose = "A reply mentioning [the docs](https://example.test) and nothing else.\n"
    assert strip_unparsed_tool_tags(prose) == prose


def test_a_well_formed_square_call_is_left_for_the_parser_not_stripped() -> None:
    """Contrast with the test above: a call that CAN parse must survive the stripper.

    Stripping it would be the old bug inverted -- the user stops seeing markup and
    the tool still never runs.
    """
    assert "TOOL_CALL" in strip_unparsed_tool_tags(SQUARE_WITH_JSON_LIST)
