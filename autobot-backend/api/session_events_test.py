# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Session and chat channel publishing (#14820).

The property that matters most here is not that a publish happens — it is that a
publish failure never breaks the request that triggered it. These helpers run
*after* a write has already committed, so raising would turn "we could not tell
the other tabs" into "your message failed", which is strictly worse.

Every publish is also asserted to be durable: a client that reconnects has to be
able to replay session changes it missed (#14818), which only works if they were
written to the replay window in the first place.
"""

from unittest.mock import AsyncMock, patch

import pytest

from api.session_events import (
    CHAT_CLEARED,
    CHAT_MESSAGE_ADDED,
    SESSION_CREATED,
    SESSION_DELETED,
    SESSION_UPDATED,
    chat_channel,
    publish_chat_cleared,
    publish_chat_message,
    publish_session_created,
    publish_session_deleted,
    publish_session_updated,
    session_channel,
)
from events.bus import PersistStrategy


def test_session_channel_is_prefixed_by_session():
    assert session_channel("s-1") == "session:s-1"


def test_chat_channel_is_prefixed_by_chat():
    assert chat_channel("s-1") == "chat:s-1"


def test_the_two_channels_are_distinct_for_one_session():
    # Lifecycle and conversation contents are separately subscribable, so a
    # client can watch a session list without paying for message traffic.
    assert session_channel("s-1") != chat_channel("s-1")


@pytest.fixture
def publisher():
    with patch("api.session_events.publish_event", new=AsyncMock()) as mock:
        yield mock


@pytest.mark.asyncio
async def test_session_created_publishes_durably_on_the_session_channel(publisher):
    await publish_session_created("s-1", {"title": "New"})

    channel, event_type, payload = publisher.await_args.args
    assert channel == "session:s-1"
    assert event_type == SESSION_CREATED
    assert payload["session_id"] == "s-1"
    assert payload["session"] == {"title": "New"}
    assert publisher.await_args.kwargs["persist"] is PersistStrategy.REDIS


@pytest.mark.asyncio
async def test_session_updated_carries_only_the_changed_fields(publisher):
    await publish_session_updated("s-1", {"title": "Renamed"})

    channel, event_type, payload = publisher.await_args.args
    assert channel == "session:s-1"
    assert event_type == SESSION_UPDATED
    assert payload["changes"] == {"title": "Renamed"}


@pytest.mark.asyncio
async def test_session_deleted_publishes_on_the_session_channel(publisher):
    await publish_session_deleted("s-1")

    channel, event_type, payload = publisher.await_args.args
    assert channel == "session:s-1"
    assert event_type == SESSION_DELETED
    assert payload == {"session_id": "s-1"}


@pytest.mark.asyncio
async def test_chat_message_publishes_on_the_chat_channel(publisher):
    message = {"id": "m-1", "text": "hello"}
    await publish_chat_message("s-1", message)

    channel, event_type, payload = publisher.await_args.args
    assert channel == "chat:s-1"
    assert event_type == CHAT_MESSAGE_ADDED
    assert payload["message"] == message


@pytest.mark.asyncio
async def test_chat_cleared_publishes_on_the_chat_channel(publisher):
    await publish_chat_cleared("s-1")

    channel, event_type, _payload = publisher.await_args.args
    assert channel == "chat:s-1"
    assert event_type == CHAT_CLEARED


@pytest.mark.asyncio
async def test_every_publisher_requests_durable_persistence(publisher):
    """Replay only works for events that reached the replay window (#14818)."""
    await publish_session_created("s-1", {})
    await publish_session_updated("s-1", {})
    await publish_session_deleted("s-1")
    await publish_chat_message("s-1", {})
    await publish_chat_cleared("s-1")

    assert publisher.await_count == 5
    for call in publisher.await_args_list:
        assert call.kwargs["persist"] is PersistStrategy.REDIS


@pytest.mark.asyncio
async def test_a_publish_failure_does_not_raise_into_the_caller():
    """The write already committed; failing the request now would be worse than
    a missed notification."""
    with patch("api.session_events.publish_event", new=AsyncMock(side_effect=RuntimeError("bus down"))):
        # Each of these must return normally rather than propagate.
        await publish_session_created("s-1", {})
        await publish_session_updated("s-1", {"title": "x"})
        await publish_session_deleted("s-1")
        await publish_chat_message("s-1", {"id": "m"})
        await publish_chat_cleared("s-1")
