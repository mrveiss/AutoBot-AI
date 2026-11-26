# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A 400 for a bad role or approval category names the valid choices (#17601)."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import api.chat as chat

SID = "6a1d0b6f-2c3d-4e4f-9a01-1b2c3d4e5f60"


@pytest.fixture(autouse=True)
def _owned(monkeypatch):
    monkeypatch.setattr(chat, "validate_chat_ownership", AsyncMock(return_value={"valid": True}))


@pytest.mark.asyncio
async def test_unknown_approval_category_400_names_the_valid_categories():
    with pytest.raises(HTTPException) as caught:
        await chat.set_session_approval_categories(SID, categories=["no_such_category"], current_user={}, request=None)
    assert caught.value.status_code == 400
    assert "no_such_category" in caught.value.detail
    assert "valid:" in caught.value.detail


@pytest.mark.asyncio
async def test_unknown_role_400_names_the_valid_roles():
    with pytest.raises(HTTPException) as caught:
        await chat.set_session_role(SID, role="no_such_role", current_user={}, request=None)
    assert caught.value.status_code == 400
    assert "no_such_role" in caught.value.detail
    assert "valid:" in caught.value.detail
