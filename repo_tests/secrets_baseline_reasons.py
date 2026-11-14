# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reasons for ``repo_tests/secrets_baseline_reasons_guard_test.py`` (#16299 AC5).

A ``.secrets.baseline`` entry is a (filename, type, hashed_secret) triple --
stable across a line-only move (#16353: the baseline carries no line number).
Every entry the baseline holds needs a tracked reason; an exemption you
cannot read is an accident, not a decision
(``docs/developer/RATCHET_BASELINES.md`` rule 1).

The baseline was sampled at AC5's introduction (1,360 entries; 91% "Secret
Keyword", the overwhelming majority test fixtures, CI-only credentials, and
demo values already marked inline `# noqa`/`# nosec` -- not real guessable
production defaults) and found too large for a genuine per-entry manual
review in one slice. The owner ruled a **declared boundary**, not a
comprehensive one:

- The 5 entries matching #16299's own named guessable defaults get a real,
  specific, individually-reviewed reason (``SPECIFIC_REASONS`` below) --
  cross-checked by independently re-hashing each literal (plain SHA1, no
  salt -- matches detect-secrets' "Secret Keyword" hasher empirically) and
  confirming it against the baseline's own ``hashed_secret``, not asserted
  from the filename alone.
- Every other entry present in the baseline at this guard's introduction is
  in ``secrets_baseline_legacy_keys.json`` (kept out of this ``.py`` file --
  1,355 entries would blow the 600-line file-size ratchet), one disclosed,
  generic reason (``LEGACY_REASON``) -- not silently allowed, explicitly
  deferred to #17034 (the full-audit follow-up, v0.9.0).

The legacy set is frozen, not derived from the live baseline at test time: a
baseline entry NOT in that JSON file may not carry ``LEGACY_REASON`` -- that
is the guard's actual boundary enforcement (rule 2: a test must fail when the
boundary moves). A new entry added after this file was written must get its
own real reason in ``SPECIFIC_REASONS``, or the guard fails; it cannot
silently borrow the legacy label.

A count ceiling alone does not enforce this: swapping one legitimate legacy
entry out of the JSON file for a fabricated one, keeping the total at 1,355,
would pass a "does not grow" check while silently laundering a new,
unreviewed entry under the legacy label. ``FROZEN_LEGACY_KEYS_SHA256`` pins
the exact CONTENT (a hash over the canonicalised set, not the count), so ANY
edit -- add, remove, or swap -- must also update this constant, which is a
visible, deliberate act in the diff. #17034 does not need to touch this file
at all: a legacy entry it individually reviews moves to ``SPECIFIC_REASONS``
instead (the guard's membership check is an OR of both sets, so an entry
present in both is harmless) -- this file is permanently frozen from here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

#: sha256 over the canonicalised (sorted, deterministically JSON-dumped) content
#: of secrets_baseline_legacy_keys.json as frozen at #16299's introduction --
#: pins the exact SET, not just its size (see the module docstring for why a
#: count alone is not enough). Computed once; never re-derive it FROM the live
#: file to "fix" a mismatch -- a mismatch means the file changed and that
#: change needs its own review, the same as any other ratchet-baseline edit.
#: Re-pinned once, by #20895, for a shrink-only edit: 19 entries over 6 paths absent from the tree were
#: removed; the digest is the old one (reproduced first) recomputed over the remaining keys.
FROZEN_LEGACY_KEYS_SHA256 = (
    "898bc7dbf08652ee9ee701dc41b88d54843ed32db8c0844ba94124d5b92311fa"  # pragma: allowlist secret
)


def content_hash(keys: frozenset[BaselineKey]) -> str:
    """The same canonicalisation used to compute FROZEN_LEGACY_KEYS_SHA256."""
    canonical = json.dumps(sorted(keys), sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


#: The sentinel legacy-boundary reason. A baseline key may carry this ONLY
#: when it is also a member of load_legacy_keys() below -- enforced by the
#: guard, not by convention.
LEGACY_REASON = (
    "legacy entry predating #16299's baseline-reasons guard -- unreviewed, pending the full-audit follow-up (#17034)"
)

#: The reason table lives in its own module (#17134) -- it is the part that grows.
from repo_tests.secrets_baseline_reason_entries import SPECIFIC_REASONS, BaselineKey  # noqa: E402,F401

_LEGACY_KEYS_PATH = Path(__file__).with_name("secrets_baseline_legacy_keys.json")


def load_legacy_keys() -> frozenset[BaselineKey]:
    """The frozen (filename, type, hashed_secret) triples exempted under LEGACY_REASON.

    Loaded from JSON, not inlined, so this module stays well under the
    600-line file-size ratchet -- the set has 1,336 entries (1,355 before #20895 pruned the dead paths).
    """
    with _LEGACY_KEYS_PATH.open(encoding="utf-8") as fh:
        return frozenset(tuple(entry) for entry in json.load(fh))
