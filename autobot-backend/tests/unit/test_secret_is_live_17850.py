# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`Secret.is_live` is the one "this secret row is active" rule (#17850); expiry stays separate."""

from datetime import timedelta

import pytest

from autobot_shared.time_utils import now_utc
from models.secret import Secret


@pytest.mark.parametrize(("active", "expected"), [(True, True), (False, False), (None, False)])
def test_is_live_follows_is_active(active, expected) -> None:
    assert Secret(is_active=active).is_live is expected


def test_is_live_ignores_expiry() -> None:
    row = Secret(is_active=True, expires_at=now_utc() - timedelta(days=1))
    assert row.is_expired and row.is_live
