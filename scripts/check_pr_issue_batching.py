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

# Mirrors pr-issue-validation.yml:86 -- keep the two in step. One difference,
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

# Plain stdlib logging, deliberately (#1082): this runs as a bare script in CI,
# where autobot_shared.logging_manager would pull in config this job does not have.
logger = logging.getLogger(__name__)

RATIONALE_HINT = (
    "This PR references exactly one issue. Batch same-scope issues into one PR "
    "(one CI suite per batch, not per issue), or state why this one stands alone "
    "by adding a line to the PR body:\n\n"
    "    Single-issue rationale: <why this cannot ride with another issue>"
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


def single_issue_rationale(body: str) -> str | None:
    """The non-empty rationale line, or None when absent or blank."""
    match = _RATIONALE.search(body or "")
    if match is None:
        return None
    return match.group(1).strip() or None


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
    return False, RATIONALE_HINT


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
