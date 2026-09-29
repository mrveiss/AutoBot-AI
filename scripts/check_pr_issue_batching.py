# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Enforce the same-scope batching rule on pull request bodies (#15492).

``CLAUDE.md`` states it plainly -- *batch same-scope issues into one PR by
default, one CI suite per batch, not per issue* -- and nothing checked it, so
the rule held exactly as often as it was remembered. Each miss costs a full
CI suite.

This is deliberately **not** a ban on single-issue PRs. A dependency bump
carries one advisory, a revert reverts one thing, a hotfix is narrow on
purpose, and genuinely independent changes should stay apart. The defect being
fixed is that a single-issue PR required no thought at all; the author now has
to say why in one line, which is the smallest change that makes the decision
deliberate.

The keyword set is the one ``.github/workflows/pr-issue-validation.yml`` already
uses to decide what counts as an issue reference, so the two gates cannot
disagree about what a reference is. #16795 split it in two for *this* gate's own
question: a reference is any of them, but only a closing keyword is a delivered
issue, and "batched" is a claim about delivery.

#17128: batching moved from a per-PR-authorship rule to a per-landing one. A
``vehicle-*`` branch now carries several already-approved member PRs into one
CI run and closes/refs them as carried, so a member PR is single-issue *by
design* -- the same-issue rule this gate enforces on how a PR is authored no
longer matches how batching actually happens, and it was failing almost every
PR. A vehicle (by branch name or by its member table) passes outright. Every
other single-issue or closes-nothing PR still gets the same guidance it always
did, but now as a ``::warning::`` annotation rather than a failing exit code --
a nudge, not a block.
"""

from __future__ import annotations

import logging
import os
import re
import sys

# Mirrors the issue-linkage regex in pr-issue-validation.yml -- keep the two in
# step. Deliberately no line number: the previous citation pinned one, the regex
# moved, and the anchor rotted while the mechanism did not. One difference,
# and it is the whole point of this gate: the sibling only needs to know whether
# ANY issue is linked, so it stops at the first number. The repo writes batches
# as `Closes #A, #B`, where only #A follows the keyword -- counting the sibling's
# way would score every batched PR as single-issue and fail exactly the PRs this
# rule exists to reward. So a keyword here consumes the whole comma/and-separated
# run that follows it.
_ONE_REF = r"(?:#?\d+|MVA-\d+)"
# `, and` (Oxford) must read as ONE separator, not a comma followed by a non-ref.
_SEP_RE = r"\s*(?:,\s*(?:and\s+)?|and\s+)"
# #16795: the two keyword classes do NOT mean the same thing to this gate.
# `Closes #A` says the PR delivers #A; `Refs #B` says #B is context -- usually
# the umbrella, which issue decomposition tells every child PR to link. Counting
# them together made the common, correct shape (`Closes #A` + `Refs #umbrella`)
# score as two issues and exempt itself from the rule this gate exists to
# enforce. #16781, #16783 and #16788 each passed that way, none with a rationale,
# and each was reported as "Batched" -- a guard that cannot tell *satisfied* from
# *not examined* is worse than an absent one, because the green is read as a
# judgement. The wider set still answers "is anything linked at all", which is
# the only question the sibling gate owns.
#
# #17580: both gates knew three of GitHub's nine closing keywords, and the two
# agreeing with each other is what hid it -- the invariant they were written to
# protect ("the two gates cannot disagree about what a reference is") held while
# both diverged from the platform that does the closing. `Fix #N` read here as no
# reference at all while GitHub closed the issue on merge, and `Fix #A`/`Fix #B`
# scored as closing nothing, so a batch was never asked for its rationale. Four
# merged PRs closed an issue with a body that said "does not close #N" -- GitHub
# does not parse negation, and neither gate saw a closing keyword to argue with.
#
# Longest alternative first per verb, as a CONVENTION rather than a requirement.
# I wrote it believing `close` ahead of `closes` would match the stem, leave the
# `s` and fail `\s+`; the mutation test says otherwise -- alphabetical order still
# recognises all nine, because Python's `re` backtracks into the other
# alternatives and POSIX ERE (the sibling gate's `grep -E`) is leftmost-longest.
# The order is kept for readability and to stay diffable against the workflow's
# copy, and `test_the_longest_inflection_comes_first_in_each_verb` pins the
# convention, not a behaviour. Recorded because the trap is real in engines that
# are leftmost-first without backtracking, and a future port would meet it.
_CLOSING_WORDS = "closes|closed|close|fixes|fixed|fix|resolves|resolved|resolve"
_MENTION_WORDS = "refs|references|part of"
_RUN = rf"({_ONE_REF}(?:{_SEP_RE}{_ONE_REF})*)"
# The left boundary is load-bearing, and widening the verb set is what made it
# load-bearing here: with bare stems in the alternation, `unresolved #1234`
# matches `resolved #1234`, `prefixes #12` matches `fixes #12`, and `discloses
# #5` matches `closes #5`. Every one of those reads as a reference the author
# never wrote, and all three errors point the same way -- the link gate is
# SATISFIED and the batching count is INFLATED -- so the guard reports
# compliance for a body that claims the opposite. `.github/workflows/
# pr-issue-validation.yml` already carried this guard on its fork-override
# alternation, with a comment saying why; the widened patterns did not inherit
# it. A lookbehind rather than a consumed character, so two references can sit
# adjacent and the group numbering of `_RUN` is untouched.
# GitHub accepts a colon after the keyword. Its own documentation: "The keywords
# can be followed by colons or in uppercase. For example: `Closes: #10`,
# `CLOSES #10`, or `CLOSES: #10`." Both gates required whitespace IMMEDIATELY
# after the keyword, so `Fixes: #123` closed the issue on merge while the link
# gate rejected the PR for having no linkage and the batching count omitted it
# (#17580, review). Same divergence this file exists to remove, in the other
# direction from the missing-inflections one: there the gate saw no reference
# where GitHub saw one, here it sees none where GitHub closes.
_COLON = r":?"
_LEFT_EDGE = r"(?<![A-Za-z0-9_-])"
_CLOSING = re.compile(rf"{_LEFT_EDGE}(?:{_CLOSING_WORDS}){_COLON}\s+{_RUN}", re.IGNORECASE)
_REFERENCE = re.compile(rf"{_LEFT_EDGE}(?:{_CLOSING_WORDS}|{_MENTION_WORDS}){_COLON}\s+{_RUN}", re.IGNORECASE)
_SPLIT = re.compile(_SEP_RE, re.IGNORECASE)
# #17580 AC3: a closing keyword at the START of a line is a deliberate
# declaration; the same keyword inside a sentence is usually prose. GitHub does
# not care about the difference and closes on both, which is how #16464 was
# closed by a body whose sentence read "this PR does not close #16464". The
# negation blindness is the platform's and cannot be fixed here, so the only
# defence is telling the author before the merge. Markdown lead-ins are allowed
# because `- Closes #1`, `> Closes #1` and `**Closes #1**` are all deliberate.
# A numbered list and a task-list checkbox are line-start declarations too, and
# the original lead-in class excluded both: digits, `.`, `)`, `[` and `]` are
# not in it, so `1. Closes #123` and `- [x] Closes #123` were reported as
# mid-sentence prose. Both are idiomatic in a PR body -- the second is how this
# repository's own template asks for them -- so the warning fired on exactly the
# authors who had done it right.
_MARKDOWN_LEAD = r"[\s>*_#\-]*"
_LIST_LEAD = rf"(?:(?:\d+[.)]|\[[ xX]\]){_MARKDOWN_LEAD})*"
_LINE_START_CLOSING = re.compile(
    rf"^{_MARKDOWN_LEAD}{_LIST_LEAD}(?:{_CLOSING_WORDS}){_COLON}\s+{_RUN}", re.IGNORECASE | re.MULTILINE
)
# A reference inside a fenced block or inline code is an EXAMPLE, not a link.
# Found on this gate's own PR, whose worked examples scored as six extra issues:
# left in, a PR could satisfy the rule with sample text and never link anything.
_FENCE = re.compile(r"```.*?```|~~~.*?~~~|`[^`\n]*`", re.DOTALL)
_RATIONALE = re.compile(r"^\s*Single-issue rationale:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
# #16050: the same rationale written as a markdown HEADING, with the reason in
# the prose that follows. Two independent sessions wrote it this way within four
# hours -- #16018 and #16049, the latter the CRITICAL auth fix -- because it
# matches the section style the rest of the PR body already uses (`## Thinking
# Path`, `## What Changed`, `## Verification`). Two authors independently
# choosing a form the checker rejects is the checker's defect, and the rejected
# form is the more readable one.
#
# The hint below printed the inline form INDENTED, as an example, which reads as
# illustration rather than as an exact-match requirement -- so the gate taught
# the shape it refused.
_RATIONALE_HEADING = re.compile(
    r"^[ \t]*#{1,6}[ \t]*Single-issue rationale[ \t]*:?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)

# Plain stdlib logging, deliberately (#1082): this runs as a bare script in CI,
# where autobot_shared.logging_manager would pull in config this job does not have.
logger = logging.getLogger(__name__)

_RATIONALE_FORMS = (
    "    Single-issue rationale: <why this cannot ride with another issue>\n\n"
    "or as a section, with the reason in the prose beneath it:\n\n"
    "    ## Single-issue rationale\n\n    <why this cannot ride with another issue>"
)

RATIONALE_HINT = (
    "This PR delivers exactly one issue. Batch same-scope issues into one PR "
    "(one CI suite per batch, not per issue), or state why this one stands alone "
    "by adding a line to the PR body:\n\n" + _RATIONALE_FORMS
)


def _closes_nothing_hint(referenced: set[str]) -> str:
    """The failure for a PR that closes nothing (#16855).

    ``RATIONALE_HINT`` opens "This PR delivers exactly one issue", which is a
    count of one where the count is zero. Printed with ``_mention_note`` it said
    both at once -- one issue delivered, and the only issue named not a delivered
    one -- leaving the true number stated nowhere. ``_scope`` has carried the
    right words for this state since #16795, but only the passing path reached
    them.

    Whether such a PR should need a rationale at all is open on #16855 and
    deliberately not settled here: this changes the wording, not the verdict.
    """
    return (
        f"This PR closes no issue -- it links {_render(referenced)} with a "
        "non-closing keyword (refs/references/part of). Only resolves/closes/fixes "
        "count toward batching, so there is nothing here to batch with. A "
        "rationale line is still required while the rule stands; add one to the "
        "PR body:\n\n" + _RATIONALE_FORMS
    )


def _issues_under(body: str, pattern: "re.Pattern[str]") -> set[str]:
    """Distinct issue identifiers ``pattern`` links in ``body``."""
    found = set()
    for run in pattern.findall(_FENCE.sub(" ", body or "")):
        for ref in _SPLIT.split(run):
            ref = ref.strip().lstrip("#")
            if ref:
                found.add(ref.upper() if ref.upper().startswith("MVA-") else ref)
    return found


def referenced_issues(body: str) -> set[str]:
    """Distinct issue identifiers referenced by ``body``, under any keyword."""
    return _issues_under(body, _REFERENCE)


def closing_issues(body: str) -> set[str]:
    """Distinct issues ``body`` says this PR DELIVERS (#16795).

    A subset of :func:`referenced_issues`, and the difference is the whole gate:
    a mention links context, only a closing keyword makes a PR batched.
    """
    return _issues_under(body, _CLOSING)


def mid_sentence_closings(body: str) -> set[str]:
    """Issues closed by a keyword that is NOT at the start of its line (#17580).

    These are the dangerous ones. An author writing "this PR does not close #N"
    has said the opposite of what GitHub will do, and the gate that agreed with
    the author's intent is exactly what let #16464 close on merge while the check
    reported "closes nothing". Returned so the author can be warned; the set is
    deliberately not subtracted from :func:`closing_issues`, because GitHub does
    close them and the batching count must reflect the platform.
    """
    text = _FENCE.sub(" ", body or "")
    # Occurrences, not sets (review). This was
    # `closing_issues(body) - _issues_under(body, _LINE_START_CLOSING)`, so a body
    # containing BOTH "Closes #42" and "this does not close #42" cancelled to the
    # empty set and the author was never warned -- the one shape most likely to be
    # a real mistake, silently exempt because the same number also appeared in a
    # deliberate declaration.
    #
    # Both patterns capture the reference run as group 1, so `start(1)` is the same
    # offset for the same occurrence under either. An occurrence whose run is not
    # at a declared line start is mid-sentence, whatever else the body says about
    # that issue.
    declared_at = {match.start(1) for match in _LINE_START_CLOSING.finditer(text)}
    risky: set[str] = set()
    for match in _CLOSING.finditer(text):
        if match.start(1) in declared_at:
            continue
        for ref in _SPLIT.split(match.group(1)):
            ref = ref.strip().lstrip("#")
            if ref:
                risky.add(ref.upper() if ref.upper().startswith("MVA-") else ref)
    return risky


# #16104: an ATX heading is 1-6 `#` followed by a space, a tab, or end of line.
# `#15961` is an ISSUE REFERENCE. Treating any leading `#` as a heading made a
# section that WAS filled in read as empty -- and opening the rationale with the
# issue it is about is the natural way to write it, so the gate rejected the
# form it teaches. The hint then said "add a section" to an author who had added
# one, whose only available fix was to reword until green. A reword leaves no
# trace, which is why this survived #16050 and recurred.
_ATX_HEADING = re.compile(r"^#{1,6}(?:[ \t]|$)")


def _heading_rationale(body: str) -> tuple[bool, str | None, str | None]:
    """(heading found, the prose beneath it, the line that ended the section).

    Scans forward past blank lines to the first non-empty line, so a reason two
    paragraphs down still counts. Stops at the next heading: an empty section
    must NOT borrow the next section's text as its rationale -- that is how a
    heading-only body would pass a check about whether a human justified
    something.
    """
    match = _RATIONALE_HEADING.search(body or "")
    if match is None:
        return False, None, None
    for line in body[match.end() :].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _ATX_HEADING.match(stripped):
            return True, None, stripped
        return True, stripped, None
    return True, None, None


def _rationale_under_heading(body: str) -> str | None:
    """Prose following a `## Single-issue rationale` heading, or None (#16050)."""
    return _heading_rationale(body)[1]


def _mention_note(closing: set[str], referenced: set[str]) -> str:
    """Why a `Refs #umbrella` link did not make this PR batched (#16795).

    Without it the author reads "delivers exactly one issue" on a body that
    visibly names two, and the only available fix is to guess. The gate changed
    under them, so it owes them the reason rather than the verdict alone.
    """
    mentioned = referenced - closing
    if not mentioned:
        return ""
    verb = "is" if len(mentioned) == 1 else "are"
    return (
        f"\n\n{_render(mentioned)} {verb} linked with a non-closing keyword "
        "(refs/references/part of), which is context -- an umbrella, a follow-up, a "
        "dependency -- not a second delivered issue. Only resolves/closes/fixes count "
        "toward batching."
    )


def _rationale_failure(body: str, closing: set[str], referenced: set[str]) -> str:
    """The hint, naming WHICH of the two failures happened (#16104).

    "No section found" and "section found but empty" want opposite fixes, and a
    gate that reports the first when it means the second sends the author to add
    something already present. A red only self-corrects when it names its real
    cause.
    """
    found, _, terminator = _heading_rationale(body)
    if not found:
        if not closing:
            return _closes_nothing_hint(referenced)
        return RATIONALE_HINT + _mention_note(closing, referenced)
    if terminator is not None:
        return (
            "The `## Single-issue rationale` section is present but reads as empty. "
            f"The first line under it is `{terminator}`, which parsed as the next "
            "heading, so the section ended before any prose was found. Put the "
            "reason on a line that does not begin with a `#` followed by a space."
        )
    return (
        "The `## Single-issue rationale` section is present but has no prose "
        "beneath it. Add the reason under the heading."
    )


def single_issue_rationale(body: str) -> str | None:
    """The non-empty rationale, inline or under a heading, or None (#16050).

    Both forms require actual prose. Widening WHERE the reason may sit must not
    widen whether one is needed: this gate asks whether a human justified
    standing alone, so a heading with nothing under it has to fail exactly as
    `Single-issue rationale:` with nothing after the colon already does.
    """
    match = _RATIONALE.search(body or "")
    if match is not None and match.group(1).strip():
        return match.group(1).strip()
    return _rationale_under_heading(body)


def exemption(actor: str, branch: str, title: str) -> str | None:
    """Why this PR is outside the rule, or None if the rule applies."""
    if actor.strip().lower() == "dependabot[bot]":
        return "authored by dependabot"
    if branch.strip().startswith("hotfix-"):
        return "hotfix branch"
    if title.strip().lower().startswith("revert"):
        return "revert"
    return None


_VEHICLE_BRANCH_PREFIX = "vehicle-"


def is_vehicle(branch: str, body: str) -> bool:
    """True when *branch* or *body* mark this as a batching vehicle (#17128).

    A vehicle lands several already-approved member PRs in one branch and
    closes/refs them as carried, so the per-PR single-issue rule does not
    apply to how it was AUTHORED. The branch-name convention is the primary
    signal; the member-table check covers a vehicle rebuilt on a
    differently-named branch. A table header needs a "head" column (the merged
    SHA) plus a "member" or "pr" column -- the two shapes real vehicles use
    (``Member | Head | Delivers`` and ``PR | Head | Closes | Title``).
    """
    if branch.strip().lower().startswith(_VEHICLE_BRANCH_PREFIX):
        return True
    for line in (body or "").splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = {cell.strip().lower() for cell in stripped.strip("|").split("|")}
        if "head" in cells and ("member" in cells or "pr" in cells):
            return True
    return False


def _vehicle_notice(closing: set[str], referenced: set[str]) -> str:
    """One-line pass notice for a vehicle PR, naming what it carries (#17128)."""
    mentioned = referenced - closing
    closes = f"closes {len(closing)} issue(s)" + (f" ({_render(closing)})" if closing else "")
    refs = f"refs {len(mentioned)} issue(s)" + (f" ({_render(mentioned)})" if mentioned else "")
    return f"Vehicle PR: {closes}, {refs}."


def warning_annotation(text: str) -> str:
    """Wrap *text* as a single-line GitHub ``::warning::`` workflow command.

    ``%0A`` keeps a multi-line hint on one line -- the same encoding
    ``pipeline-scripts/ci_dispatch_watchdog.py`` already uses for ``::error::``.
    """
    return "::warning::" + text.replace("\n", "%0A")


def _mid_sentence_warning(body: str) -> str:
    """The #17580 AC3 notice, or "" when no closing keyword sits mid-sentence.

    Prepended to every verdict rather than returned from one branch: GitHub closes
    on these regardless of whether the PR is batched, excused or a vehicle, so the
    warning cannot be gated on this gate's own policy.
    """
    risky = mid_sentence_closings(body)
    if not risky:
        return ""
    return (
        warning_annotation(
            f"A closing keyword for {_render(risky)} appears mid-sentence. GitHub closes on it and "
            "does not read negation -- #16464 was closed by a body saying it did not close it. "
            "Move the keyword to the start of its own line if you mean it, or reword to 'Refs' if "
            "you do not."
        )
        + "\n"
    )


def check(body: str, actor: str = "", branch: str = "", title: str = "") -> tuple[bool, str]:
    """Return (ok, message) for one pull request.

    **Imported by ``scripts/validate_pr_body.py`` (#16859)**, which runs this
    gate locally before ``gh pr create`` so an author learns the requirement
    before the push rather than from a red check ~63 checks in. Changing this
    name, its keyword parameters or its ``(ok, message)`` return shape breaks
    that caller — it passes ``actor``/``branch``/``title`` by keyword.

    You will not find out locally: ``tools/git-hooks/pre-push`` selects the
    sibling test of each changed file (``<file>_test.py``), so editing this
    module runs ``check_pr_issue_batching_test.py`` and never
    ``validate_pr_body_test.py``. CI catches it, after the push.

    #17128: a single-issue or closes-nothing PR no longer fails -- it returns
    ``True`` with a ``::warning::`` annotation carrying the same guidance this
    gate always printed. A vehicle (see :func:`is_vehicle`) short-circuits
    everything else and passes outright, however many issues it closes or refs.
    """
    ok, message = _verdict(body, actor=actor, branch=branch, title=title)
    return ok, _mid_sentence_warning(body) + message


def _verdict(body: str, actor: str = "", branch: str = "", title: str = "") -> tuple[bool, str]:
    """The batching verdict itself, unchanged by #17580."""
    if is_vehicle(branch, body):
        return True, _vehicle_notice(closing_issues(body), referenced_issues(body))

    excused = exemption(actor, branch, title)
    if excused is not None:
        return True, f"Batching rule does not apply ({excused})."

    closing = closing_issues(body)
    if len(closing) >= 2:
        return True, f"Batched: closes {len(closing)} issues ({_render(closing)})."

    referenced = referenced_issues(body)
    if not referenced:
        # The PR-issue-link gate owns this case; do not fail twice for one defect.
        return True, "No issue reference found; pr-issue-validation owns that check."

    rationale = single_issue_rationale(body)
    if rationale:
        return True, f"{_scope(closing, referenced)}, rationale given: {rationale}"
    return True, warning_annotation(_rationale_failure(body, closing, referenced))


def _scope(closing: set[str], referenced: set[str]) -> str:
    """How this PR is linked, for the passing message (#16795).

    Used to read "Single issue (#A, #umbrella)" -- printed from the reference
    count, so it named the umbrella as something the PR delivered. The message a
    reviewer trusts has to be true about which of the two it is.
    """
    if not closing:
        return f"Closes nothing; references {_render(referenced)}"
    return f"Single issue (closes {_render(closing)})"


def _render(issues: set[str]) -> str:
    numeric = sorted(i for i in issues if i.isdigit())
    other = sorted(i for i in issues if not i.isdigit())
    return ", ".join([f"#{i}" for i in numeric] + other)


def main() -> int:
    # stdout, not stderr: #17128 added a `::warning::` workflow command to the
    # passing path, and stdout is the stream GitHub documents for those --
    # same reasoning as check_pr_template_sections.py's main().
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    ok, message = check(
        os.environ.get("PR_BODY", ""),
        os.environ.get("PR_ACTOR", ""),
        os.environ.get("PR_BRANCH", ""),
        os.environ.get("PR_TITLE", ""),
    )
    if ok:
        logger.info("%s", message)
        return 0
    logger.error("%s", message)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
