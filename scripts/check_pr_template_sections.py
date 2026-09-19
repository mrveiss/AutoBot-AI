# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Check that the required PR template sections are present and filled in (#6474).

Split out of the inline ``awk`` in ``.github/workflows/pr-template-check.yml`` by
#16793, because that version could not tell its two failure states apart.

``awk "/^## ${header}/{found=1; next} found && /^## /{exit} found{print}"``
extracts nothing when the heading is absent and nothing when the heading is
there with no prose beneath it. One message covered both:

    ::error::Required section 'Thinking Path' is empty. Please fill it in.

The second state is accurate. The first is not, and it is the common one:
``gh pr create --body`` and ``--body-file`` never load
``.github/PULL_REQUEST_TEMPLATE.md``, so any PR opened non-interactively starts
from whatever headings its author chose -- and GitHub's conventional
``## Summary`` / ``## Test plan`` produce four "empty section" errors on a body
that is entirely filled in. Observed on #16778, #16790 and #16791 in one
afternoon; each author went looking for an empty section, found a complete body,
and had to be told the real cause by somebody else. The fix each time was a
rename with identical content.

What is *required* is unchanged -- this is about the diagnosis. The extraction
below mirrors the awk one line at a time so that stays true: the same prefix
match on the opening heading, the same ``^## `` terminator (a ``###``
subheading does not end a section), the same single-line comment stripping, the
same "blank lines are not content".
"""

from __future__ import annotations

import logging
import os
import re
import sys

# The set the template publishes. Named here and quoted verbatim in the failure
# output, so an author who used different headings is told which four to use
# rather than being sent to guess (#16793).
REQUIRED_SECTIONS = ("Thinking Path", "What Changed", "Verification", "Model Used")
TEMPLATE_PATH = ".github/PULL_REQUEST_TEMPLATE.md"

# `^## ` -- with the space, as the awk had it. `##Foo` is not a heading and
# `### Foo` does not close the section it sits inside.
_HEADING = re.compile(r"^## (.*)$")
# Single-line only, matching `sed 's/<!--[^>]*-->//g'`. A comment spanning lines
# was never stripped and still is not; widening that would change what passes.
_COMMENT = re.compile(r"<!--[^>]*-->")

# Plain stdlib logging, deliberately (#1082): this runs as a bare script in CI,
# where autobot_shared.logging_manager would pull in config this job does not
# have. stdout rather than the sibling gate's stderr because these lines carry
# `::error::` workflow commands, which is the stream GitHub documents for them.
logger = logging.getLogger(__name__)


def headings(body: str) -> list[str]:
    """Every `## ` heading in ``body``, verbatim and in order."""
    found = []
    for line in (body or "").splitlines():
        match = _HEADING.match(line)
        if match is not None:
            found.append(match.group(1).strip())
    return found


def _section_lines(body: str, heading: str) -> list[str] | None:
    """Raw lines under ``## <heading>``, or None when that heading is absent.

    None and ``[]`` are the two states this gate exists to tell apart, so the
    absent case must not collapse into the empty one anywhere above here.
    """
    start = re.compile(rf"^## {re.escape(heading)}")
    collected: list[str] | None = None
    for line in (body or "").splitlines():
        if collected is None:
            if start.match(line):
                collected = []
            continue
        if _HEADING.match(line):
            break
        collected.append(line)
    return collected


def section_content(body: str, heading: str) -> str | None:
    """Prose under ``## <heading>``: None if missing, "" if present but empty."""
    lines = _section_lines(body, heading)
    if lines is None:
        return None
    stripped = (_COMMENT.sub("", line) for line in lines)
    return "\n".join(line for line in stripped if line.strip())


def _missing_report(missing: list[str], found: list[str]) -> list[str]:
    """Say the headings are absent, and name what the body has instead (#16793).

    An author whose body is complete under different headings needs the
    difference, not the verdict -- the old message sent them to search a full
    body for a blank section that did not exist.
    """
    required = ", ".join(f"## {name}" for name in REQUIRED_SECTIONS)
    if found:
        observed = "This body's own headings are: " + ", ".join(f"## {name}" for name in found) + "."
    else:
        observed = "This body has no `## ` headings at all."
    return [
        "::error::Required section(s) absent from the PR body -- missing, not empty: "
        + ", ".join(f"## {name}" for name in missing)
        + ".",
        observed,
        f"The four required headings are exactly: {required} -- see {TEMPLATE_PATH}, "
        "which is the source of truth for the set.",
        "`gh pr create --body` and `--body-file` do not load that template, so a PR opened "
        "non-interactively starts from whatever headings its author chose. Rename yours to "
        "the four above; the content underneath carries over unchanged.",
    ]


def report(body: str) -> tuple[bool, list[str]]:
    """Return (ok, output lines) for one pull request body.

    **Imported by ``scripts/validate_pr_body.py`` (#16859)**, which runs this
    gate locally before ``gh pr create`` so an author learns the requirement
    before the push rather than from a red check ~63 checks in. Changing this
    name or its ``(ok, lines)`` return shape breaks that caller.

    You will not find out locally: ``tools/git-hooks/pre-push`` selects the
    sibling test of each changed file (``<file>_test.py``), so editing this
    module runs ``check_pr_template_sections_test.py`` and never
    ``validate_pr_body_test.py``. CI catches it, after the push.
    """
    missing: list[str] = []
    empty: list[str] = []
    lines: list[str] = []

    for section in REQUIRED_SECTIONS:
        content = section_content(body, section)
        if content is None:
            missing.append(section)
        elif not content:
            empty.append(section)
        else:
            lines.append(f"::notice::Section '{section}': OK")

    for section in empty:
        # Verbatim the message this gate has always printed. #16793 is about the
        # OTHER state borrowing it; where it was already accurate it stays put,
        # and it is now accurate every time it appears.
        lines.append(f"::error::Required section '{section}' is empty. Please fill it in before merging.")
    if missing:
        lines.extend(_missing_report(missing, headings(body)))

    if not missing and not empty:
        return True, lines + ["All required PR template sections are filled in."]
    return False, lines + [_summary(missing, empty)]


def _summary(missing: list[str], empty: list[str]) -> str:
    """One closing line that keeps the two counts apart (#16793)."""
    parts = []
    if missing:
        parts.append(f"{len(missing)} absent")
    if empty:
        parts.append(f"{len(empty)} present but empty")
    return f"::error::PR template check failed: {' and '.join(parts)} required section(s)."


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    ok, lines = report(os.environ.get("PR_BODY", ""))
    for line in lines:
        logger.info("%s", line)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
