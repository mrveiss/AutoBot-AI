# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A filter on a canonical identity action finds rows stored under the old spelling (#19035)."""

from services.audit.taxonomy import AuditAction, AuditFilter


def _row(action: str) -> dict:
    return {"category": "security", "action": action, "occurred_at": 1.0, "metadata": {}}


def test_canonical_filter_matches_legacy_stored_rows() -> None:
    assert AuditFilter(action=AuditAction.AUTH_LOCKOUT.value).matches(_row("account_locked"))
    assert AuditFilter(action="auth.lockout").matches(_row("auth.lockout"))
    assert AuditFilter(actions=frozenset({"access.denied"})).matches(_row("permission_denied"))


def test_filter_does_not_match_a_different_action() -> None:
    assert not AuditFilter(action="auth.lockout").matches(_row("account_unlocked"))
    assert not AuditFilter(action="auth.lockout").matches(_row("auth.login"))
