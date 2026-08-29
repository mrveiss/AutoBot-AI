# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15278 -- the credential-vault-resolution allowlist's TRACKED_GAP class has no ratchet.

``credential_vault_resolution_guard_test.py`` (#15269) keeps three assertions over its
``ALLOWLIST`` (now in ``credential_vault_resolution_allowlist.py``, #15278): a sanity
floor on the discovered credential-field count, every direct read must be allowlisted,
and every allowlist entry must still correspond to a real read. None of those three
caps the allowlist's overall size, so a developer could silence a brand-new violation
by appending an entry -- the guard would go green either way. This module adds the cap
that was missing, mirroring the shrink-only ratchet ``scripts/check_python_file_size.py``
already uses for ``KNOWN_LARGE``: a recorded ceiling that fails the build both when the
live count exceeds it (new debt added silently) and when it falls below it without the
ceiling being lowered to match (debt paid down without the ratchet recording the win,
#14498's lesson).

Scope: TRACKED_GAP entries only
--------------------------------
``ALLOWLIST`` holds three classes, distinguished by the reason string's prefix.
``AUTH_BOOTSTRAP`` (the credential gates the vault/DB itself, or is the platform's own
internal-auth token) and ``NOT_A_READ`` (the regex's only match is prose) are
classifications, not a backlog -- forcing either to shrink would eventually pressure
someone into mis-classifying a genuinely irreducible or non-read entry just to satisfy
a ratchet that was never about them. Only ``TRACKED_GAP`` -- real debt, tracked in
#15276 -- is a backlog whose count belongs under a ratchet, and
``test_auth_bootstrap_growth_does_not_move_the_tracked_gap_count`` proves the other two
classes are exempt rather than merely asserting it in prose.

What the marker check does and does not verify
------------------------------------------------
Every ``TRACKED_GAP`` entry's reason is expected to read ``TRACKED_GAP #<issue>: <text>``.
``_malformed_tracked_gap_markers`` checks that *format* -- a literal ``#`` followed by
digits, a colon, and non-empty text -- so a marker with no number, a non-numeric one, or
a missing separator is caught. It does **not**, and cannot from inside an offline test
run, check that the numbered issue actually exists or is still open: that needs a network
call (``gh issue view <n>`` or the REST API), and this guard makes none, the same
trade-off ``ratchet_base_guard_test.py`` documents for its own workflow-only checks.
A fabricated-but-well-formed issue number (e.g. ``TRACKED_GAP #1: ...`` naming a closed
or nonexistent issue) will pass this guard. Closing that gap is a separate, explicitly
network-dependent job -- not something to fake a pass for here.
"""

from __future__ import annotations

import re

from repo_tests.credential_vault_resolution_allowlist import ALLOWLIST, _AUTH_BOOTSTRAP, _TRACKED

#: The recorded TRACKED_GAP count. THIS RATCHET TURNS BOTH WAYS: raise it only by
#: adding a new, correctly TRACKED_GAP-marked entry in the same change, and lower it
#: whenever a TRACKED_GAP entry is fixed and removed -- never leave it stale in
#: either direction (#15278).
TRACKED_GAP_CEILING = 29

_TRACKED_GAP_MARKER_RE = re.compile(rf"^{re.escape(_TRACKED)} #(\d+):\s+\S")


def _tracked_gap_entries(allowlist: dict[tuple[str, str], str]) -> dict[tuple[str, str], str]:
    """Every *allowlist* entry classified TRACKED_GAP -- the only class this ratchet tracks."""
    return {key: reason for key, reason in allowlist.items() if reason.startswith(_TRACKED)}


def _tracked_gap_count(allowlist: dict[tuple[str, str], str]) -> int:
    return len(_tracked_gap_entries(allowlist))


def _malformed_tracked_gap_markers(
    allowlist: dict[tuple[str, str], str],
) -> list[tuple[tuple[str, str], str]]:
    """TRACKED_GAP entries whose reason does not match ``TRACKED_GAP #<n>: <text>``.

    Format only -- see the module docstring for why issue existence/open-state is not,
    and cannot offline be, checked here.
    """
    entries = _tracked_gap_entries(allowlist)
    return [(key, reason) for key, reason in entries.items() if not _TRACKED_GAP_MARKER_RE.match(reason)]


def _tracked_gap_verdict(live_count: int, ceiling: int) -> str | None:
    """Message for *live_count* against the recorded *ceiling*, or None if it holds.

    Mirrors ``scripts/check_python_file_size.py``'s ``_grandfathered_verdict``: the
    ratchet turns one way only, checked in both directions.
    """
    if live_count > ceiling:
        return (
            f"TRACKED_GAP count is {live_count}, over its recorded ceiling of {ceiling}. "
            "A new gap must be fixed, or filed against #15276 with its own TRACKED_GAP "
            "entry and this ceiling raised in the same change -- it may not just grow "
            "silently."
        )
    if live_count < ceiling:
        return (
            f"TRACKED_GAP count is {live_count}, under its recorded ceiling of {ceiling}. "
            f"Lower TRACKED_GAP_CEILING to {live_count} in this file -- the ratchet only "
            "turns down, and an unlowered ceiling re-licenses the entries just removed."
        )
    return None


# ---------------------------------------------------------------------------
# Non-vacuity: every test below reasons over ALLOWLIST's contents.
# ---------------------------------------------------------------------------


def test_the_allowlist_import_is_not_empty() -> None:
    assert ALLOWLIST, "ALLOWLIST imported empty -- every ratchet assertion below would be vacuous"


# ---------------------------------------------------------------------------
# The ratchet turns both ways, on the real ALLOWLIST
# ---------------------------------------------------------------------------


def test_the_live_tracked_gap_count_is_at_its_recorded_ceiling() -> None:
    """The real ALLOWLIST today: neither over nor under TRACKED_GAP_CEILING."""
    live = _tracked_gap_count(ALLOWLIST)
    verdict = _tracked_gap_verdict(live, TRACKED_GAP_CEILING)
    assert verdict is None, verdict


def test_an_added_tracked_gap_entry_is_rejected() -> None:
    """Mutation: over. A new TRACKED_GAP entry with no ceiling bump must fail."""
    mutated = dict(ALLOWLIST)
    mutated[("autobot-backend/new_consumer.py", "new_api_key")] = f"{_TRACKED} #99999: a brand-new, unrecorded gap"
    verdict = _tracked_gap_verdict(_tracked_gap_count(mutated), TRACKED_GAP_CEILING)
    assert verdict is not None and "over its recorded ceiling" in verdict, verdict


def test_a_removed_tracked_gap_entry_with_a_stale_ceiling_is_rejected() -> None:
    """Mutation: under. Paying down debt without lowering the ceiling must fail."""
    mutated = dict(ALLOWLIST)
    first_tracked_key = next(key for key, reason in ALLOWLIST.items() if reason.startswith(_TRACKED))
    del mutated[first_tracked_key]
    verdict = _tracked_gap_verdict(_tracked_gap_count(mutated), TRACKED_GAP_CEILING)
    assert verdict is not None and "under its recorded ceiling" in verdict, verdict


# ---------------------------------------------------------------------------
# The ratchet is scoped to TRACKED_GAP -- AUTH_BOOTSTRAP/NOT_A_READ are exempt
# ---------------------------------------------------------------------------


def test_auth_bootstrap_growth_does_not_move_the_tracked_gap_count() -> None:
    """Adding an AUTH_BOOTSTRAP entry must not change the count this ratchet tracks.

    Forcing that class to shrink too would eventually pressure someone into
    mis-classifying a genuinely irreducible credential just to keep this guard green.
    """
    mutated = dict(ALLOWLIST)
    mutated[("autobot-backend/new_bootstrap.py", "some_password")] = f"{_AUTH_BOOTSTRAP}: irreducible, not a gap"
    assert _tracked_gap_count(mutated) == _tracked_gap_count(ALLOWLIST)


# ---------------------------------------------------------------------------
# The TRACKED_GAP marker's format, not its issue's existence or open-state
# ---------------------------------------------------------------------------


def test_every_real_tracked_gap_marker_matches_the_required_format() -> None:
    malformed = _malformed_tracked_gap_markers(ALLOWLIST)
    assert not malformed, f"TRACKED_GAP entries with a malformed marker: {malformed}"


def test_a_malformed_or_absent_issue_number_is_rejected() -> None:
    """Mutation: three ways a marker can be silently unfixable back to an issue.

    None of these fabricates a real issue number -- they exercise the *format* check
    only, which is all this guard can do offline (see the module docstring).
    """
    for label, bad_reason in (
        ("no issue number", f"{_TRACKED}: a gap with no number at all"),
        ("non-digit issue number", f"{_TRACKED} #abc: a gap with a non-numeric marker"),
        ("missing separator", f"{_TRACKED} #12345 a gap missing its colon"),
    ):
        mutated = {("autobot-backend/x.py", "x_api_key"): bad_reason}
        malformed = _malformed_tracked_gap_markers(mutated)
        assert malformed, f"{label!r} was not flagged: {bad_reason!r}"
