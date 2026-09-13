# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A PreToolUse hook's exit code decides whether its own decision is read (#15956).

The harness parses a hook's ``permissionDecision`` JSON from **stdout, and only on
exit 0**. Exit 2 is a blocking error whose reason is taken from **stderr**. So a
hook that prints ``"permissionDecision":"ask"`` and then exits 2 has its payload
discarded: the call is denied outright and the operator sees a refusal with no
reason, because nothing was written to stderr.

Two hooks did exactly that.

``protect-files.sh`` had two ``ask`` sites, both guarding the settings files, and
five ``deny`` sites. Its ``ask()`` helper ended in ``exit 2``, so for the whole
life of that bug the only path in that hook capable of reaching a human never
did — while every ``deny`` behaved correctly. ``scan-secrets.sh`` had the same
defect at its single non-zero exit, and there the author's intent is on the
record in the reason string itself: *"Review carefully before allowing"* is a
sentence written for a human who is being asked a question, and no human was
ever shown it.

**Why it survived.** A denial and a discarded ask produce an identical
observable: the tool call is blocked. Nothing in the output distinguishes
"refused on purpose" from "meant to ask you and could not", so the hooks looked
like they were working. That is also why this guard reads the *source* rather
than a hook's behaviour on one input — a runtime test would have to know which
decision was intended before it could tell the two apart, and that knowledge is
precisely what the bug destroys.

**Why the sweep is the test.** Two instances were found by grepping for the
shape rather than by following the report, which named one file. A fix limited
to the reported site is indistinguishable from a fix that checked its
neighbours, so the neighbour check is kept here permanently instead of being
performed once: any hook added later that emits a non-deny decision before a
non-zero exit fails this test rather than joining the pattern silently.

The parse is deliberately shallow, but it does not guess. It pairs a decision
with the next ``exit`` only when that exit is not indented deeper than the
decision itself; a deeper one sits inside a branch this parser cannot evaluate,
so execution may bypass it and reach a different exit later. Crediting it anyway
would let the guard certify a contract it never checked, silently and in the
passing direction — the defect this file exists to catch, one level up. Refused
pairings fail loudly through ``test_every_decision_has_a_reachable_exit``.

**Three dimensions, because the defect has moved twice.** ``EXPECTED_EXIT``
reads the exit code; ``STDERR_WRITE`` reads the channel the reason travels on;
and the membership check reads the decision *value* — added after a hook was
found emitting ``warn``, which is not in the contract and therefore does nothing
at all while looking exactly like a decision that works (#16079). Each dimension
was added because a fix relocated the bug into it. The lesson is kept here
deliberately: a guard measures one dimension, and the bug moves to the next.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ._paths import repo_root

HOOKS_DIR = repo_root() / ".claude" / "hooks"

# The harness contract. `deny` blocks the call and its reason comes from stderr,
# so exit 2 is correct. Every other decision is only read on exit 0.
EXPECTED_EXIT = {"deny": 2, "ask": 0, "allow": 0}

# Matches ANY value, not only the valid three. A detector that enumerates the
# valid set cannot see an invalid member of it -- and an invalid decision is
# inert, which is the single thing this file most needs to catch. Found #16079
# that way: a `warn` this regex was blind to, sitting green for its whole life.
DECISION_RE = re.compile(r'permissionDecision\\?":\\?"(?P<decision>[A-Za-z_]*)')
EXIT_RE = re.compile(r"^(?P<indent>\s*)exit\s+(?P<code>\d+)\s*$")
INDENT_RE = re.compile(r"^\s*")
STDERR_WRITE = re.compile(r">&\s*2")

VALID_DECISIONS = frozenset(EXPECTED_EXIT)

# Emitted values outside the contract, each pinned to the issue owning its
# remedy. A ratchet, not an exemption list: the test below asserts each entry is
# STILL emitted and STILL invalid, so a fix fails this suite until the entry is
# dropped in the same PR. An exemption list that only grows is where this class
# of defect hides.
KNOWN_INVALID = {
    ("block-dangerous-commands.sh", "warn"): "#16079",
}


def _hook_files() -> list[Path]:
    if not HOOKS_DIR.is_dir():
        pytest.skip(f"{HOOKS_DIR} does not exist in this checkout")
    return sorted(p for p in HOOKS_DIR.glob("*.sh") if not p.name.endswith("_test.sh"))


def _pair_exit(lines: list[str], index: int) -> tuple[int | None, int, str]:
    """Pair the decision at ``lines[index]`` with the exit it actually reaches.

    Returns ``(code, last line scanned, status)``, where status is ``"paired"``,
    ``"none"`` when no ``exit`` appears in the window, or ``"conditional"``.

    The indent rule is the substance here. Accepting the first *textual* ``exit``
    lets a conditional ``exit 0`` be selected while execution falls through to a
    later ``exit 2``: the guard would then certify a contract it never checked,
    silently and in the passing direction -- the same shape as the defect this
    file exists to catch. An ``exit`` nested deeper than its decision is reached
    only through a branch this parser cannot evaluate, so it is refused rather
    than assumed, and the caller turns that refusal into a loud failure.
    """
    decision_indent = len(INDENT_RE.match(lines[index]).group(0))
    for offset in range(index + 1, min(index + 8, len(lines))):
        exit_match = EXIT_RE.match(lines[offset])
        if not exit_match:
            continue
        if len(exit_match.group("indent")) > decision_indent:
            return None, offset, "conditional"
        return int(exit_match.group("code")), offset, "paired"
    return None, min(index + 7, len(lines) - 1), "none"


def _emissions(path: Path) -> list[tuple[int, str, int | None, str, bool]]:
    """Every decision in ``path``: line, value, exit code, pairing status, stderr.

    One scanner, deliberately. The exit window and the stderr window were
    computed by two functions that had to agree and nothing made them; a guard
    whose two halves can drift apart is the thing this suite is about.
    """
    return _scan(path.read_text(encoding="utf-8").splitlines())


def _scan(lines: list[str]) -> list[tuple[int, str, int | None, str, bool]]:
    """The scan itself, over lines, so fixtures can exercise it without a file."""
    out: list[tuple[int, str, int | None, str, bool]] = []
    for index, line in enumerate(lines):
        match = DECISION_RE.search(line)
        if not match:
            continue
        code, end, status = _pair_exit(lines, index)
        window = lines[max(0, index - 8) : end + 1]
        out.append(
            (
                index + 1,
                match.group("decision"),
                code,
                status,
                any(STDERR_WRITE.search(w) for w in window),
            )
        )
    return out


@pytest.mark.parametrize("hook", _hook_files(), ids=lambda p: p.name)
def test_decision_exit_codes_match_the_harness_contract(hook: Path) -> None:
    """An `ask` or `allow` must exit 0, or the harness discards it as a denial."""
    wrong = [
        (line, decision, code)
        for line, decision, code, _status, _err in _emissions(hook)
        if decision in VALID_DECISIONS
        and code is not None
        and code != EXPECTED_EXIT[decision]
    ]
    assert not wrong, "\n".join(
        f"{hook.name}:{line} emits permissionDecision '{decision}' then exits {code}; "
        f"expected exit {EXPECTED_EXIT[decision]}. "
        + (
            "A non-zero exit makes the harness read this as a blocking error and take "
            "its reason from stderr, so the decision above is discarded and the "
            "operator sees a refusal with no reason."
            if decision != "deny"
            else "A deny must exit 2 so the call is actually blocked."
        )
        for line, decision, code in wrong
    )


@pytest.mark.parametrize("hook", _hook_files(), ids=lambda p: p.name)
def test_every_decision_has_a_reachable_exit(hook: Path) -> None:
    """Fail loudly if a hook's shape defeats the shallow parse above.

    A decision this test cannot pair with an exit is a decision it is not
    checking, and an unchecked emission is exactly the state #15956 was in.
    Better to fail here and have someone teach the parser than to report a
    green that covered nothing.
    """
    unpaired = [
        (line, decision, status)
        for line, decision, code, status, _err in _emissions(hook)
        if code is None and decision in VALID_DECISIONS
    ]
    assert not unpaired, "\n".join(
        f"{hook.name}:{line} emits permissionDecision '{decision}' "
        + (
            "with no `exit` within the following 7 lines."
            if status == "none"
            else "whose next `exit` is indented deeper than the decision, so it sits "
            "inside a branch and execution may bypass it to reach a different one."
        )
        + " This guard cannot tell whether the harness will read it. Restructure "
        "the hook or extend the parser — do not skip it."
        for line, decision, status in unpaired
    )


def test_the_sweep_covers_more_than_the_two_known_hooks() -> None:
    """The neighbour check is the point, so assert it is actually sweeping.

    #15956 was reported against one file and was true of two. If this suite ever
    narrows to the files that were known at the time, it stops being a sweep and
    becomes a regression test for two lines.
    """
    hooks = _hook_files()
    assert len(hooks) >= 3, (
        f"only {len(hooks)} hook(s) found under {HOOKS_DIR}; this guard exists to "
        "check every hook, not the two that were known when it was written"
    )
    assert any(
        _emissions(hook) for hook in hooks
    ), "no hook emits a permissionDecision — the regex has probably gone stale"


# --------------------------------------------------------------- the channel
#
# EXPECTED_EXIT above measures the EXIT CODE. Once `ask` was corrected to exit 0,
# the remaining half of this defect moved into the CHANNEL: `deny` still exits 2,
# which is right, but its reason went to stdout, which exit 2 discards. The guard
# was then unable to tell the fixed file from the broken one -- it pinned the
# broken half as correct, because the dimension it measures was no longer the
# dimension the bug lived in.
#
# That is the generalisable lesson and the reason this second check exists:
# **when a fix moves a defect from one dimension to another, the guard has to
# move with it.** A suite that only ever checks the old dimension reports green
# on the new bug.

@pytest.mark.parametrize("hook", _hook_files(), ids=lambda p: p.name)
def test_a_blocking_decision_writes_its_reason_to_stderr(hook: Path) -> None:
    """Exit 2 takes its reason from stderr, so a silent exit-2 explains nothing.

    Without this, a hook can satisfy every exit-code assertion above and still
    give the operator a bare block -- which is the original #15956 symptom
    ("No stderr output"), simply relocated from `ask` to `deny`.
    """
    silent = [
        (line, decision)
        for line, decision, code, _status, has_stderr in _emissions(hook)
        if code not in (None, 0) and not has_stderr
    ]
    assert not silent, "\n".join(
        f"{hook.name}:{line} emits '{decision}' and exits non-zero without writing to stderr. "
        "The harness takes an exit-2 reason from stderr and parses stdout only on exit 0, so "
        "the reason above is discarded and the operator sees a block with no explanation. "
        "Add `printf '%s\\n' \"$REASON\" >&2` beside it."
        for line, decision in silent
    )


# ------------------------------------------------------------ the value
#
# EXPECTED_EXIT measures the exit code and STDERR_WRITE measures the channel.
# A decision has a third dimension that neither reads: **the value itself**.
# `warn` is well-formed JSON in the right place with the right shape and is not
# in the contract, so nothing acts on it -- inert, and indistinguishable from a
# working decision at every site a reader would check. See #16079.
#
# The detector could not see it, and that is the part worth keeping: the regex
# enumerated `ask|allow|deny`, so it matched the valid values and was blind to
# an invalid one. A guard keyed on the set of correct answers cannot report a
# wrong answer. It now matches any value and checks membership here.


@pytest.mark.parametrize("hook", _hook_files(), ids=lambda p: p.name)
def test_every_decision_value_is_in_the_harness_contract(hook: Path) -> None:
    """A value outside allow/deny/ask is not a weaker decision -- it is none."""
    invalid = [
        (line, decision)
        for line, decision, _code, _status, _err in _emissions(hook)
        if decision not in VALID_DECISIONS
        and (hook.name, decision) not in KNOWN_INVALID
    ]
    assert not invalid, "\n".join(
        f"{hook.name}:{line} emits permissionDecision '{decision}', which is not one "
        f"of {sorted(VALID_DECISIONS)}. The harness does not recognise it, so the "
        "emission does nothing at all while looking exactly like one that works. "
        "Use a contract value, or drop the JSON and print plain text."
        for line, decision in invalid
    )


def test_the_known_invalid_ratchet_only_shrinks() -> None:
    """Each pinned entry must still be present and still invalid.

    This is what separates a ratchet from an exemption list. When #16079 is
    fixed, this fails until its entry is removed in the same PR -- so the list
    cannot quietly outlive the defects it records, which is the failure mode of
    every allowlist that only ever grows.
    """
    live = {
        (hook.name, decision)
        for hook in _hook_files()
        for _line, decision, _code, _status, _err in _emissions(hook)
        if decision not in VALID_DECISIONS
    }
    stale = sorted(set(KNOWN_INVALID) - live)
    assert not stale, "\n".join(
        f"KNOWN_INVALID pins {hook}:'{decision}' ({KNOWN_INVALID[(hook, decision)]}) "
        "but that emission is gone or now valid. Remove the entry in the PR that "
        "fixed it."
        for hook, decision in stale
    )


# ------------------------------------------------------- guarding the detector
#
# Every assertion above is only as good as `_scan`. Run over the real hooks
# alone, a detector that stopped detecting would report an empty population --
# and an empty population passes every "no bad emissions" assertion in this file.
# The sweep test catches total blindness; these fixtures catch the rest: that it
# matches what it must, refuses what it must not, and pairs the right `exit`.

_FALL_THROUGH = [
    'echo \'{"permissionDecision":"deny"}\'',
    "if [ -n \"$X\" ]; then",
    "    exit 0",
    "fi",
    "exit 2",
]


def test_the_detector_matches_a_real_emission() -> None:
    found = _scan(['  echo \'{"permissionDecision":"ask"}\'', "  exit 0"])
    assert found == [(1, "ask", 0, "paired", False)]


def test_the_detector_ignores_a_line_that_is_not_an_emission() -> None:
    assert _scan(["# permissionDecision is discussed here", "exit 0"]) == []


def test_the_detector_sees_a_value_outside_the_contract() -> None:
    """The #16079 case: blindness to an invalid value is the failure that matters."""
    found = _scan(['echo \'{"permissionDecision":"warn"}\' >&2', "exit 0"])
    assert [(d, s) for _l, d, _c, s, _e in found] == [("warn", "paired")]


def test_a_conditional_exit_is_refused_rather_than_paired() -> None:
    """Taking the first textual `exit` here would report exit 0 for a deny.

    That is a pass in the wrong direction: the guard would certify the contract
    on a path execution may never take. Refusing the pairing routes it to
    `test_every_decision_has_a_reachable_exit`, which fails loudly instead.
    """
    (_line, decision, code, status, _err), = _scan(_FALL_THROUGH)
    assert (decision, code, status) == ("deny", None, "conditional")


def test_an_unconditional_exit_at_the_same_indent_is_paired() -> None:
    """The contrast case -- the rule must not refuse the shape the hooks use."""
    (_line, _decision, code, status, _err), = _scan(
        ['  echo \'{"permissionDecision":"deny"}\'', "  exit 2", "exit 0"]
    )
    assert (code, status) == (2, "paired")


def test_the_stderr_window_closes_at_the_paired_exit() -> None:
    """A `>&2` after the exit belongs to a later block, not to this decision."""
    found = _scan(
        ['echo \'{"permissionDecision":"deny"}\'', "exit 2", 'echo "other" >&2']
    )
    assert found[0][4] is False
