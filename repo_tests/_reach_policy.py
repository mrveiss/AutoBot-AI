# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Why each absolute reach floor is still absolute, and which ones are not done (#17914).

52 declarations bound their sweep with `floor=N` plus a `growth=M` allowance. The floor is a
constant, the tree grows, and the gap is consumed on a schedule -- `hooks-path-override` was
re-pinned seventeen times and every one of those numbers was correct when written.

**"52 carry an allowance" is not "52 pending conversions", and reading it that way is the
expensive mistake.** A relative floor needs a reference that measures the SAME population, so
that every change the rule should welcome moves numerator and denominator together
(`RATCHET_BASELINES.md` rule 7). Where the reference drifts on its own, a fraction walks
downward with nothing wrong and fires falsely -- the `docs/` case, where `archives/` only ever
grows, so a share of all docs sinks on its own. Many of these 52 are CORRECTLY absolute, and
"it has never tripped" is not the test for either verdict.

So each one carries a verdict and a measured reason. Two verdicts only:

``ABSOLUTE``
    No reference co-moves with this population. The floor stays a constant, and the mid-window
    rule in `_reach.verify_floor` (#17356) is what keeps it off the bottom of its window.
``CONVERTIBLE``
    A reference enumerating the same class exists and the conversion is real work still to do.
    `MAX_CONVERTIBLE` pins how many may remain and RATCHETS DOWN only, so this is a backlog
    that cannot grow quietly rather than a note somebody meant to come back to.

The reason codes, each a different argument -- conflating them produces the wrong fix:

``NOT_PATHS``
    The discovered items are parsed objects -- routers, workflow jobs, locale keys, symbols,
    source line sites. No file enumeration measures this population at all, so there is no
    reference to take a fraction of.
``SUBSET_DRIFTS``
    A proper subset of a larger file class, where the rest of the class grows at its own rate.
    A fraction of the class sinks as the other half grows: production Python against all
    tracked Python falls whenever tests are added, which is a change the rule welcomes.
``FIXED_INVENTORY``
    A small, deliberately enumerable set. A fraction of a large reference is meaningless at
    this size, and the band is already equality or close to it.
``COMPLETION_GAP``
    The guard completes materially fewer items than it lists. The relative mode applies ONE
    fraction to both `examined()` and `completed()`, so no single value can bound both.
``FRACTION_IS_COARSER``
    A reference exists and agrees, and the population is small enough that the coarsest safe
    fraction implies a floor BELOW the constant it would replace -- which #17914 AC2 refuses --
    while the only tighter fraction fires on a one-file skew.
``REFERENCE_EXISTS``
    The population is an independently enumerable file class. This is the `CONVERTIBLE` reason.

Measured 2026-10-04 against `origin/main` at `baec13de40`, by importing the registry and
running each declaration's own `discover` once. Counts are deliberately NOT written into the
reasons: a population written down here outlives the merge that changes it (#17384).
"""

from __future__ import annotations

from repo_tests._reach_policy_verdicts import (  # noqa: F401 (re-exported, #12732)
    ABSOLUTE,
    ALLOWANCE_VERDICTS,
    CONVERTIBLE,
)

#: The only legal verdicts and reason codes. Closed sets, because the table is read by a test
#: that compared membership and not spelling: `"ABSOLUTEE"` or an empty reason would have been
#: accepted as a recorded decision.
VERDICTS = frozenset({ABSOLUTE, CONVERTIBLE})
REASON_CODES = frozenset(
    {"NOT_PATHS", "SUBSET_DRIFTS", "FIXED_INVENTORY", "COMPLETION_GAP", "FRACTION_IS_COARSER", "REFERENCE_EXISTS"}
)

#: Declaration name -> (verdict, reason code, why).
#:
#: Every absolute declaration carrying a `growth` allowance must appear here, and
#: `reach_declarations_test` fails on a new one that does not -- so the pattern cannot be
#: re-added without someone writing down why (#17914 AC4). The rows live in
#: `_reach_policy_verdicts` (split at the 600-line ceiling, #12732) and are re-exported above.

#: Declarations still waiting for a relative floor. Compared as a SET in both directions by
#: `reach_declarations_test`, not by a count: a `<=` ceiling never forces itself down, and one
#: declaration converting would silently free a slot for a new unconverted one
#: (RATCHET_BASELINES.md rule 4). SHRINKS ONLY -- an entry leaves when its declaration converts,
#: and nothing may add one.
CONVERTIBLE_BACKLOG = frozenset({"tracked-key-material"})
