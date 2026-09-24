# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The agent router addresses its events to their owner (#17354).

`_publish_event_safe` used to hardcode `"global"`, which
`api/live_events.py:_authorize_channel` admits every authenticated client to,
while publishing the operator's goal text, the shell command they ran and its
stdout. No caller could fix that, because the channel was not theirs to pass.
"""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.agent_events import BROADCAST_CHANNEL, owner_channel, publish_event_safe, publish_goal_events


class TestOwnerChannel:
    def test_the_user_id_names_the_channel(self):
        assert owner_channel({"user_id": "u1"}) == "agent:u1"

    def test_the_username_is_the_fallback(self):
        """`_authorize_channel` accepts either, so either may address the event."""
        assert owner_channel({"username": "alice"}) == "agent:alice"

    @pytest.mark.parametrize("payload", [None, {}, {"user_id": ""}, {"user_id": None}])
    def test_an_unidentifiable_caller_gets_no_channel(self, payload):
        """`None` is not "fall back to broadcast" -- see the drop test below."""
        assert owner_channel(payload) is None


class TestPublishEventSafe:
    @staticmethod
    def _bus() -> MagicMock:
        bus = MagicMock()
        bus.publish = AsyncMock()
        return bus

    @pytest.mark.asyncio
    async def test_it_publishes_on_the_channel_it_is_given(self):
        """Positive control: without it, the drop test below proves nothing."""
        bus = self._bus()
        with patch("api.agent_events.get_event_bus", return_value=bus):
            await publish_event_safe("agent:u1", "goal_received", {"goal": "ship it"})

        assert bus.publish.await_args.args[0] == "agent:u1"
        assert bus.publish.await_args.args[1] == "goal_received"

    @pytest.mark.asyncio
    async def test_no_channel_drops_the_event_rather_than_broadcasting_it(self):
        bus = self._bus()
        with patch("api.agent_events.get_event_bus", return_value=bus):
            await publish_event_safe(None, "goal_received", {"goal": "ship it"})

        bus.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_publish_failure_is_not_fatal_to_the_caller(self):
        bus = self._bus()
        bus.publish.side_effect = RuntimeError("bus down")
        with patch("api.agent_events.get_event_bus", return_value=bus):
            await publish_event_safe("agent:u1", "goal_received", {"goal": "ship it"})

    @pytest.mark.asyncio
    async def test_both_goal_events_carry_the_callers_channel(self):
        """The goal text is the operator's own -- #17354's original instance."""
        bus = self._bus()
        with patch("api.agent_events.get_event_bus", return_value=bus):
            await publish_goal_events("ship it", False, "agent:u1")

        assert [call.args[0] for call in bus.publish.await_args_list] == ["agent:u1", "agent:u1"]
        assert [call.args[1] for call in bus.publish.await_args_list] == ["user_message", "goal_received"]


def test_the_broadcast_constant_is_still_the_broadcast_channel():
    """`agent_paused`/`agent_resumed` are node-wide, and this names that choice.

    If this ever stops being `"global"`, the guard in
    `repo_tests/global_channel_carries_no_tenant_payload_17354_test.py` that
    follows the constant is watching the wrong name.
    """
    assert BROADCAST_CHANNEL == "global"


class TestTheOwnerChannelCannotNameSomeoneElse:
    """`agent:{id}` is admitted on EITHER field, so the two must never collide.

    `api/live_events.py:_authorize_channel` answers the `agent:` prefix with
    `claimed_id in (user_id, username)` -- either field, no tag saying which
    namespace the claimed id came from. `owner_channel` builds the channel the
    same way, `user_id` first and `username` as the fallback, so the two ends
    agree on the spelling. What keeps that safe is not the check: it is that no
    username can equal another account's user id.

    That safety rests on two facts in two files neither of which knows about the
    other -- user ids are UUIDs, usernames exclude the hyphen -- so it is a
    coincidence until something asserts it. A review of #17363 raised the
    collision as a possible cross-tenant read; it is not one today, and these
    are the two facts that make it so. If either moves (numeric user ids, or a
    username pattern that admits `-`), this fails instead of a tenant reading
    another tenant's goal text, shell commands and stdout.
    """

    #: The model's own declaration, asserted from source rather than through the
    #: ORM: `UserCore` has no `__table__` at import time, and a guard that needs
    #: a mapped class configured is a guard that skips when the mapping is lazy.
    _MODEL = Path(__file__).resolve().parents[2] / "autobot_shared" / "user_management" / "models" / "user.py"

    def test_a_user_id_is_a_uuid(self):
        source = self._MODEL.read_text(encoding="utf-8")

        assert "id: Mapped[uuid.UUID]" in source, (
            "the user primary key is no longer declared as a UUID; if it is now numeric or "
            "free text, `agent:{id}` authorization on either field can collide (#17363)"
        )

    def test_a_uuid_can_never_be_a_username(self):
        from autobot_shared.user_management.schemas.user import _checked_username

        with pytest.raises(ValueError, match="letters, numbers"):
            _checked_username(str(uuid.uuid4()))

    def test_no_username_may_contain_the_character_a_uuid_always_has(self):
        from autobot_shared.user_management.schemas.user import _checked_username

        with pytest.raises(ValueError, match="letters, numbers"):
            _checked_username("a-b")

    def test_an_ordinary_username_is_still_accepted(self):
        """Positive control: a validator that rejected everything would pass the
        two assertions above while breaking registration."""
        from autobot_shared.user_management.schemas.user import _checked_username

        assert _checked_username("alice_9") == "alice_9"

    def test_the_channel_uses_the_user_id_when_both_are_present(self):
        """The narrower field wins, so the fallback is only ever a fallback."""
        assert owner_channel({"user_id": "u1", "username": "alice"}) == "agent:u1"
