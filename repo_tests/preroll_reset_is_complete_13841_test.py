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
#: An assignment inside `reset()`: `this.name = ...`.
_ASSIGNED = re.compile(r"^\s+this\.([a-zA-Z][a-zA-Z0-9]*)\s*=", re.M)


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


def test_reset_clears_every_declared_field() -> None:
    """The property item 3 claims. `timer` is cleared via clearTimeout, so it counts."""
    fields_block, reset_block = _object_literal_and_reset()
    declared = set(_FIELD.findall(fields_block))
    assigned = set(_ASSIGNED.findall(reset_block))

    missed = sorted(declared - assigned)
    assert not missed, (
        f"_preroll.reset() does not clear {missed}. Every field the object declares must be "
        "cleared, or a stale value survives into the next utterance and mis-sizes its lead-in "
        "-- the #13736 defect this object was extracted to prevent. Nothing behavioural catches "
        "it: dropping a field from reset() leaves all 18 pre-roll tests passing."
    )

    stray = sorted(assigned - declared)
    assert not stray, f"reset() assigns {stray}, which the object does not declare -- a rename left it behind"
