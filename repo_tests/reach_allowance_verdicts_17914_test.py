# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The allowance table is a record of decisions, so it is checked like one (#17914).

52 declarations bound their sweep with a constant plus a `growth` allowance, which is the shape
that produced seventeen re-pins of one guard. "52 carry an allowance" is NOT "52 pending
conversions" -- a relative floor needs a reference measuring the SAME population, and where the
reference drifts on its own a fraction walks downward and fires with nothing wrong. So each one
carries a verdict and a measured reason in `repo_tests/_reach_policy`.

These cases guard the TABLE. Whether every declaration is IN it is asserted in
`reach_declarations_test`, which is where the live registry is swept.

Nothing here reads the tree, deliberately: a table of recorded decisions should be checkable
without a sweep, and keeping it that way is what lets these run at pre-push unmarked.
"""

from __future__ import annotations

from repo_tests._reach_policy import (
    ABSOLUTE,
    ALLOWANCE_VERDICTS,
    CONVERTIBLE,
    CONVERTIBLE_BACKLOG,
    REASON_CODES,
    VERDICTS,
)


def test_the_conversion_backlog_only_shrinks() -> None:
    """`CONVERTIBLE` is a backlog with a frozen membership, not a note someone meant to revisit.

    A set rather than a ceiling, for the reason above: a count lets one conversion pay for one
    new deferral.
    """
    convertible = {name for name, (verdict, _, _) in ALLOWANCE_VERDICTS.items() if verdict == CONVERTIBLE}
    assert convertible == CONVERTIBLE_BACKLOG, (
        f"the CONVERTIBLE verdicts and the frozen backlog disagree. In the table but not the "
        f"backlog: {sorted(convertible - CONVERTIBLE_BACKLOG)}; in the backlog but no longer "
        f"CONVERTIBLE: {sorted(CONVERTIBLE_BACKLOG - convertible)}. Converting one means "
        f"removing it from BOTH in the same change; adding one is a new deferral and needs a "
        f"stated blocker, not a slot freed by someone else's work."
    )


def test_every_verdict_and_reason_code_is_one_of_the_recorded_ones() -> None:
    """The table is read by membership, so a typo would have passed as a recorded decision.

    `"ABSOLUTEE"` is not `ABSOLUTE` and an empty reason is not a reason; both would have
    satisfied `name in ALLOWANCE_VERDICTS` and neither says anything. Closed sets plus a
    non-empty reason, which is the whole content of the obligation.
    """
    bad = sorted(
        f"{name}: verdict={verdict!r} code={code!r} reason={reason[:40]!r}"
        for name, (verdict, code, reason) in ALLOWANCE_VERDICTS.items()
        if verdict not in VERDICTS or code not in REASON_CODES or len(reason.strip()) < 20
    )
    assert not bad, (
        "ALLOWANCE_VERDICTS entries with an unrecognised verdict, an unrecognised reason code, "
        "or no reason worth reading:\n  " + "\n  ".join(bad)
    )


def test_the_verdict_check_rejects_a_typo_and_an_empty_reason() -> None:
    """Known positive (RATCHET_BASELINES rule 6): the validation must see a bad row.

    Without this, the check above is a claim about a table that happens to be clean, and a
    future row spelled `"ABSOLUTEE"` -- which satisfies `name in ALLOWANCE_VERDICTS` exactly as
    well as the real thing -- would read as a recorded decision.
    """
    assert "ABSOLUTEE" not in VERDICTS
    assert "" not in REASON_CODES
    planted = {
        "typo-verdict": ("ABSOLUTEE", "NOT_PATHS", "a reason long enough to be real prose"),
        "unknown-code": (ABSOLUTE, "BECAUSE_I_SAID_SO", "a reason long enough to be real prose"),
        "empty-reason": (ABSOLUTE, "NOT_PATHS", "   "),
        "good-row": (CONVERTIBLE, "REFERENCE_EXISTS", "a reason long enough to be real prose"),
    }
    caught = {
        name
        for name, (verdict, code, reason) in planted.items()
        if verdict not in VERDICTS or code not in REASON_CODES or len(reason.strip()) < 20
    }
    assert caught == {"typo-verdict", "unknown-code", "empty-reason"}, caught


def test_the_table_is_not_empty() -> None:
    """The vacuity floor: every assertion here iterates the table, so an empty one passes all."""
    assert len(ALLOWANCE_VERDICTS) >= 40, (
        f"only {len(ALLOWANCE_VERDICTS)} verdicts recorded; the sweep that fills this started "
        f"from 52 allowance-carrying declarations, so a number this small means entries were "
        f"dropped rather than converted"
    )
