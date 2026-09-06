# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The trailer check must reject trailers and ignore prose that names them (#15848).

`no-commit-trailers.yml` bans agent/tooling trailers. Two of its three arms were
deliberately unanchored, on the reasoning that their tokens are implausible in
prose. That reasoning did not survive contact: a commit message DOCUMENTING the
policy has to quote the strings it bans, and was rejected by the check it
describes. Three separate writes about the hazard were refused in one session,
one of them a commit explaining the fix.

Anchoring costs nothing, because a trailer is a line-position construct --
git's own ``interpret-trailers`` reads only the final block, and every tool that
emits these writes them at line start. ``^[[:space:]]*`` keeps an indented
trailer caught.

The pair below is the point. Asserting only that real trailers are rejected
would pass with the pattern matching every line in the body, which is the defect
this closes; asserting only that prose passes would pass with the check disabled.
Both directions, or neither means anything.
"""

from __future__ import annotations

import re
# Fixed argv, no user input.
import subprocess  # nosec B404
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "no-commit-trailers.yml"

#: Trailers a tool emits. Every one must be rejected.
REJECTED = [
    "Generated with [Claude Code](https://claude.com/claude-code)",
    "   Generated with [Claude Code]",
    "Co-authored-by: someone <noreply@paperclip.com>",
    "  Co-authored-by: someone <noreply@paperclip.com>",
    "Claude-Session: https://example.invalid/session",
]

#: Prose that NAMES a banned trailer. Every one must pass -- documenting a rule
#: must not be punished by the rule.
ALLOWED = [
    "we reject the Generated with [Claude promo trailer on every commit",
    "the noreply@paperclip address is banned in trailers, not in prose",
    "a Claude-Session: line would leak a session URL into public history",
    "see .github/workflows/no-commit-trailers.yml for why these are refused",
]


def _agent_re() -> str:
    """The live pattern, read from the workflow rather than duplicated here.

    A copy would drift and this test would then assert about a pattern nobody
    runs -- the failure mode the whole file is about.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"^\s*agent_re='([^']+)'", text, re.MULTILINE)
    assert match, "agent_re not found in the workflow -- this test cannot see what it checks"
    return match.group(1)


def _matches(pattern: str, line: str) -> bool:
    """Ask grep, not Python: the workflow runs `grep -qE`, and the dialects differ."""
    return (
        # Fixed argv; inputs are module constants.
        subprocess.run(  # nosec B603 B607
            ["grep", "-qE", pattern],
            input=line,
            text=True,
            check=False,
        ).returncode
        == 0
    )


@pytest.mark.parametrize("line", REJECTED)
def test_a_real_trailer_is_rejected(line: str) -> None:
    assert _matches(_agent_re(), line), f"a tool-emitted trailer slipped through: {line!r}"


@pytest.mark.parametrize("line", ALLOWED)
def test_prose_naming_a_trailer_is_not_rejected(line: str) -> None:
    assert not _matches(_agent_re(), line), (
        f"prose describing the policy was rejected by it: {line!r} -- "
        "the check cannot tell a mention from a trailer (#15848)"
    )


def test_every_arm_is_anchored() -> None:
    """Pins the rule itself, because the pair above cannot.

    A future arm added without an anchor would be caught by the ALLOWED cases
    only if someone happened to write prose containing its token. This asserts
    the property directly at the one place it is expressed.
    """
    pattern = _agent_re()
    assert pattern.startswith("^"), f"agent_re is not anchored at a line start: {pattern!r}"
    # The hazard is an arm that BEGINS with `.*`, which re-defeats the anchor it
    # sits behind by matching anything before its token. A `.*` after a trailer
    # key (`[A-Za-z-]+:.*token`) is fine and is how the paperclip arm is written.
    arms = pattern.lstrip("^").lstrip("[[:space:]]*").strip("()").split("|")
    offenders = [a for a in arms if a.startswith(".*")]
    assert not offenders, (
        f"these arms begin with `.*`, re-defeating the anchor: {offenders} -- "
        "a trailer is `Key: value`, so require the key before the token"
    )
