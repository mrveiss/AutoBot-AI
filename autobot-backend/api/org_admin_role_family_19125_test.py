# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19125: literal ``"admin"`` role checks admit the whole admin family (superadmin included)."""

from unittest.mock import AsyncMock

import pytest

from api.chat_presets import _is_org_admin
from security.session_ownership import SessionOwnershipValidator


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("admin", True),
        ("superadmin", True),
        ("SuperAdmin", True),
        ("org_admin", True),
        ("owner", True),
        ("operator", False),
        ("user", False),
        ("", False),
    ],
)
def test_chat_presets_org_admin_covers_the_admin_family(role, expected):
    assert _is_org_admin({"role": role}) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "expected"),
    [("admin", True), ("superadmin", True), ("org_admin", True), ("user", False), ("operator", False)],
)
async def test_session_ownership_org_admin_gate_covers_the_admin_family(role, expected):
    validator = SessionOwnershipValidator.__new__(SessionOwnershipValidator)
    validator.get_session_context = AsyncMock(return_value={"org_id": "org-1"})
    assert await validator._is_org_admin_access({"role": role, "org_id": "org-1"}, "s") is expected
