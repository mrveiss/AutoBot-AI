# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A quoted marker is text, a real one is a boundary (#17513).

Reported from a live session: one answer arrived as two messages, the second
badged **Thought**. The line that did it was the model documenting the markers::

    - Thinking tags (`[THOUGHT]`, `[PLANNING]`) requirements

The persisted text was intact -- the split happened in the streaming classifier,
which matched the markers with a plain regex and could not tell a marker the
model QUOTED from one it emitted.

Every test here pairs a quoted case with a real one. Without the real-marker
assertions the whole file would be satisfied by a classifier that never splits
anything again, which trades a visible bug for an invisible one.
"""

from __future__ import annotations

import pytest

from chat_workflow.thought_markers import (
    detect_content_type,
    find_last_tag_positions,
    find_new_segment_start,
    mask_code_regions,
)

#: The exact line from the reported session.
REPORTED_LINE = "- Thinking tags (`[THOUGHT]`, `[PLANNING]`) requirements"


class TestTheReportedRegression:
    def test_the_reported_line_is_one_response_segment(self) -> None:
        assert detect_content_type(REPORTED_LINE) == "response"

    def test_the_reported_line_yields_no_segment_boundary(self) -> None:
        # The boundary is what severed the reply: content after the marker
        # became a new message and the text before it was cut off mid-clause.
        assert find_new_segment_start(REPORTED_LINE, "thought") == ""
        assert find_new_segment_start(REPORTED_LINE, "planning") == ""

    def test_no_marker_position_is_reported_for_the_quoted_line(self) -> None:
        assert find_last_tag_positions(REPORTED_LINE) == {
            "thought_start": -1,
            "thought_end": -1,
            "planning_start": -1,
            "planning_end": -1,
        }

    def test_the_full_reported_paragraph_survives_intact(self) -> None:
        # The surrounding bullets are what the user saw split across two
        # messages, so the paragraph is asserted as a whole.
        paragraph = (
            "- Multi-step task execution procedures\n" f"{REPORTED_LINE}\n" "- Personality and tone guidelines\n"
        )

        assert detect_content_type(paragraph) == "response"
        assert find_new_segment_start(paragraph, "thought") == ""


class TestARealMarkerStillSplits:
    """The control. Without these, "never split" would pass everything above."""

    def test_an_open_thought_block_is_typed_thought(self) -> None:
        assert detect_content_type("Let me think. [THOUGHT]weighing options") == "thought"

    def test_the_segment_is_the_content_after_the_marker(self) -> None:
        text = "Let me think. [THOUGHT]weighing options"

        assert find_new_segment_start(text, "thought") == "weighing options"

    def test_a_closed_thought_block_returns_to_response(self) -> None:
        assert detect_content_type("[THOUGHT]done[/THOUGHT] Here is the answer.") == "response"

    def test_response_resumes_after_the_closing_marker(self) -> None:
        text = "[THOUGHT]done[/THOUGHT] Here is the answer."

        assert find_new_segment_start(text, "response", previous_type="thought") == " Here is the answer."

    def test_an_open_planning_block_is_typed_planning(self) -> None:
        assert detect_content_type("[PLANNING]step one") == "planning"


class TestQuotedAndRealTogether:
    """A reply may document a marker AND use one; both must be honoured."""

    def test_a_real_marker_after_a_quoted_one_still_splits(self) -> None:
        text = f"{REPORTED_LINE}\n[THOUGHT]actually reasoning now"

        assert detect_content_type(text) == "thought"
        assert find_new_segment_start(text, "thought") == "actually reasoning now"

    def test_several_quoted_markers_on_one_line_are_all_ignored(self) -> None:
        # `find_new_segment_start` keeps the LAST match, so with several quoted
        # markers the boundary landed after the final one -- which is why the
        # remainder read `) requirements` rather than the intended text.
        text = "see `[THOUGHT]`, `[/THOUGHT]`, `[PLANNING]` and `[/PLANNING]` for details"

        assert detect_content_type(text) == "response"
        assert find_new_segment_start(text, "thought") == ""
        assert find_new_segment_start(text, "response", previous_type="thought") == ""


class TestFencedBlocks:
    def test_a_marker_in_a_fenced_block_is_not_a_boundary(self) -> None:
        text = "Example:\n```\n[THOUGHT]like this[/THOUGHT]\n```\nThat is the format."

        assert detect_content_type(text) == "response"
        assert find_new_segment_start(text, "thought") == ""

    def test_a_marker_in_a_double_backtick_span_is_not_a_boundary(self) -> None:
        assert detect_content_type("use ``[THOUGHT]`` verbatim") == "response"


class TestTheStreamingCase:
    """Detection runs on text still arriving, so spans are often unclosed."""

    def test_a_quoted_marker_is_ignored_before_its_span_closes(self) -> None:
        # The chunk boundary that would otherwise break the reply one chunk
        # early: the opening backtick has arrived, the closing one has not.
        partial = "- Thinking tags (`[THOUGHT]"

        assert detect_content_type(partial) == "response"
        assert find_new_segment_start(partial, "thought") == ""

    def test_a_real_marker_is_still_seen_when_no_backtick_is_open(self) -> None:
        # The other half: an unclosed-span rule must not swallow real markers in
        # ordinary prose.
        assert detect_content_type("thinking about it [THOUGHT]here goes") == "thought"

    @pytest.mark.parametrize(
        "prefix",
        ["", "hello ", "a `code` span then ", "```\nfence\n```\n"],
        ids=["bare", "prose", "after-closed-span", "after-fence"],
    )
    def test_a_real_marker_survives_various_prefixes(self, prefix: str) -> None:
        assert detect_content_type(f"{prefix}[THOUGHT]reasoning") == "thought"


class TestTheMaskItself:
    def test_the_mask_preserves_length(self) -> None:
        # Load-bearing: positions found in the masked copy are used to slice the
        # ORIGINAL text, so any length change would corrupt the segment.
        for text in (REPORTED_LINE, "```\n[THOUGHT]\n```", "a `b` c", "unclosed `span"):
            assert len(mask_code_regions(text)) == len(text), text

    def test_the_mask_blanks_code_and_keeps_prose(self) -> None:
        masked = mask_code_regions("keep `[THOUGHT]` keep")

        assert "[THOUGHT]" not in masked
        assert masked.startswith("keep ")
        assert masked.endswith(" keep")

    def test_the_mask_leaves_text_without_code_untouched(self) -> None:
        text = "no code here [THOUGHT] at all"

        assert mask_code_regions(text) == text
