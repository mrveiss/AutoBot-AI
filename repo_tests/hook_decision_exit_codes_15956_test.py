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

The parse is deliberately shallow — it pairs each decision with the next ``exit``
that follows it in the file. That is sufficient for the guard shape in use here,
where a decision is always immediately followed by its exit, and it fails loudly
rather than silently if a hook adopts a structure it cannot read: see
``test_every_decision_has_a_reachable_exit``.
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

DECISION_RE = re.compile(r'permissionDecision\\?":\\?"(?P<decision>ask|allow|deny)')
EXIT_RE = re.compile(r"^\s*exit\s+(?P<code>\d+)\s*$")


def _hook_files() -> list[Path]:
    if not HOOKS_DIR.is_dir():
        pytest.skip(f"{HOOKS_DIR} does not exist in this checkout")
    return sorted(p for p in HOOKS_DIR.glob("*.sh") if not p.name.endswith("_test.sh"))


def _decisions_with_exits(path: Path) -> list[tuple[int, str, int | None]]:
    """Pair each decision emission with the next ``exit`` line after it.

    Returns ``(line number, decision, exit code or None)`` per emission.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    found: list[tuple[int, str, int | None]] = []
    for index, line in enumerate(lines):
        match = DECISION_RE.search(line)
        if not match:
            continue
        code: int | None = None
        for following in lines[index + 1 : index + 8]:
            exit_match = EXIT_RE.match(following)
            if exit_match:
                code = int(exit_match.group("code"))
                break
        found.append((index + 1, match.group("decision"), code))
    return found


@pytest.mark.parametrize("hook", _hook_files(), ids=lambda p: p.name)
def test_decision_exit_codes_match_the_harness_contract(hook: Path) -> None:
    """An `ask` or `allow` must exit 0, or the harness discards it as a denial."""
    wrong = [
        (line, decision, code)
        for line, decision, code in _decisions_with_exits(hook)
        if code is not None and code != EXPECTED_EXIT[decision]
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
        (line, decision)
        for line, decision, code in _decisions_with_exits(hook)
        if code is None
    ]
    assert not unpaired, "\n".join(
        f"{hook.name}:{line} emits permissionDecision '{decision}' with no `exit` "
        "within the following 7 lines. This guard cannot tell whether the harness "
        "will read it. Restructure the hook or extend the parser — do not skip it."
        for line, decision in unpaired
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
        _decisions_with_exits(hook) for hook in hooks
    ), "no hook emits a permissionDecision — the regex has probably gone stale"
