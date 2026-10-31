# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Knowledge audit views read and write the canonical trail, once (#17225 D2)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from services.audit import knowledge_view
from services.audit.knowledge_view import KnowledgeAuditLog, to_knowledge_view
from services.audit.taxonomy import AuditCategory, AuditEventType


def _canonical(action: str, actor: str, fact: str | None = None, org: str | None = None, at: float = 0.0) -> dict:
    meta = {"note": "n"}
    if org:
        meta["organization_id"] = org
    return {
        "id": f"id-{action}-{actor}",
        "category": "knowledge",
        "action": action,
        "actor_id": actor,
        "resource_type": "fact" if fact else "knowledge",
        "resource_id": fact or org,
        "metadata": meta,
        "occurred_at": at,
        "ip_address": None,
    }


def test_the_view_keeps_the_shape_the_api_returned() -> None:
    view = to_knowledge_view(_canonical("view", "u1", fact="f1", org="o1", at=0.0))
    assert view == {
        "id": "id-view-u1",
        "type": "view",
        "user_id": "u1",
        "fact_id": "f1",
        "organization_id": "o1",
        "details": {"note": "n"},
        "ip_address": None,
        "timestamp": datetime.fromtimestamp(0, tz=timezone.utc).isoformat(),
    }


@pytest.mark.asyncio
async def test_log_event_records_once_through_the_service() -> None:
    """The old subclass wrote the knowledge zsets AND the unified key; now there is one write."""
    emit = AsyncMock()
    with patch.object(knowledge_view, "emit_knowledge", new=emit):
        await KnowledgeAuditLog().log_event(AuditEventType.SHARE, "u1", fact_id="f1", organization_id="o1")
    emit.assert_awaited_once()
    args, kwargs = emit.call_args
    assert args == (AuditEventType.SHARE, "u1")
    assert kwargs["resource_type"] == "fact" and kwargs["resource_id"] == "f1"
    assert kwargs["metadata"] == {"organization_id": "o1"}


@pytest.mark.asyncio
async def test_fact_log_asks_for_knowledge_events_on_that_fact() -> None:
    query = AsyncMock(return_value=[])
    with patch.object(knowledge_view, "query_filtered", new=query):
        await KnowledgeAuditLog().get_fact_access_log("f1", limit=7)
    flt = query.call_args.args[0]
    assert (flt.category, flt.resource_type, flt.resource_id) == (AuditCategory.KNOWLEDGE, "fact", "f1")
    assert query.call_args.kwargs["limit"] == 7


@pytest.mark.asyncio
async def test_permission_changes_need_a_fact_or_a_user() -> None:
    query = AsyncMock(return_value=[])
    with patch.object(knowledge_view, "query_filtered", new=query):
        assert await KnowledgeAuditLog().get_permission_changes() == []
    query.assert_not_called()


@pytest.mark.asyncio
async def test_compliance_report_counts_one_organisations_window() -> None:
    events = [
        _canonical("share", "u1", fact="f1", org="o1"),
        _canonical("update", "u1", fact="f1", org="o1"),
        _canonical("update", "u2", fact="f2", org="o1"),
    ]
    query = AsyncMock(return_value=events)
    start, end = datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 2, 1, tzinfo=timezone.utc)
    with patch.object(knowledge_view, "query_filtered", new=query):
        report = await KnowledgeAuditLog().generate_compliance_report("o1", start, end)
    flt = query.call_args.args[0]
    assert flt.metadata == (("organization_id", "o1"),)
    assert (flt.from_ts, flt.to_ts) == (start.timestamp(), end.timestamp())
    assert report["total_events"] == 3 and report["unique_users"] == 2
    assert report["facts_modified"] == 2 and report["permission_changes"] == 1
    assert report["most_active_users"][0] == {"user_id": "u1", "count": 2}
