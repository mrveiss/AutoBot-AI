# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the same-scope batching gate (#15492).

Each case here fails when the element it names is removed from
``check_pr_issue_batching.py``. The mutation matrix is recorded in the PR body:
inverting the ``>= 2`` comparison reddens the batched case, and deleting the
rationale detection reddens the rationale case.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_pr_issue_batching import (  # noqa: E402
    RATIONALE_HINT,
    check,
    exemption,
    referenced_issues,
    single_issue_rationale,
)

TWO = "Closes #15178, #15173\n"
ONE = "Closes #15178\n"


class TestReferenceCounting:
    def test_every_repo_keyword_is_recognised(self) -> None:
        for word in ("resolves", "closes", "fixes", "refs", "references", "part of"):
            assert referenced_issues(f"{word} #42") == {"42"}, word

    def test_the_hash_is_optional_as_the_sibling_gate_allows(self) -> None:
        assert referenced_issues("closes 42") == {"42"}

    def test_the_same_issue_named_twice_counts_once(self) -> None:
        assert referenced_issues("Closes #42\nAlso refs #42") == {"42"}

    def test_an_mva_ticket_is_a_reference(self) -> None:
        assert referenced_issues("closes MVA-7") == {"MVA-7"}

    def test_a_bare_issue_number_is_not_a_reference(self) -> None:
        """Without a keyword it is prose, not a link -- #15178 alone must not count."""
        assert referenced_issues("this relates to #15178 somehow") == set()

    @pytest.mark.parametrize(
        ("body", "expected"),
        [
            ("Closes #15178, #15173", {"15178", "15173"}),
            ("Fixes #1 and #2", {"1", "2"}),
            ("refs #1, #2, and MVA-7", {"1", "2", "MVA-7"}),
            ("Closes #1,#2,#3", {"1", "2", "3"}),
        ],
    )
    def test_a_keyword_consumes_the_whole_list_after_it(self, body: str, expected: set) -> None:
        """`Closes #A, #B` is how this repo writes a batch, and only #A follows the
        keyword. Counting one-per-keyword would score every batched PR as single-issue
        and fail exactly the PRs this rule exists to reward.
        """
        assert referenced_issues(body) == expected


class TestCodeIsNotALink:
    """A reference inside code is an example. Found on this gate's own PR, whose
    worked examples scored as six extra issues -- left in, a PR could satisfy the
    batching rule entirely with sample text and never link anything real.
    """

    def test_a_fenced_block_contributes_nothing(self) -> None:
        assert referenced_issues("```\nCloses #1, #2\n```\n") == set()

    def test_a_tilde_fence_contributes_nothing(self) -> None:
        assert referenced_issues("~~~\nCloses #1, #2\n~~~\n") == set()

    def test_inline_code_contributes_nothing(self) -> None:
        assert referenced_issues("the string `Closes #1` is an example") == set()

    def test_prose_outside_a_fence_still_counts(self) -> None:
        body = "```\nCloses #1\n```\n\nCloses #15492, #15488\n"
        assert referenced_issues(body) == {"15492", "15488"}


class TestTheRuleItself:
    def test_two_issues_pass(self) -> None:
        ok, message = check(TWO)
        assert ok, message
        assert "#15173" in message and "#15178" in message

    def test_one_issue_fails_and_the_error_names_the_escape_hatch(self) -> None:
        ok, message = check(ONE)
        assert not ok
        assert "Single-issue rationale:" in message, message

    def test_one_issue_with_a_rationale_passes(self) -> None:
        ok, message = check(ONE + "Single-issue rationale: the other half is blocked on #15043\n")
        assert ok, message
        assert "blocked on #15043" in message

    def test_a_blank_rationale_does_not_pass(self) -> None:
        """An empty line satisfies the grep but not the requirement."""
        assert not check(ONE + "Single-issue rationale:   \n")[0]

    def test_no_reference_is_left_to_the_other_gate(self) -> None:
        ok, message = check("## What Changed\nnothing linked here\n")
        assert ok
        assert "pr-issue-validation" in message


class TestExemptions:
    @pytest.mark.parametrize(
        ("actor", "branch", "title", "why"),
        [
            ("dependabot[bot]", "dependabot/npm/x", "bump x", "dependabot"),
            ("someone", "hotfix-15499", "fix(x): urgent", "hotfix"),
            ("someone", "issue-1", "Revert \"feat(x): thing\"", "revert"),
        ],
    )
    def test_an_exempt_pr_passes_on_one_issue(
        self, actor: str, branch: str, title: str, why: str
    ) -> None:
        ok, message = check(ONE, actor, branch, title)
        assert ok, message
        assert why in message

    def test_a_normal_pr_is_not_exempt(self) -> None:
        assert exemption("someone", "issue-15492-batching-gate", "ci(guard): thing") is None

    def test_the_dependabot_check_is_not_a_substring_match(self) -> None:
        """A human named 'dependabot-wrangler' is not dependabot."""
        assert exemption("dependabot-wrangler", "issue-1", "feat: x") is None


class TestRationaleParsing:
    def test_the_line_is_found_anywhere_in_the_body(self) -> None:
        body = "## Thinking Path\nstuff\n\nSingle-issue rationale: standalone\n\n## What Changed\n"
        assert single_issue_rationale(body) == "standalone"

    def test_absent_returns_none(self) -> None:
        assert single_issue_rationale("## What Changed\n") is None


class TestRationaleAsAHeading:
    """`## Single-issue rationale` with the reason beneath it (#16050).

    Two independent sessions wrote it this way within four hours -- #16018, and
    #16049 which was the CRITICAL auth fix -- because it matches the section
    style the rest of the PR body uses. Two authors independently choosing a
    form the checker rejects is the checker's defect.
    """

    def test_a_heading_with_prose_beneath_it_counts(self) -> None:
        body = ONE + "## Single-issue rationale\n\nan auth fix must read in one pass\n"
        assert check(body)[0]
        assert single_issue_rationale(body) == "an auth fix must read in one pass"

    def test_the_reason_may_sit_several_blank_lines_down(self) -> None:
        """The naive fix reads only the next line, which is blank in every real body."""
        body = ONE + "## Single-issue rationale\n\n\n\nreason far below\n"
        assert single_issue_rationale(body) == "reason far below"

    def test_an_empty_section_does_not_borrow_the_next_one(self) -> None:
        """The contrast, and the one that keeps this a check rather than a keyword.

        This gate asks whether a human justified standing alone. A fix that
        matches the heading and stops looking lets any PR pass by including a
        heading with nothing under it -- and the next section's prose would be
        silently adopted as the rationale.
        """
        body = ONE + "## Single-issue rationale\n\n## What Changed\n\nunrelated prose\n"
        assert single_issue_rationale(body) is None
        assert not check(body)[0]

    def test_a_heading_at_the_end_of_the_body_is_not_a_rationale(self) -> None:
        assert single_issue_rationale(ONE + "## Single-issue rationale\n\n") is None

    def test_the_inline_form_still_works_and_still_rejects_a_blank(self) -> None:
        """Widening WHERE the reason may sit must not widen WHETHER one is needed."""
        assert single_issue_rationale(ONE + "Single-issue rationale: stands alone\n") == "stands alone"
        assert single_issue_rationale(ONE + "Single-issue rationale:   \n") is None

    def test_the_hint_names_both_accepted_forms(self) -> None:
        """The old hint printed one indented example, which read as illustration
        rather than as an exact-match requirement -- so the gate taught the shape
        it refused."""
        assert "## Single-issue rationale" in RATIONALE_HINT
        assert "Single-issue rationale: <why" in RATIONALE_HINT
