# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Flag automation session ids and internal process roles in outward text (#19645).

Maintainer decision (2026-10-26): text in issues, pull requests and commit messages
must make sense to an outside contributor. Short-lived automation session names and
internal process roles do not; the reader cannot look either up.

One detector, three callers:

* ``scripts/check_pr_template_sections.py`` ``report()`` -- a hit FAILS the PR body
  check (CI's pr-template-check.yml and the local ``scripts/validate_pr_body.py``).
* ``.github/workflows/issue-triage.yml`` job ``wording`` -- an issue body with a hit
  gets the ``needs-wording`` label and one marker-identified comment; issues are
  flagged, never blocked (``issue`` subcommand below).
* ``scripts/lint-conventions.sh --commit-msg`` -- a hit fails the commit subject
  (``subject`` subcommand below).

Fenced code, inline code and single-line HTML comments are skipped, so text may
quote a flagged form as an example. Standard library only: the commit-msg hook and
the issue workflow run this with a bare ``python3``.

Session names are ``autobot-ai-`` plus two hex characters, but hex alone cannot tell
an all-letter id (``cb``) from a component suffix (``db``), so the bare name is
flagged only when the id holds a digit (``4d``, ``0d``, ``a0``, ``27``); an all-letter
id needs session context (``session autobot-ai-cb``). Merge-train names need their
letter suffix (``train 85l``), so ML prose such as "train 100 epochs" stays clean.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from typing import Iterator

logger = logging.getLogger(__name__)

# Single-line only, matching the `sed 's/<!--[^>]*-->//g'` the PR check started from.
COMMENT = re.compile(r"<!--[^>]*-->")
_FENCE = re.compile(r"^\s*(```|~~~)")
_INLINE_CODE = re.compile(r"`[^`]*`")

# (what it is, pattern). Bare two-character tokens are too common alone (hex SHAs,
# `a0` inside identifiers, `(10, 20)`, `db → redis`), so a session id needs a second
# signal: an attribution date `(a0, 2026-10-24` or a handoff word before an arrow.
_HANDOFF = r"(?i:handed|handoff|hand-off|handover|passed|reassigned)"
# Merge trains are numbered by series plus a letter (`85l`); match the shape, not the
# current series, so the next one is caught too. The letter is required: without it
# "train 100 epochs" and "train 32 models" are ordinary prose.
_TRAIN_NUMBER = r"\d{2,3}(?![kmb]\b)[a-z]"  # k/m/b are magnitudes: "train 10k samples"
# A session id holding a digit; component suffixes (`ui`, `db`, `api`) hold none.
_SESSION_ID_WITH_DIGIT = r"(?:\d[0-9a-f]|[0-9a-f]\d)"
RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("automation session name", re.compile(rf"\bautobot-ai-{_SESSION_ID_WITH_DIGIT}\b")),
    ("automation session name", re.compile(r"(?i:\bsession):? autobot-ai-[a-f]{2}\b")),
    ("session id in an attribution", re.compile(r"\([0-9a-z]{2},\s*20\d\d-\d\d-\d\d")),
    ("session id before an arrow", re.compile(rf"\b{_HANDOFF}(?: over)?(?: from)? [0-9a-z]{{2}} ?→")),
    ("session id after an arrow", re.compile(rf"\b{_HANDOFF}\b[^→\n]{{0,40}}→ ?[0-9a-z]{{2}}\b")),
    ("internal process role", re.compile(r"\btrainmaster\b", re.IGNORECASE)),
    ("internal merge-train name", re.compile(rf"\btrain {_TRAIN_NUMBER}\b")),
    ("internal process role", re.compile(r"\bM\d owner\b")),
)
REPLACEMENTS = (
    "maintainer decision (YYYY-MM-DD)",
    "tracked in #N",
    "the merge train (PR #N)",
    "code review on PR #N",
)
LABEL = "needs-wording"
MARKER = "<!-- outward-wording-19645 -->"


@dataclass(frozen=True)
class Hit:
    """One flagged match: which rule and the matched text.

    The surrounding line is deliberately not kept: callers print hits to CI logs and
    post them as comments, and echoing an author's raw line would replay workflow
    commands, @mentions and links (#19645 review).
    """

    rule: str
    match: str


def prose_lines(text: str) -> Iterator[tuple[str, str]]:
    """Yield ``(raw line, prose)`` outside fences; prose drops inline code and comments.

    The one stripper for outward text: the PR check's multi-close rule (#19521)
    and this detector both read through it.
    """
    fenced = False
    for line in (text or "").splitlines():
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            yield line, _INLINE_CODE.sub("", COMMENT.sub("", line))


def find_hits(text: str) -> list[Hit]:
    """Every rule match in the prose of ``text``, in line order."""
    hits = []
    for _raw, prose in prose_lines(text):
        for rule, pattern in RULES:
            hits.extend(Hit(rule, m.group(0)) for m in pattern.finditer(prose))
    return hits


def describe(hits: list[Hit]) -> list[str]:
    """One line per hit plus the replacement wording; plain text, no CI markup."""
    lines = [f'{hit.rule}: "{hit.match}"' for hit in hits]
    return lines + [replacement_hint()]


def replacement_hint() -> str:
    """The wording to use instead, quoted from the maintainer decision."""
    quoted = ", ".join(f'"{text}"' for text in REPLACEMENTS)
    return (
        "Outward text must make sense to an outside contributor: no automation session ids "
        f"and no internal process roles (maintainer decision 2026-10-26, #19645). Write {quoted} instead."
    )


def issue_comment(hits: list[Hit]) -> str:
    """The marker-identified issue comment: the matches when flagged, a note when clean."""
    if not hits:
        return f"{MARKER}\nThe wording check now passes; the `{LABEL}` label has been removed."
    rows = "\n".join(f"- {hit.rule}: `{hit.match}`" for hit in hits)
    return (
        f"{MARKER}\nThis issue body names an automation session or an internal process role:\n\n"
        f"{rows}\n\n{replacement_hint()}\n\nEdit the body and this check re-runs; the "
        f"`{LABEL}` label clears when it passes."
    )


def issue_decision(issue: dict, hits: list[Hit]) -> dict[str, str]:
    """Step outputs for one issue: whether to upsert the comment and what to do to the label.

    Clean and unlabelled posts nothing, so a clean issue never gets a comment; clean but
    still labelled updates the earlier comment to say so and removes the label.
    """
    labelled = any(label.get("name") == LABEL for label in issue.get("labels") or [])
    if hits:
        action = "keep" if labelled else "add"
    else:
        action = "remove" if labelled else "none"
    return {
        "hit": "true" if hits else "false",
        "comment": "true" if hits or labelled else "false",
        "label": action,
        "number": str(issue.get("number", "")),
        "marker": MARKER,
        "label_name": LABEL,
    }


def _issue_main(event_path: str, out_path: str) -> int:
    with open(event_path, encoding="utf-8") as handle:
        issue = json.load(handle).get("issue") or {}
    hits = find_hits(issue.get("body") or "")
    decision = issue_decision(issue, hits)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(issue_comment(hits) + "\n")
    for line in describe(hits) if hits else ["issue body wording: clean"]:
        logger.info("%s", line)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.writelines(f"{key}={value}\n" for key, value in decision.items())
    return 0


def _subject_main(subject: str) -> int:
    hits = find_hits(subject)
    if not hits:
        return 0
    for line in describe(hits):
        logger.info("  FAIL  %s", line)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    subject = sub.add_parser("subject", help="check one commit subject; exit 1 on a hit")
    subject.add_argument("text")
    issue = sub.add_parser("issue", help="decide label/comment for an issues event")
    issue.add_argument("--event", required=True)
    issue.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    if args.command == "subject":
        return _subject_main(args.text)
    return _issue_main(args.event, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
