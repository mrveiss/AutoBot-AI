# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Route files not yet on the function-scoped session dependency, each held back by an open PR (#21332).

Shrink-only (docs/developer/RATCHET_BASELINES.md): `test_commit_before_answer_guard_21332.py` compares this table with
the base commit and with the files the guard measures as violating, so an entry can only be removed. The value names
the open PR that edits the file. The third batch of #21332 moved the last five files; the table is empty and stays so.

Boundary: only `autobot-backend/llc/api` route modules are listed. A route outside llc is not in this guard's scope.
"""

from __future__ import annotations

COMMIT_BEFORE_ANSWER_BASELINE: dict[str, str] = {}
