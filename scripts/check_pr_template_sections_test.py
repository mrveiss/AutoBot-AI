# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the PR template section gate (#6474, diagnosis split in #16793).

The load-bearing case is ``test_the_two_failures_do_not_produce_the_same_output``:
it fails the moment the absent and empty branches are collapsed back together,
which is the defect #16793 fixed. Every other case here fails when the element
it names is removed from ``check_pr_template_sections.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_pr_template_sections import (  # noqa: E402
    REQUIRED_SECTIONS,
    TEMPLATE_PATH,
    headings,
    report,
    section_content,
)

COMPLETE = (
    "## Thinking Path\nwhy\n\n"
    "## What Changed\nwhat\n\n"
    "## Verification\nhow\n\n"
    "## Model Used\nOpus 5\n"
)
# The shape that produced four "empty section" errors on a complete body: a PR
# opened with `gh pr create --body`, which never loads the template (#16793).
WRONG_HEADINGS = "## Summary\nwhat this does\n\n## Test plan\nran the suite\n"
# Heading present, nothing beneath it -- the one state the old message described
# accurately.
EMPTY_SECTION = COMPLETE.replace("## Verification\nhow\n", "## Verification\n")


class TestExtraction:
    def test_a_complete_body_passes(self) -> None:
        ok, lines = report(COMPLETE)
        assert ok, lines
        assert sum("': OK" in line for line in lines) == len(REQUIRED_SECTIONS)

    def test_an_absent_heading_reads_as_none_not_empty(self) -> None:
        """The distinction the whole gate rests on."""
        assert section_content(WRONG_HEADINGS, "Verification") is None
        assert section_content(EMPTY_SECTION, "Verification") == ""

    def test_a_comment_only_section_is_still_empty(self) -> None:
        body = COMPLETE.replace("## Verification\nhow\n", "## Verification\n<!-- how -->\n")
        assert section_content(body, "Verification") == ""

    def test_a_sub_heading_does_not_end_a_section(self) -> None:
        body = COMPLETE.replace("## Verification\nhow\n", "## Verification\n### Unit\nhow\n")
        assert section_content(body, "Verification") == "### Unit\nhow"

    def test_the_next_section_is_not_borrowed_as_content(self) -> None:
        assert section_content(EMPTY_SECTION, "Verification") == ""

    def test_a_heading_with_a_suffix_still_matches(self) -> None:
        """`/^## Verification/` was a prefix match; keeping it keeps what passes."""
        body = COMPLETE.replace("## Verification\n", "## Verification (manual)\n")
        assert section_content(body, "Verification") == "how"

    def test_headings_are_reported_verbatim_and_in_order(self) -> None:
        assert headings(WRONG_HEADINGS) == ["Summary", "Test plan"]
        assert headings("no headings here\n") == []


class TestTheTwoFailuresAreToldApart:
    """A missing heading and an empty one want opposite fixes (#16793).

    Reporting "empty" for an absent heading sent four authors in one afternoon
    to search a complete body for a blank section. A red only self-corrects when
    it names its real cause.
    """

    def test_the_two_failures_do_not_produce_the_same_output(self) -> None:
        missing = "\n".join(report(WRONG_HEADINGS)[1])
        empty = "\n".join(report(EMPTY_SECTION)[1])
        assert not report(WRONG_HEADINGS)[0] and not report(EMPTY_SECTION)[0]
        assert missing != empty, "the absent and empty branches have been collapsed again"

    def test_an_absent_heading_says_absent_and_not_empty(self) -> None:
        text = "\n".join(report(WRONG_HEADINGS)[1])
        assert "missing, not empty" in text
        assert "is empty. Please fill it in" not in text, "the misleading message came back"

    def test_an_absent_heading_lists_the_four_required_headings_verbatim(self) -> None:
        text = "\n".join(report(WRONG_HEADINGS)[1])
        for section in REQUIRED_SECTIONS:
            assert f"## {section}" in text, section

    def test_an_absent_heading_names_what_was_found_instead(self) -> None:
        """Without this the author cannot see why a filled-in body failed."""
        text = "\n".join(report(WRONG_HEADINGS)[1])
        assert "## Summary" in text and "## Test plan" in text

    def test_a_body_with_no_headings_at_all_says_so_rather_than_listing_nothing(self) -> None:
        text = "\n".join(report("just prose, no headings\n")[1])
        assert "no `## ` headings at all" in text

    def test_the_failure_names_the_template_as_the_source_of_truth(self) -> None:
        assert TEMPLATE_PATH in "\n".join(report(WRONG_HEADINGS)[1])

    def test_an_empty_section_keeps_the_original_wording(self) -> None:
        text = "\n".join(report(EMPTY_SECTION)[1])
        assert "Required section 'Verification' is empty. Please fill it in before merging." in text

    def test_the_summary_keeps_the_two_counts_apart(self) -> None:
        mixed = WRONG_HEADINGS + "## Thinking Path\nwhy\n\n## What Changed\n"
        text = "\n".join(report(mixed)[1])
        assert "2 absent" in text and "1 present but empty" in text, text


class TestTheRuleIsUnchanged:
    """#16793 changed the diagnosis, not what is required."""

    def test_every_template_heading_is_still_required(self) -> None:
        for section in REQUIRED_SECTIONS:
            body = COMPLETE.replace(f"## {section}\n", "## Something Else\n")
            assert not report(body)[0], section

    def test_an_empty_body_fails(self) -> None:
        assert not report("")[0]
