# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reading criteria, and refusing a citation that cannot be opened (#17090).

The half of the verifier with no model in it, tested as the facts it is: what
the issue says, and what merged code actually contains.
"""

from __future__ import annotations

import subprocess  # nosec B404 -- fixed argv, no shell; one positive control

import pytest

from agents.ac_criteria import (
    Citation,
    Criterion,
    code_searcher,
    criterion_terms,
    extract_criteria,
    file_reader,
    parse_citations,
    unparsed_amendment_hint,
    verify_citations,
)
from autobot_shared.paths import git_repo_root, scrubbed_git_env

_BODY = """## Problem

Something is wrong.

## Acceptance criteria

- [ ] The first criterion mentions `publish_event`
      and continues on a second line.
- [x] The second is already ticked
- [ ] The third only works on the live install

## Related

- [ ] This is not a criterion, it is under another heading
"""


class TestExtraction:
    def test_it_reads_only_the_acceptance_criteria_section(self):
        criteria = extract_criteria(_BODY)

        assert [c.index for c in criteria] == [1, 2, 3]
        assert all(c.source == "body" for c in criteria)
        assert "not a criterion" not in " ".join(c.text for c in criteria)

    def test_a_continuation_line_belongs_to_its_criterion(self):
        first = extract_criteria(_BODY)[0]

        assert first.text.endswith("continues on a second line.")

    def test_a_ticked_box_is_read_as_ticked(self):
        assert [c.checked for c in extract_criteria(_BODY)] == [False, True, False]

    def test_an_issue_without_the_heading_yields_nothing(self):
        """Nothing found, not nothing there -- the caller says so in its notes."""
        assert extract_criteria("## Problem\n- [ ] a box with no AC heading\n") == []

    def test_a_comment_restating_criteria_amends_the_set(self):
        comments = [("c9", "## Acceptance criteria\n- [ ] A criterion added later\n")]

        criteria = extract_criteria(_BODY, comments)

        assert criteria[-1].source == "comment:c9"
        assert criteria[-1].index == 4

    def test_a_prose_amendment_is_reported_rather_than_parsed(self):
        hint = unparsed_amendment_hint([("c9", "criterion 2 no longer applies")])

        assert hint is not None and "c9" in hint

    def test_a_comment_that_restates_the_list_is_not_also_flagged_as_unread(self):
        """It WAS read, so warning about it would teach readers to ignore the warning."""
        assert unparsed_amendment_hint([("c9", "## Acceptance criteria\n- [ ] amend: a new one\n")]) is None


class TestHostEvidence:
    @pytest.mark.parametrize(
        "text",
        [
            "works on the live install",
            "the unit is enabled in systemd",
            "the file lands under /opt/autobot",
            "verified in production",
        ],
    )
    def test_a_criterion_about_a_running_system_is_flagged(self, text):
        assert Criterion(1, text, False, "body").needs_host_evidence

    def test_an_ordinary_code_criterion_is_not(self):
        """The negative control: over-flagging would make every verdict unavailable."""
        assert not Criterion(1, "`publish_event` is called with a scoped channel", False, "body").needs_host_evidence


class TestCitations:
    def test_it_finds_citations_and_drops_duplicates(self):
        found = parse_citations("see a/b.py:12, again a/b.py:12, and c/d.ts:3")

        assert [str(c) for c in found] == ["a/b.py:12", "c/d.ts:3"]

    def test_a_sentence_with_a_colon_is_not_a_citation(self):
        assert parse_citations("the ratio was 3:1 and the note said: done") == []

    def test_a_real_line_is_accepted(self):
        verified, rejected = verify_citations([Citation("x.py", 2)], lambda _p: "one\ntwo\n")

        assert [str(c) for c in verified] == ["x.py:2"] and rejected == []

    def test_a_line_past_the_end_is_rejected(self):
        verified, rejected = verify_citations([Citation("x.py", 9)], lambda _p: "one\ntwo\n")

        assert verified == [] and "file has 2 line(s)" in rejected[0]

    def test_a_missing_file_is_rejected(self):
        verified, rejected = verify_citations([Citation("x.py", 1)], lambda _p: None)

        assert verified == [] and "no such file" in rejected[0]

    def test_a_blank_line_is_rejected(self):
        verified, rejected = verify_citations([Citation("x.py", 2)], lambda _p: "one\n\nthree\n")

        assert verified == [] and "blank" in rejected[0]


class TestTerms:
    def test_backticked_tokens_are_what_gets_searched(self):
        terms = criterion_terms(Criterion(1, "`VALID_KINDS` includes `issue` in `work_claims.py`", False, "body"))

        assert terms == ["VALID_KINDS", "issue", "work_claims.py"]

    def test_a_criterion_naming_nothing_searchable_yields_no_terms(self):
        """No terms means no evidence means can't tell -- the safe direction."""
        assert criterion_terms(Criterion(1, "the design is tasteful", False, "body")) == []


def _has_ref(ref: str = "origin/main") -> bool:
    result = subprocess.run(  # nosec B603 B607 -- fixed argv, no shell
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        cwd=str(git_repo_root()),
        env=scrubbed_git_env(),
        check=False,
    )
    return result.returncode == 0


class TestTheGitPlumbingActuallyReads:
    """Positive controls. Every test above substitutes the reader, so without
    these the module could be perfect and still read nothing from merged code."""

    @pytest.mark.skipif(not _has_ref(), reason="origin/main is not present in this checkout")
    def test_the_reader_opens_a_file_that_exists_in_merged_code(self):
        content = file_reader()("CLAUDE.md")

        assert content and "AutoBot Development Instructions" in content

    @pytest.mark.skipif(not _has_ref(), reason="origin/main is not present in this checkout")
    def test_the_reader_reports_none_for_a_path_that_does_not_exist(self):
        assert file_reader()("no/such/file/at/all.py") is None

    @pytest.mark.skipif(not _has_ref(), reason="origin/main is not present in this checkout")
    def test_the_searcher_finds_a_term_that_is_really_there(self):
        hits = code_searcher()(["VALID_KINDS"])

        assert "work_claims.py:" in hits, "the searcher must return `path:line:` citations, not a ref-prefixed form"

    @pytest.mark.skipif(not _has_ref(), reason="origin/main is not present in this checkout")
    def test_the_searcher_says_so_when_a_term_matches_nothing(self):
        assert "no match" in code_searcher()(["ZzQqNoSuchIdentifierAnywhere"])
