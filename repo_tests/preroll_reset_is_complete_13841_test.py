# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""`_preroll.reset()` must clear every field the object declares (#13841).

Item 3 of #13841 extracted twelve loose module-level bindings into one object so
that "reset becomes one call and cannot miss a field". The first half is true.
The second was not, and the test suite proved it: dropping `this.pendingSec = 0`
from `reset()` left all 18 pre-roll tests passing.

So the structural fix removed the *opportunity* for the bug the issue describes --
three #13736 review findings of the form "field X was not reset alongside field
Y" -- without removing the *possibility*. A new field added to the object and
forgotten in `reset()` is the same defect in a tidier shape, and nothing behavioural
catches it: a stale `pendingSec` only shows up as a mis-sized lead-in on some later
utterance, which no unit test asserts.

This compares the two lists in source, so it is derived rather than enumerated and
cannot drift as fields are added. It is a static check for a reason: the object is
module-private, and exporting it to make it testable would widen the composable's
surface for the benefit of a guard.

The two sequence guards are deliberately NOT in the object and NOT reset --
`_utteranceSeq` and `_stopSeq` are monotonic, and zeroing them would make a stale
chunk's sequence match the new utterance's. They live outside `_preroll` precisely
so `reset()` cannot reach them, which is why this test finds nothing to say about
them.
"""

import re
from pathlib import Path

from repo_tests._paths import repo_root

_SOURCE = Path("autobot-frontend/src/composables/useVoiceOutput.ts")

#: A field line inside the object literal: `name: <init>,` at one indent level.
_FIELD = re.compile(r"^  (?!reset\b)([a-zA-Z][a-zA-Z0-9]*)\s*:", re.M)
#: An assignment inside `reset()`, with its VALUE: `this.name = <value>`.
_ASSIGNED = re.compile(r"^\s+this\.([a-zA-Z][a-zA-Z0-9]*)\s*=\s*(.+?)\s*$", re.M)

#: Values that constitute clearing. Every field of `_preroll` resets to one of these, so
#: the set is the contract rather than a convenience: review on #17887 noted that comparing
#: NAMES alone passes `this.pendingSec = this.pendingSec`, which clears nothing and is the
#: shape of the #13736 defect this guard exists to catch.
_CLEARING = {"[]", "0", "0.0", "false", "null", "''", '""', "undefined"}


def _object_literal_and_reset() -> tuple[str, str]:
    """The `_preroll` object literal, and the body of its `reset` method."""
    source = (repo_root() / _SOURCE).read_text(encoding="utf-8")
    start = source.index("const _preroll = {")
    literal = source[start : source.index("\n}\n", start)]
    reset_at = literal.index("reset(): void {")
    return literal[:reset_at], literal[reset_at:]


def test_the_object_literal_and_reset_were_both_found() -> None:
    """Non-vacuity: a rename that breaks the anchors must fail here, not pass empty."""
    fields_block, reset_block = _object_literal_and_reset()
    assert (
        len(_FIELD.findall(fields_block)) >= 9
    ), f"found too few fields to be reading the right block: {fields_block[:200]}"
    assert len(_ASSIGNED.findall(reset_block)) >= 9, "found too few assignments to be reading reset()"


def _reset_problems(fields_block: str, reset_block: str) -> list[str]:
    """Every way `reset()` can fail its contract, as a list -- so fixtures can drive it.

    Split out because a detector that only ever sees the real file cannot be shown to fail
    (the repo's own rule: every detector needs a fixture that trips it and one that does
    not). The fixtures below are literals in this file, so nothing they assert can degrade
    through a loader.
    """
    declared = set(_FIELD.findall(fields_block))
    assigned = {name: value.rstrip(";,") for name, value in _ASSIGNED.findall(reset_block)}
    problems = []
    missed = sorted(declared - set(assigned))
    if missed:
        problems.append(f"not cleared at all: {missed}")
    stray = sorted(set(assigned) - declared)
    if stray:
        problems.append(f"assigned but not declared: {stray}")
    not_clearing = sorted(
        f"{name} = {value}" for name, value in assigned.items() if name in declared and value not in _CLEARING
    )
    if not_clearing:
        problems.append(f"assigned something that does not clear: {not_clearing}")
    return problems


def test_reset_clears_every_declared_field() -> None:
    """The property item 3 claims. `timer` is cleared via clearTimeout, so it counts."""
    problems = _reset_problems(*_object_literal_and_reset())
    assert not problems, (
        f"_preroll.reset() breaks its contract: {problems}. Every field the object declares "
        "must be CLEARED, or a stale value survives into the next utterance and mis-sizes its "
        "lead-in -- the #13736 defect this object was extracted to prevent. Nothing behavioural "
        "catches it: dropping a field from reset() leaves all 18 pre-roll tests passing."
    )


# ---------------------------------------------------------------------------
# Contrast pair, on fixtures rather than on the tree: one that must pass and
# three that must trip. Without these the detector above is only ever shown
# agreeing with a file that already complies.
# ---------------------------------------------------------------------------

_COMPLETE = (
    "  pendingSec: 0,\n  holding: false,\n",
    "reset(): void {\n    this.pendingSec = 0\n    this.holding = false\n  },",
)


def test_a_complete_reset_is_accepted() -> None:
    assert _reset_problems(*_COMPLETE) == []


def test_a_field_missing_from_reset_is_reported() -> None:
    fields, _ = _COMPLETE
    problems = _reset_problems(fields, "reset(): void {\n    this.pendingSec = 0\n  },")
    assert any("not cleared at all" in p and "holding" in p for p in problems), problems


def test_an_assignment_that_does_not_clear_is_reported() -> None:
    """`this.pendingSec = this.pendingSec` satisfies a name comparison and clears nothing."""
    fields, _ = _COMPLETE
    problems = _reset_problems(
        fields, "reset(): void {\n    this.pendingSec = this.pendingSec\n    this.holding = false\n  },"
    )
    assert any("does not clear" in p for p in problems), problems


def test_an_assignment_to_an_undeclared_field_is_reported() -> None:
    fields, _ = _COMPLETE
    problems = _reset_problems(
        fields, "reset(): void {\n    this.pendingSec = 0\n    this.holding = false\n    this.gone = 0\n  },"
    )
    assert any("not declared" in p for p in problems), problems
