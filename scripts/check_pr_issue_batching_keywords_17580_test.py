# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# scripts/check_pr_issue_batching_keywords_17580_test.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The closing-keyword set, and the mid-sentence warning (#17580).

Split from ``check_pr_issue_batching_test.py``, which reached the 600-line ceiling:
these cases are about which words GitHub closes on and where they appear, while that
file is about the batching verdict.

Both gates knew three of GitHub's nine keywords, and agreeing with each other is
what hid it -- the invariant they were written to protect held while both diverged
from the platform that does the closing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_pr_issue_batching import (  # noqa: E402
    _CLOSING_WORDS,
    check,
    closing_issues,
    mid_sentence_closings,
)

# ---------------------------------------------------------------------------
# GitHub's closing keywords (#17580)
#
# Both gates knew three of the nine, and agreeing with each other is what hid
# it: the invariant they were written to protect held while both diverged from
# the platform that does the closing. `Fix #N` read as no reference at all while
# GitHub closed the issue, and `Fix #A`/`Fix #B` scored as closing nothing, so a
# batch was never asked for its rationale.
# ---------------------------------------------------------------------------

#: GitHub's documented set, three inflections of three verbs. Written out rather
#: than generated, because a generator would reproduce whatever mistake its
#: pattern contained -- the point of this list is to be independently readable
#: against the platform documentation.
GITHUB_CLOSING_KEYWORDS = (
    "close",
    "closes",
    "closed",
    "fix",
    "fixes",
    "fixed",
    "resolve",
    "resolves",
    "resolved",
)

_WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pr-issue-validation.yml"


def _checker_keywords() -> set[str]:

    return set(_CLOSING_WORDS.split("|"))


_MENTIONS = {"refs", "references", "part of"}


def _workflow_keyword_sets() -> list[tuple[int, set[str]]]:
    """EVERY closing-keyword alternation in the sibling workflow, with its line.

    This used to be `next(ln for ln in ... if "grep -iqE" in ln)` -- the FIRST
    such line, which is the link-check near the top of the file. The workflow has
    a second alternation, the fork-override `keyword_re`, and it sat at three of
    the nine keywords while the checked one had all nine. So the parity test
    covering "the two gates cannot disagree" was itself reading a narrower
    population than the rule it enforced, which is the shape #17580 is about.

    Discovered by asking which alternations exist rather than re-running the one
    that was already found: re-running confirms the line, never the omission.

    Any parenthesised alternation naming at least one closing keyword counts, so
    a third one added later is checked without this helper being touched. The
    reference-shape groups (`(#?[0-9]+|MVA-[0-9]+)`) and the boundary group
    (`(^|[^[:alnum:]_-])`) are alternations too and are skipped because they name
    no keyword.
    """
    found: list[tuple[int, set[str]]] = []
    for lineno, line in enumerate(_WORKFLOW.read_text(encoding="utf-8").splitlines(), 1):
        for group in re.findall(r"\(([^()]+)\)", line):
            parts = [part.strip() for part in group.split("|")]
            if len(parts) < 2 or not any(part in GITHUB_CLOSING_KEYWORDS for part in parts):
                continue
            found.append((lineno, {part for part in parts if part not in _MENTIONS}))
    return found


@pytest.mark.parametrize("keyword", GITHUB_CLOSING_KEYWORDS)
def test_every_github_closing_keyword_is_recognised_as_closing(keyword):
    """The behavioural half: the gate must agree with what GitHub will do on merge."""
    assert closing_issues(f"{keyword.capitalize()} #12345") == {
        "12345"
    }, f"{keyword!r} closes the issue on GitHub; this gate must count it as delivered"


def test_the_checker_knows_exactly_githubs_set():
    missing = set(GITHUB_CLOSING_KEYWORDS) - _checker_keywords()
    extra = _checker_keywords() - set(GITHUB_CLOSING_KEYWORDS)

    assert not missing, f"GitHub closes on these and the gate does not see them: {sorted(missing)}"
    assert not extra, f"the gate treats these as closing and GitHub does not: {sorted(extra)}"


def test_both_gates_know_the_same_set():
    """The invariant the original comment protects, now checked rather than remembered.

    Hand-maintained parity is why the divergence from GitHub survived: the two
    files agreed, so there was nothing to notice.
    """
    alternations = _workflow_keyword_sets()
    assert alternations, (
        "no closing-keyword alternation found in the workflow at all -- this test "
        "would pass vacuously, so it fails instead (nothing found != did not look)"
    )
    expected = _checker_keywords()
    for lineno, words in alternations:
        assert words == expected, (
            f"{_WORKFLOW.name}:{lineno} disagrees with the checker about what a "
            f"closing keyword is — workflow-only: {sorted(words - expected)}, "
            f"checker-only: {sorted(expected - words)}"
        )


def test_the_longest_inflection_comes_first_in_each_verb():
    """A convention pin, and deliberately labelled as one.

    I expected `close` ahead of `closes` to match the stem and then fail the whitespace match.
    It does not: Python's `re` backtracks into the remaining alternatives, and the
    sibling gate's `grep -E` is POSIX leftmost-longest. Reordering this set
    alphabetically leaves all nine keyword tests green — measured, by doing it.

    So this asserts a convention: inflections grouped per verb, longest first, so
    the set stays readable and diffable against the workflow's copy. It is kept
    because the trap is real in a leftmost-first engine without backtracking, and
    whoever ports this pattern will meet it.
    """
    order = _CLOSING_WORDS_ORDER = _CLOSING_WORDS.split("|")
    for stem in ("close", "fix", "resolve"):
        inflections = [w for w in order if w.startswith(stem)]
        assert (
            inflections[-1] == stem
        ), f"{stem!r} must come last among {inflections} — an earlier stem shadows its own inflections"
    assert _CLOSING_WORDS_ORDER  # the split produced something


def test_a_negated_closing_keyword_still_counts_as_closing():
    """GitHub does not parse negation, so neither may the gate (#17580).

    Four merged PRs closed an issue with a body reading "does not close #N".
    A gate that honoured the prose would disagree with the platform and report a
    delivery that did not happen — or hide one that did.
    """
    assert closing_issues("This PR does not close #12345") == {"12345"}


# ---------------------------------------------------------------------------
# AC3: a closing keyword mid-sentence is flagged (#17580)
#
# GitHub closes on it and does not read negation. #16464 was closed at
# 00:40:55Z by PR #17544, whose body reads "this PR does not close #16464",
# while this gate reported "closes nothing" — the author's check agreed with the
# author's intent and the platform did the opposite.
# ---------------------------------------------------------------------------

#: The exact sentence from the PR that closed #16464, kept verbatim as the fixture.
NEGATED_FIXTURE = "**Acceptance criteria — this PR does not close #16464.**"


def test_the_16464_sentence_is_flagged():
    assert mid_sentence_closings(NEGATED_FIXTURE) == {"16464"}


def test_the_warning_reaches_the_author():
    ok, message = check(f"{NEGATED_FIXTURE}\nRefs #16464\n")

    assert ok, "AC3 asks for a warning, not a failure -- the platform's behaviour is not the author's defect"
    assert "::warning::" in message
    assert "16464" in message
    assert "does not read negation" in message


@pytest.mark.parametrize(
    "line",
    [
        "Closes #123",
        "- Closes #123",
        "> Closes #123",
        "**Closes #123**",
        "  Fixes #123",
        "1. Closes #123",
        "2) Fixes #123",
        "- [x] Closes #123",
        "- [ ] Resolves #123",
    ],
    ids=["plain", "bullet", "quote", "bold", "indented", "numbered", "paren-numbered", "checked", "unchecked"],
)
def test_a_deliberate_declaration_is_not_flagged(line):
    """Every lead-in an author actually uses for a real closing line.

    The last four were reported as mid-sentence prose: the lead-in class held
    whitespace and markdown punctuation but not digits, `.`, `)`, `[` or `]`.
    A numbered list and a task-list checkbox are the two most ordinary ways to
    write a deliberate closing line -- the repository's own PR template asks for
    the checkbox form -- so the warning fired on the authors who had done it
    right, which is the failure mode that teaches people to ignore a warning.
    """
    assert mid_sentence_closings(line) == set()


# ---------------------------------------------------------------------------
# The left word boundary (#17580)
#
# Widening the alternation to bare stems (`fix`, `close`, `resolve`) is what
# turned a missing boundary into a live defect: every one of these bodies
# matched a closing keyword as a SUBSTRING of an ordinary English word. The
# direction is what makes it more than a nit -- each one makes the link gate
# report SATISFIED and inflates the batching count, so the guard certifies a
# body that says the opposite of what it is credited with. `unresolved #1234`
# is the worst of them.
#
# The fork-override alternation in the workflow already carried this boundary,
# with a comment explaining it; the widened patterns did not inherit it.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "body",
    [
        "This remains unresolved #1234",
        "still unfixed #99",
        "we disclose #5 as an example",
        "the issue is enclosed #77",
        "prefixes #12345",
        "the self-closes #8 case",
    ],
    ids=["unresolved", "unfixed", "disclose", "enclosed", "prefixes", "hyphenated"],
)
def test_a_keyword_inside_a_word_is_not_a_reference(body):
    """A keyword must be a word, not a substring of one."""
    assert closing_issues(body) == set(), (
        f"{body!r} names no issue -- matching it makes the link gate pass and the "
        f"batching count rise on a body that references nothing"
    )


@pytest.mark.parametrize(
    "body",
    ["Closes #4242", "closes #4242", "(closes #4242)", "- [x] Closes #4242", "See also: fixes #4242"],
    ids=["plain", "lower", "parenthesised", "checkbox", "after-colon"],
)
def test_the_boundary_does_not_cost_a_real_reference(body):
    """The contrast case: a boundary that also rejected real references would be a
    worse bug than the one it fixes, so each punctuation lead-in is pinned."""
    assert closing_issues(body) == {"4242"}


def test_the_batching_count_still_includes_a_mid_sentence_closing():
    """Deliberately NOT subtracted: GitHub closes them, so the count must say so.

    Reporting a lower count here would make the gate disagree with the platform in
    the other direction — the defect #17580 is about, mirrored.
    """
    body = "This does not close #1 and does not fix #2.\n"

    assert closing_issues(body) == {"1", "2"}


def test_a_mixed_body_flags_only_the_mid_sentence_one():
    body = "Closes #10\n\nBackground: this does not close #11.\n"

    assert closing_issues(body) == {"10", "11"}
    assert mid_sentence_closings(body) == {"11"}


def test_the_warning_is_prepended_to_a_batched_verdict_too():
    """GitHub closes regardless of whether this gate is satisfied."""
    body = "Closes #10\nCloses #11\n\nNote: does not close #12.\n"

    ok, message = check(body)

    assert ok
    assert "::warning::" in message
    assert "Batched: closes 3 issues" in message, "the verdict itself must survive the prepend"


def test_a_body_using_only_non_s_keywords_is_reported_as_batched():
    """AC4 literally: the batching **verdict**, not just the extracted count.

    Consequence 1 in #17580 is about what the gate *reports*: `Fix #A` / `Fix #B`
    closed two issues and scored as closing nothing, so a batch was never asked for
    a rationale. The tests above assert `closing_issues`, which is the input to that
    verdict rather than the verdict — so the step a reader of AC4 checks was covered
    only by inference. This asserts it directly, with no `-s` keyword anywhere in the
    body.
    """
    ok, message = check("Fix #101\nFix #102\nFix #103\n")

    assert ok
    assert "Batched: closes 3 issues" in message, (
        "a body closing three issues with `Fix` must report as batched — "
        "reporting nothing is the defect this issue exists to remove"
    )


# ---------------------------------------------------------------------------
# The colon form (#17580, review)
#
# GitHub's documentation: "The keywords can be followed by colons or in
# uppercase. For example: `Closes: #10`, `CLOSES #10`, or `CLOSES: #10`."
#
# Both gates required whitespace IMMEDIATELY after the keyword, so `Fixes: #123`
# closed the issue on merge while the link gate rejected the PR for having no
# linkage and the batching count omitted it. That is this file's own subject in
# the opposite direction from the missing inflections: there the gates saw no
# reference where GitHub saw one; here they see none where GitHub *closes*.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("keyword", GITHUB_CLOSING_KEYWORDS)
def test_the_colon_form_closes_for_every_keyword(keyword):
    assert closing_issues(f"{keyword.capitalize()}: #12345") == {
        "12345"
    }, f"{keyword!r} followed by a colon closes the issue on GitHub; this gate must count it"


@pytest.mark.parametrize(
    "body",
    ["CLOSES: #10", "- [x] Fixes: #10", "1. Resolves: #10", "> Closed: #10", "**Closes: #10**"],
    ids=["upper", "checkbox", "numbered", "quote", "bold"],
)
def test_the_colon_form_in_the_documented_and_template_shapes(body):
    """Colon plus whitespace, in the lead-ins authors actually use."""
    assert closing_issues(body) == {"10"}, f"{body!r} parsed as {closing_issues(body)}"


def test_a_colon_with_no_space_before_the_reference_is_a_STATED_gap():
    """``Closes:#10`` -- GitHub's behaviour for this form is not established.

    Its documentation says the keywords "can be followed by colons" and every
    example it gives has a space (``Closes: #10``). It does not say whether the
    space is required, so the pattern keeps ``\\s+`` after the optional colon and
    this form is rejected.

    Asserted rather than left unwritten, so the choice is visible and a change to
    it is deliberate. Deliberately NOT written as "either answer is acceptable":
    the first version of this test asserted ``"10" in closing_issues(body) or
    closing_issues(body) == set()``, which passes whichever way the gate behaves
    and therefore records nothing -- the same could-not-fail shape this file's
    other guards exist to catch.
    """
    assert closing_issues("Closes:#10") == set(), (
        "the gate now accepts a colon with no following whitespace -- if that was deliberate, "
        "GitHub's behaviour for this form has been established and this test should say so"
    )


@pytest.mark.parametrize(
    "body",
    ["This remains unresolved: #1234", "prefixes: #12345", "we disclose: #5", "self-closes: #8"],
    ids=["unresolved", "prefixes", "disclose", "hyphenated"],
)
def test_the_colon_did_not_reopen_the_substring_hole(body):
    """Adding `:?` must not cost the left boundary. A keyword inside a word is
    still not a reference, colon or no colon."""
    assert closing_issues(body) == set(), f"{body!r} names no issue, but the gate read {closing_issues(body)}"


# ---------------------------------------------------------------------------
# Mid-sentence detection counts OCCURRENCES, not issue numbers (#17580, review)
# ---------------------------------------------------------------------------
def test_an_issue_both_declared_and_disclaimed_is_still_warned_about():
    """The set-difference version cancelled this to empty and said nothing.

    A body that declares an issue closed AND says it does not close it is the
    shape most likely to be a real mistake, and it was the one silently exempt:
    `closing_issues` and the line-start matcher both contained "42", so their
    difference was empty.
    """
    body = "Closes #42\nThis does not close #42\n"
    assert mid_sentence_closings(body) == {"42"}, (
        "an issue that also appears in a deliberate declaration must still be flagged for its "
        "mid-sentence occurrence -- GitHub closes on both"
    )


def test_the_warning_reaches_the_author_for_a_both_ways_body():
    ok, message = check("Closes #42\nThis does not close #42\n")
    del ok
    assert "42" in message, f"the author was not told about the mid-sentence occurrence: {message!r}"


def test_a_body_that_only_declares_is_still_not_flagged():
    """The contrast: occurrence tracking must not start warning about clean bodies."""
    assert mid_sentence_closings("Closes #42\n- [x] Fixes #43\n") == set()
