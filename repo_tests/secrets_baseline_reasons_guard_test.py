# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every ``.secrets.baseline`` entry has a tracked reason (#16299 AC5).

The baseline is an allowlist: every entry in it is something detect-secrets
flagged and the repo decided not to block on. An entry with no recorded
reason is an *accident* wearing the shape of a *decision*
(``docs/developer/RATCHET_BASELINES.md`` rule 1) -- which is exactly how the
5 guessable defaults #16299 was filed for sat unexamined in a 1,360-entry
baseline nobody was reading end to end.

Comprehensively reasoning all 1,360 entries by hand is not this guard's job
(see ``repo_tests/secrets_baseline_reasons.py``'s module docstring for why,
and #17034 for the follow-up that will shrink the legacy set). This guard
enforces the **declared boundary** the owner ruled instead:

- ``SPECIFIC_REASONS``' keys are the individually-reviewed defaults -- must
  be present, non-empty, and NOT the generic legacy sentinel (a specific
  reason that degrades to the generic one is not a specific reason).
- ``secrets_baseline_legacy_keys.json``'s keys are the pre-existing, disclosed
  legacy bucket -- may carry ``LEGACY_REASON`` and nothing else.
- Every OTHER current baseline entry -- one that is in neither set -- is the
  actual boundary violation this guard exists to catch: a new, unreasoned
  entry that was never looked at, or one trying to borrow the legacy label
  without being in the frozen snapshot.
"""

from __future__ import annotations

import json

from repo_tests._paths import repo_root
from repo_tests.secrets_baseline_reasons import (
    FROZEN_LEGACY_KEYS_SHA256,
    LEGACY_REASON,
    SPECIFIC_REASONS,
    BaselineKey,
    content_hash,
    load_legacy_keys,
)

_REPO_ROOT = repo_root()
_BASELINE = _REPO_ROOT / ".secrets.baseline"


def _baseline_keys() -> set[BaselineKey]:
    baseline = json.loads(_BASELINE.read_text(encoding="utf-8"))
    results = baseline.get("results")
    assert isinstance(results, dict) and results, (
        f"{_BASELINE} holds no results -- an empty or unparsed baseline proves nothing; "
        "this guard needs a real population to check"
    )
    return {(path, entry["type"], entry["hashed_secret"]) for path, entries in results.items() for entry in entries}


def _offenders(baseline_keys: set[BaselineKey], legacy_keys: frozenset[BaselineKey]) -> list[str]:
    """Baseline keys with no valid reason: neither a real SPECIFIC_REASONS entry
    nor a member of the frozen legacy snapshot."""
    reasoned = set(SPECIFIC_REASONS) | legacy_keys
    return [f"{path} type={type_} hashed_secret={h}" for (path, type_, h) in sorted(baseline_keys - reasoned)]


def test_every_baseline_entry_has_a_tracked_reason() -> None:
    baseline_keys = _baseline_keys()
    legacy_keys = load_legacy_keys()
    offenders = _offenders(baseline_keys, legacy_keys)
    assert not offenders, (
        "these .secrets.baseline entries have no tracked reason (#16299 AC5) -- add a real, "
        "specific reason to SPECIFIC_REASONS in repo_tests/secrets_baseline_reasons.py "
        "(never LEGACY_REASON for a new entry -- that label is frozen to the entries present "
        "when it was introduced):\n  " + "\n  ".join(offenders)
    )


def test_specific_reasons_are_real_not_the_generic_legacy_label() -> None:
    """A SPECIFIC_REASONS entry that equals LEGACY_REASON is not a specific reason --
    it means someone downgraded an individually-reviewed entry back to the generic
    bucket without deleting it from SPECIFIC_REASONS."""
    degraded = [key for key, reason in SPECIFIC_REASONS.items() if not reason.strip() or reason == LEGACY_REASON]
    assert not degraded, f"SPECIFIC_REASONS entries with no real, specific reason: {degraded}"


def test_specific_reasons_actually_match_current_baseline_entries() -> None:
    """A known positive (rule 6): every SPECIFIC_REASONS key must exist in the
    real baseline right now, or the reason is reasoning about nothing."""
    baseline_keys = _baseline_keys()
    stale = sorted(set(SPECIFIC_REASONS) - baseline_keys)
    assert not stale, (
        f"SPECIFIC_REASONS names {len(stale)} key(s) not present in .secrets.baseline -- "
        f"stale entries that must be removed from SPECIFIC_REASONS: {stale}"
    )


def test_legacy_keys_match_the_frozen_snapshot_exactly() -> None:
    """A count ceiling alone would let someone swap a legitimate legacy entry for a
    fabricated one while keeping the total unchanged -- silently laundering a new,
    unreviewed entry under the legacy label without ever growing the count. Pinning
    the exact content (a hash over the canonicalised set) catches an add, a remove,
    OR a swap; #17034 never needs to touch this file at all (see
    repo_tests/secrets_baseline_reasons.py's module docstring for why), so this
    hash should never need updating again."""
    legacy_keys = load_legacy_keys()
    actual_hash = content_hash(legacy_keys)
    assert actual_hash == FROZEN_LEGACY_KEYS_SHA256, (
        f"secrets_baseline_legacy_keys.json's content no longer matches the hash frozen at "
        f"#16299's introduction ({len(legacy_keys)} entries, hash {actual_hash}) -- this file "
        "is not meant to be edited; a new baseline entry must get a real reason in "
        "SPECIFIC_REASONS instead of touching this snapshot"
    )


def test_negative_control_a_new_unreasoned_entry_is_caught() -> None:
    """Proves the sweep can actually fail (rule 6's known positive, from the other
    direction): a synthetic entry in neither set must be flagged."""
    legacy_keys = load_legacy_keys()
    synthetic_key: BaselineKey = ("some/new/file.py", "Secret Keyword", "0" * 40)
    assert synthetic_key not in SPECIFIC_REASONS
    assert synthetic_key not in legacy_keys
    offenders = _offenders({synthetic_key}, legacy_keys)
    assert offenders == ["some/new/file.py type=Secret Keyword hashed_secret=" + "0" * 40]
