# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The MCP add route refuses a non-admin's platform-wide request with 403 (#16663 AC1).

Silently stripping the request and reporting success told the caller it had worked. A
non-admin asking for SYSTEM or PUBLIC visibility, or a general/autobot access level (the same
reach), now gets 403. An admin gets the fact stored as asked. Anyone else keeps their metadata,
minus the owner fields.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


async def _add(metadata: dict, role: str):
    from api import knowledge_mcp as mod

    kb = MagicMock()
    kb.add_document = AsyncMock(return_value="doc-1")
    request = SimpleNamespace(content="c", metadata=metadata, source="mcp")
    with patch.object(mod, "get_knowledge_base", MagicMock(return_value=kb)):
        response = await mod.mcp_add_to_knowledge_base(request, current_user={"user_id": "u1", "role": role})
    return response, kb


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata", [{"visibility": "public"}, {"visibility": "system"}, {"access_level": "general"}])
async def test_a_non_admin_asking_for_platform_wide_reach_gets_403(metadata):
    from api import knowledge_mcp as mod

    kb = MagicMock()
    kb.add_document = AsyncMock()
    request = SimpleNamespace(content="c", metadata=metadata, source="mcp")
    with patch.object(mod, "get_knowledge_base", MagicMock(return_value=kb)):
        with pytest.raises(HTTPException) as err:
            await mod.mcp_add_to_knowledge_base(request, current_user={"user_id": "u1", "role": "user"})

    assert err.value.status_code == 403
    kb.add_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_admin_stores_a_system_fact_as_asked():
    response, kb = await _add({"visibility": "system"}, "admin")

    assert response["success"] is True
    assert kb.add_document.await_args.kwargs["metadata"]["visibility"] == "system"


@pytest.mark.asyncio
async def test_a_non_admin_keeps_their_metadata_but_not_an_owner_field():
    response, kb = await _add({"visibility": "private", "owner_id": "someone-else", "title": "t"}, "user")

    assert response["success"] is True
    assert kb.add_document.await_args.kwargs["metadata"] == {"visibility": "private", "title": "t"}
