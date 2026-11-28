# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Hold a declaration's `what=` to the population its `discover` actually reaches (#17844).

`floor` is a number the framework verifies. `what=` was free text nobody verified, and a
`declare()` records both in the same call. A guard can therefore be in a third state that
neither the floor assertion nor `guard_reach_meta_test` can see: **floored correctly, over the
wrong population.**

Measured on #17844's base: of 52 `what=` strings, 14 named a root, path or scope and 38 were
bare population nouns. Seven guards claimed some form of *"production python files"* over floors
spanning 2555 to 3247. The 692-file spread is legitimate -- the guards have different scan roots
-- and invisible, because only two of the seven said so. A reach report could not distinguish a
guard covering the tree from one covering two thirds of it.

WHAT THIS CHECK CANNOT SEE, STATED RATHER THAN DISCOVERED LATER
---------------------------------------------------------------
* **A declaration with no `roots=` is not checked at all.** Scope stays opt-in because a
  declaration whose items are not paths -- parsed workflow jobs, locale keys, router names --
  has no path prefix to compare. `reach_declarations_test` records those separately so the
  un-scoped set is a list that shrinks rather than a silence.
* **A root is satisfied by ONE item under it.** This catches a root the sweep stopped reaching
  entirely; it says nothing about a root the sweep reaches badly. That is the floor's job, and
  the floor is a single number over all roots -- a per-root floor is the fuller fix and is not
  this one.
* **Prefix matching, not path semantics.** `roots=("autobot-backend",)` also admits a future
  `autobot-backend-v2/`. Declaring the separator -- `"autobot-backend/"` -- is the remedy, and
  the existing call sites that already carry a trailing slash are why it is not forced here.
* **A `roots=` that ALIASES the constant `discover` walks cannot catch that constant being
  narrowed.** Every adopted call site passes its own `SCAN_ROOTS`/`_TREES`/`_ROOTS`, so
  narrowing the constant narrows both sides at once: the sweep shrinks, the claim shrinks with
  it, `verify_scope` stays green and `what=` simply re-renders to the smaller claim. That is
  the honest trade -- an independently written tuple cannot drift from the sweep by accident,
  an aliased one cannot be caught drifting on purpose -- and the second half is covered
  instead by `reach_scope_claim_17844_test`'s frozen expectation of each declaration's roots,
  which is written out by hand and fails when the constant moves. Reported by review; recorded
  here because the mutation that proves the check fires narrows the DISCOVERY, not the
  constant, and a reader could take that as covering both.
* **Nothing checks that `roots` is the WHOLE truth.** A guard may declare one of its two roots
  and the sweep over the undeclared one then reads as out-of-scope and fails loudly -- which is
  the safe direction, but it is a refusal rather than a discovery: this cannot tell you which
  root was forgotten.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence


def relative_paths(found: Sequence[object], root: Path) -> list[str] | None:
    """*found* as repository-relative POSIX strings, or ``None`` if it is not path-shaped.

    ``None`` rather than a raise, so the caller can report "this declaration cannot carry
    ``roots=``" as a declaration-level fact instead of as a sweep failure. A single non-path
    member is enough: a mixed sequence has no scope a prefix can describe.
    """
    resolved = root.resolve()
    rels: list[str] = []
    for item in found:
        if not isinstance(item, (str, os.PathLike)):
            return None
        text = Path(os.fspath(item))
        if text.is_absolute():
            try:
                text = text.resolve().relative_to(resolved)
            except ValueError:
                return None
        rels.append(text.as_posix())
    return rels


def scope_complaint(name: str, what: str, roots: tuple[str, ...], rels: list[str] | None) -> str:
    """The message for a declared scope the sweep does not match, or ``""`` when it does.

    Both directions, because they are different defects wearing one symptom. A declared root
    the sweep never reaches is the **overclaim** #17844 is about -- `what=` promising a
    population the discovery does not read. An item outside every declared root is the mirror:
    the string is narrower than the sweep, so a reader under-reads the guard's coverage and the
    data is still wrong.
    """
    if rels is None:
        return (
            f"[{name}] declares roots={roots} but its discovery returns items that are not "
            f"paths, so the claim cannot be checked against the sweep. Drop `roots=` and record "
            f"the declaration as un-scoped instead of carrying a scope nothing verifies."
        )
    unreached = [prefix for prefix in roots if not any(rel.startswith(prefix) for rel in rels)]
    if unreached:
        return (
            f"[{name}] claims {what!r}, but its sweep found NOTHING under {unreached}. "
            f"The floor is still cleared by the other root(s), so this passes every count check "
            f"while the guard speaks for a tree it no longer reads. Either fix the discovery or "
            f"narrow `roots=` -- and narrowing is a coverage decision, not a formatting one."
        )
    outside = sorted({rel for rel in rels if not rel.startswith(roots)})
    if outside:
        return (
            f"[{name}] claims {what!r}, but {len(outside)} discovered item(s) lie outside every "
            f"declared root -- e.g. {outside[:3]}. The scope is narrower than the sweep, so the "
            f"declaration under-reports what this guard covers. Widen `roots=`."
        )
    return ""
