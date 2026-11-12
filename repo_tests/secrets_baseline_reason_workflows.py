# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Baseline reasons for the ``.github/workflows`` gate files (#18208).

Split out of ``secrets_baseline_reason_entries.py``, which reached its 600-line
ceiling. #18208 moved the migration and security checks into ``_gate-*.yml``
workflows verbatim; their entries carry the same hashes that are frozen legacy
entries under the old file names, so each gets its own specific reason here.

Imports nothing, so ``secrets_baseline_reason_entries`` can merge it without a cycle.
"""

from __future__ import annotations

from typing import Tuple

_MIGTEST_HASH = "73f8b006461899b9ce28347f03f96db78b7abff8"  # pragma: allowlist secret

WORKFLOW_REASONS: dict[Tuple[str, str, str], str] = {
    (".github/workflows/_gate-migration.yml", kind, _MIGTEST_HASH): (
        "the throwaway `migtest` user/password of the migration gate's CI-only postgres service "
        "container and the admin database URL built from them, moved verbatim from "
        "migration-gate.yml (frozen legacy entry, same hash) when #18208 made it a gate workflow. "
        "Plain SHA1 of `migtest` reproduces this hash."
    )
    for kind in ("Basic Auth Credentials", "Secret Keyword")
}
WORKFLOW_REASONS[
    (
        ".github/workflows/_gate-security.yml",
        "Secret Keyword",
        "bb97e2eb9656dd63351c52cd1d35ff3a38383690",  # pragma: allowlist secret
    )
] = (
    "the `run:` block of the detect-secrets step (it names secrets.baseline paths), moved verbatim "
    "from security.yml, where the same hash is a frozen legacy entry, when #18208 made it a gate "
    "workflow; no credential is present in that step."
)
