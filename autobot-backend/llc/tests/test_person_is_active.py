# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who may still be given work, decided once (GH#13956).

The members picker and the org chart both ask this, and the issue is explicit
that they must not diverge. Neither computes it inline, so this is the only
place the rule exists — and the only place it needs testing.

The rule is deliberately not a filter. A person who has left keeps the work
items assigned to them (reassignment is always explicit) and the role they
held (#14221), so a surface that drops them cannot explain who those belong to.
"""

from __future__ import annotations

from datetime import datetime, timezone

from llc.api.companies import _person_is_active


def test_an_active_user_may_be_given_work() -> None:
    assert _person_is_active(True, None) is True


def test_a_deactivated_user_may_not() -> None:
    assert _person_is_active(False, None) is False


def test_a_soft_deleted_user_may_not_even_while_still_flagged_active() -> None:
    """`deleted_at` wins over `is_active`.

    A soft delete does not necessarily clear the flag, so reading only
    `is_active` would leave deleted users assignable — the exact gap reported.
    """
    assert _person_is_active(True, datetime(2026, 1, 1, tzinfo=timezone.utc)) is False


def test_an_unknown_user_may_not() -> None:
    """A membership whose user row is missing (outer-join miss) resolves False.

    Nothing is known about them, and "unknown" must never read as "available".
    """
    assert _person_is_active(None, None) is False
