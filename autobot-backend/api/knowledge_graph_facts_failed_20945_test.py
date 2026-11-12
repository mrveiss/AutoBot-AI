# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A fact read that raises is a failed facts section, not an empty successful page (#20945)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.knowledge_search_aggregator import get_multi_source_graph
from api.schemas_knowledge_graph import GraphRequest
from tests.fixtures.graph_buckets_fakes_20945 import ALICE, TENANT_A, ListingKB, client_with


@pytest.mark.asyncio
async def test_a_raising_continuation_read_marks_the_facts_section_failed():
    kb = ListingKB([], await client_with({}))
    user = {"user_id": ALICE, "role": "user", "org_id": TENANT_A, "auth_method": "jwt"}
    body = GraphRequest(include_categories=False, include_relations=False, cursor="500:0")
    with (
        patch("api.knowledge_search_aggregator.get_or_create_knowledge_base", new=AsyncMock(return_value=kb)),
        patch("api.knowledge_search_aggregator.visible_facts_page", new=AsyncMock(side_effect=RuntimeError("secret"))),
        patch("services.audit_logger.audit_log", new=AsyncMock(return_value=True)),
    ):
        result = await get_multi_source_graph(MagicMock(), body, user)
    facts = next(s for s in result["stats"]["sections"] if s["key"] == "facts")
    assert facts["failed"] is True and facts["total"] is None and facts["limited"] is True
    assert facts["cursor"] == "500:0", "the requested cursor is kept so a retry reads the same page"
    assert "secret" not in repr(result), "exception text never reaches the caller"
