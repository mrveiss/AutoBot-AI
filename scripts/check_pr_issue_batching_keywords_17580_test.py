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


def _workflow_keywords() -> set[str]:
    """The closing keywords in the sibling gate's grep alternation."""
    line = next(ln for ln in _WORKFLOW.read_text(encoding="utf-8").splitlines() if "grep -iqE" in ln)
    alternation = re.search(r'grep -iqE "\(([^)]+)\)', line)
    assert alternation, f"could not find the alternation in: {line.strip()!r}"
    return {w for w in alternation.group(1).split("|") if w not in {"refs", "references", "part of"}}


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
    assert _workflow_keywords() == _checker_keywords(), (
        "the two gates disagree about what a closing keyword is — "
        f"workflow-only: {sorted(_workflow_keywords() - _checker_keywords())}, "
        f"checker-only: {sorted(_checker_keywords() - _workflow_keywords())}"
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
    ["Closes #123", "- Closes #123", "> Closes #123", "**Closes #123**", "  Fixes #123"],
    ids=["plain", "bullet", "quote", "bold", "indented"],
)
def test_a_deliberate_declaration_is_not_flagged(line):
    """Every markdown lead-in an author actually uses for a real closing line."""
    assert mid_sentence_closings(line) == set()


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
