# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Server-side work-item binding and its tenant scope (#13704, #13687).

#13696 removed the L4 wiring rather than ship it, because the only carrier for
`work_item_id` was a raw client JSON bag and neither LLC lookup filtered on
`company_id`. These pin both halves of the fix: the value is server-written, and
the lookups are company-scoped even if a binding is stale or forged.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_workflow.session_work_item import SessionWorkItemService, apply_work_item

ALICE_CO = "11111111-1111-1111-1111-111111111111"
BOB_CO = "22222222-2222-2222-2222-222222222222"
WORK_ITEM = "33333333-3333-3333-3333-333333333333"


class TestClientSuppliedValueIsNeverTrusted:
    def test_a_server_binding_overrides_a_client_value(self):
        context = {"work_item_id": "attacker-chosen", "other": "kept"}

        result = apply_work_item(context, WORK_ITEM)

        assert result["work_item_id"] == WORK_ITEM
        assert result["other"] == "kept"

    def test_an_unbound_session_has_the_client_value_stripped(self):
        """The core of #13687: an unbound session must not be able to name one.

        Leaving the client's value in place would preserve exactly the
        cross-tenant read this issue exists to remove.
        """
        context = {"work_item_id": "attacker-chosen", "other": "kept"}

        result = apply_work_item(context, None)

        assert "work_item_id" not in result
        assert result["other"] == "kept"

    def test_absent_context_stays_absent(self):
        assert apply_work_item(None, None) is None


class TestBindingCarriesItsVerifiedCompany:
    @pytest.mark.asyncio
    async def test_the_company_is_stored_with_the_binding(self):
        """The company cannot be read back later from the session or context.

        `session.metadata["company_id"]` is assigned from the client bag at
        `chat_workflow/manager.py:3331`, so persisting the company the endpoint
        actually authorised is what makes the tenant scope trustworthy.
        """
        svc = SessionWorkItemService()
        redis = MagicMock()
        redis.set = AsyncMock()

        with patch.object(SessionWorkItemService, "_get_redis", new_callable=AsyncMock, return_value=redis):
            await svc.set_work_item("s-1", WORK_ITEM, ALICE_CO)

        stored = json.loads(redis.set.await_args.args[1])
        assert stored == {"work_item_id": WORK_ITEM, "company_id": ALICE_CO}

    @pytest.mark.asyncio
    async def test_a_binding_without_a_company_is_rejected(self):
        svc = SessionWorkItemService()
        with pytest.raises(ValueError, match="company_id is required"):
            await svc.set_work_item("s-1", WORK_ITEM, "")

    @pytest.mark.asyncio
    async def test_get_binding_returns_both_values(self):
        svc = SessionWorkItemService()
        redis = MagicMock()
        redis.get = AsyncMock(return_value=json.dumps({"work_item_id": WORK_ITEM, "company_id": ALICE_CO}).encode())

        with patch.object(SessionWorkItemService, "_get_redis", new_callable=AsyncMock, return_value=redis):
            assert await svc.get_binding("s-1") == (WORK_ITEM, ALICE_CO)

    @pytest.mark.asyncio
    async def test_a_redis_failure_leaves_l4_silent_not_broken(self):
        svc = SessionWorkItemService()
        with patch.object(SessionWorkItemService, "_get_redis", side_effect=RuntimeError("redis down")):
            assert await svc.get_binding("s-1") == (None, None)


class TestGoalAncestryIsCompanyScoped:
    @pytest.mark.asyncio
    async def test_no_binding_issues_no_query(self):
        """A turn with no binding must cost no DB round-trip."""
        from chat_workflow.tiered_context_sources import resolve_goal_ancestry

        factory = MagicMock()
        with patch(
            "chat_workflow.session_work_item.SessionWorkItemService.get_binding",
            new_callable=AsyncMock,
            return_value=(None, None),
        ):
            with patch("user_management.database.get_async_session_factory", factory):
                assert await resolve_goal_ancestry("s-1") is None

        factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_malformed_work_item_id_is_not_a_per_turn_warning(self):
        from chat_workflow.tiered_context_sources import resolve_goal_ancestry

        with patch(
            "chat_workflow.session_work_item.SessionWorkItemService.get_binding",
            new_callable=AsyncMock,
            return_value=("not-a-uuid", ALICE_CO),
        ):
            with patch("chat_workflow.tiered_context_sources.logger") as log:
                assert await resolve_goal_ancestry("s-1") is None

        assert not log.warning.called, "a client-shaped id is a debug, not a warning"

    @pytest.mark.asyncio
    async def test_the_company_from_the_binding_scopes_both_lookups(self):
        """The scope must reach the work-item fetch AND the goal walk."""
        from chat_workflow.tiered_context_sources import resolve_goal_ancestry

        work_item = MagicMock()
        work_item.goal_id = "44444444-4444-4444-4444-444444444444"
        wi_svc, goal_svc = MagicMock(), MagicMock()
        wi_svc.get = AsyncMock(return_value=work_item)
        goal_svc.get_goal_ancestry_for_work_item = AsyncMock(return_value=[{"title": "Ship", "level": "vision"}])

        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
        session_cm.__aexit__ = AsyncMock(return_value=False)

        modules = {
            "llc.services.goal": MagicMock(GoalService=MagicMock(return_value=goal_svc)),
            "llc.services.work_item_service": MagicMock(WorkItemService=MagicMock(return_value=wi_svc)),
            "user_management.database": MagicMock(
                get_async_session_factory=MagicMock(return_value=MagicMock(return_value=session_cm))
            ),
        }
        with patch.dict("sys.modules", modules):
            with patch(
                "chat_workflow.session_work_item.SessionWorkItemService.get_binding",
                new_callable=AsyncMock,
                return_value=(WORK_ITEM, ALICE_CO),
            ):
                result = await resolve_goal_ancestry("s-1")

        assert result == [{"title": "Ship", "level": "vision"}]
        assert wi_svc.get.await_args.kwargs["company_id"] == ALICE_CO
        assert goal_svc.get_goal_ancestry_for_work_item.await_args.kwargs["company_id"] == ALICE_CO
