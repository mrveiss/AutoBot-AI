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
disagree about what a reference is.
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
_REFERENCE = re.compile(
    r"(?:resolves|closes|fixes|refs|references|part of)\s+"
    rf"({_ONE_REF}(?:{_SEP_RE}{_ONE_REF})*)",
    re.IGNORECASE,
)
_SPLIT = re.compile(_SEP_RE, re.IGNORECASE)
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

RATIONALE_HINT = (
    "This PR references exactly one issue. Batch same-scope issues into one PR "
    "(one CI suite per batch, not per issue), or state why this one stands alone "
    "by adding a line to the PR body:\n\n"
    "    Single-issue rationale: <why this cannot ride with another issue>\n\n"
    "or as a section, with the reason in the prose beneath it:\n\n"
    "    ## Single-issue rationale\n\n    <why this cannot ride with another issue>"
)


def referenced_issues(body: str) -> set[str]:
    """Distinct issue identifiers referenced by ``body``."""
    found = set()
    for run in _REFERENCE.findall(_FENCE.sub(" ", body or "")):
        for ref in _SPLIT.split(run):
            ref = ref.strip().lstrip("#")
            if ref:
                found.add(ref.upper() if ref.upper().startswith("MVA-") else ref)
    return found


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


def _rationale_failure(body: str) -> str:
    """The hint, naming WHICH of the two failures happened (#16104).

    "No section found" and "section found but empty" want opposite fixes, and a
    gate that reports the first when it means the second sends the author to add
    something already present. A red only self-corrects when it names its real
    cause.
    """
    found, _, terminator = _heading_rationale(body)
    if not found:
        return RATIONALE_HINT
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


def check(body: str, actor: str = "", branch: str = "", title: str = "") -> tuple[bool, str]:
    """Return (ok, message) for one pull request."""
    excused = exemption(actor, branch, title)
    if excused is not None:
        return True, f"Batching rule does not apply ({excused})."

    issues = referenced_issues(body)
    if len(issues) >= 2:
        return True, f"Batched: references {len(issues)} issues ({_render(issues)})."
    if not issues:
        # The PR-issue-link gate owns this case; do not fail twice for one defect.
        return True, "No issue reference found; pr-issue-validation owns that check."

    rationale = single_issue_rationale(body)
    if rationale:
        return True, f"Single issue ({_render(issues)}), rationale given: {rationale}"
    return False, _rationale_failure(body)


def _render(issues: set[str]) -> str:
    numeric = sorted(i for i in issues if i.isdigit())
    other = sorted(i for i in issues if not i.isdigit())
    return ", ".join([f"#{i}" for i in numeric] + other)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
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
