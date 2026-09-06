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
    "X-Co-Author2: someone <noreply@paperclip.com>",
    "GENERATED WITH [CLAUDE CODE]",
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


def _grep_flags() -> str:
    """The flags the workflow actually greps with, read from the workflow.

    Hardcoding ``-qE`` here ran the live pattern under conditions production
    does not use: the workflow greps **case-insensitively** (``grep -iqE``). A
    test that reads the pattern from the source of truth and then applies it
    differently is asserting about something nobody runs -- the same defect
    class this file exists to close, one level up.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"grep\s+(-[a-zA-Z]+)\s+\"\$\{agent_re\}\"", text)
    assert match, "could not find the workflow's grep invocation for agent_re"
    return match.group(1)


def _matches(pattern: str, line: str) -> bool:
    """Ask grep, not Python: the dialects differ, and so do the flags.

    grep exits 0 for a match, 1 for none, and **2 for an error** -- a malformed
    pattern, an unsupported flag. Reporting `returncode == 0` folds 2 into "no
    match", so every `assert not _matches(...)` below passes whether grep
    applied the workflow's rule and disagreed, or never ran it at all.

    That is not a theoretical input here: both the pattern and the flags are
    read out of the workflow, so a workflow edit is exactly what produces a 2 --
    the one event these tests exist to notice, and the one where folding it into
    False makes them go quiet instead (#15850 review).
    """
    # Fixed argv; inputs are module constants.
    result = subprocess.run(  # nosec B603 B607
        ["grep", _grep_flags(), pattern],
        input=line,
        text=True,
        check=False,
        capture_output=True,
    )
    if result.returncode not in (0, 1):
        raise AssertionError(
            f"grep exited {result.returncode} for pattern {pattern!r} with flags "
            f"{_grep_flags()!r}: {result.stderr.strip()!r}. That is not 'no match' -- "
            "the pattern taken from the workflow did not run, so a test asserting "
            "no match would have passed without applying the rule."
        )
    return result.returncode == 0


def test_matches_refuses_to_read_a_grep_failure_as_no_match() -> None:
    """The acceptance test for that refusal, not just that something objected.

    Every ALLOWED case asserts `not _matches(...)`, which grep can satisfy two
    ways: exit 1, the thing under test, and exit 2, "I could not run that". The
    `match=` here pins WHICH refusal fired -- a bare `pytest.raises` would be
    satisfied by any AssertionError, including one from a genuinely broken
    helper, which is the same conflation one level up.
    """
    with pytest.raises(AssertionError, match="did not run"):
        _matches("^[unterminated", "anything")


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


def _final_block(body: str) -> str:
    """Everything after the last blank line — what the workflow scans.

    #15850 review: the workflow used `git interpret-trailers --parse`, which
    returns only `Key: value` lines and therefore **dropped the promo footer**
    entirely — it is a bare line, not a trailer. Fixing the prose false-positive
    had opened a bypass: a contributor could add the banned footer and pass.

    This mirrors the workflow's `awk 'BEGIN{RS=""} END{print}'` rather than
    reimplementing trailer semantics, because a helper that parses differently
    from the thing it verifies asserts about something nobody runs.
    """
    blocks = [b for b in body.split("\n\n") if b.strip()]
    return blocks[-1] if blocks else ""


#: A bare, unstructured footer. `interpret-trailers` does not return it, so a
#: parse-based scan cannot see it at all (#15850 review, CWE-693).
UNSTRUCTURED_FOOTER = "Generated with [Claude Code](https://claude.com/claude-code)"


def test_the_unstructured_footer_is_still_detected() -> None:
    """MUTATION TARGET. Scan parsed trailers instead of the raw block and this passes.

    The promo line is not `Key: value`, so any parse-based approach drops it
    and the check silently stops enforcing the rule it exists for.
    """
    body = f"fix: something\n\nA description.\n\n{UNSTRUCTURED_FOOTER}\n"
    assert _matches(_agent_re(), _final_block(body)), (
        "the unstructured Claude footer was not detected — a parse-based scan " "drops it and opens a bypass (#15850)"
    )


#: Prose that BEGINS a line with a banned string, above a real trailer block.
#: `^`-anchoring alone rejects these; only scanning the parsed trailer block
#: distinguishes them (#15850 review).
LINE_START_PROSE = [
    "Generated with [Claude Code] is the promo trailer this rule bans.",
    "Claude-Session: lines leak a session URL, which is why they are refused.",
    "Co-authored-by: noreply@paperclip is the address the rule matches.",
]


@pytest.mark.parametrize("line", LINE_START_PROSE)
def test_prose_beginning_a_line_is_not_a_trailer(line: str) -> None:
    """A commit documenting this policy starts a line with what it quotes.

    The workflow takes the message's RAW final block -- `awk 'BEGIN{RS=""}
    END{print}'` -- before matching, so prose above that block is out of scope
    positionally rather than by a pattern that has to guess. `_final_block`
    below mirrors that awk exactly.

    Not `git interpret-trailers --parse`, which this used to say: it returns
    only `Key: value` lines and drops a bare unstructured footer entirely,
    which is a bypass rather than a narrowing (#15850 review).
    """
    body = f"fix: something\n\n{line}\n\nSigned-off-by: A <a@b.c>\n"
    # Fixed argv; input is a module constant.
    parsed = _final_block(body)
    assert not _matches(_agent_re(), parsed), (
        f"prose beginning a line was read as a trailer: {line!r} -- "
        "the final-block parse is not being applied (#15850)"
    )


def test_the_workflow_scans_the_raw_final_block() -> None:
    """Pins the rule itself, because the prose cases cannot.

    `LINE_START_PROSE` extracts a body's final block with `_final_block` and
    asserts the pattern does not match it -- which stays true no matter what
    the workflow feeds its grep. Reverting the workflow to scan `${body}` leaves
    every one of those tests green while restoring the exact defect they were
    written for. Mutation-verified: that revert passed 15/15 before this
    assertion existed.

    So the application is pinned here, at the one line where it is expressed.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r'\$\{trailers\}"\s*\|\s*grep\s+-iqE\s+"\$\{agent_re\}"', text), (
        "the agent_re grep does not read ${trailers} -- it is scanning the whole "
        "commit body, so prose beginning a line is matched as a trailer (#15850)"
    )
    assert re.search(r"trailers=.*BEGIN\{RS=", text), (
        "${trailers} is not the RAW final block. A parse-based extraction "
        "(`interpret-trailers --parse`) returns only `Key: value` lines and drops "
        "the unstructured footer entirely, which is a bypass, not a narrowing (#15850)."
    )
