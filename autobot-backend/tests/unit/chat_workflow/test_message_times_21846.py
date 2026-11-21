# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A persisted batch gets distinct, ordered, zone-carrying times, and every reader orders old and new alike (#21846)."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from chat_history.deduplication import DeduplicationMixin, parse_message_timestamp
from chat_history.message_times import distinct_ordered_times, message_timestamp, timestamp_sort_key
from chat_history.messages import MessagesMixin
from chat_workflow.manager import ChatWorkflowManager

EARLY = 1_700_000_000.0


def _entry(text, created_at=EARLY):
    return MessagesMixin._build_message_dict(None, "assistant", text, "response", None, None, created_at=created_at)


def test_the_stored_timestamp_carries_a_zone_and_sub_second_resolution():
    stamp = message_timestamp(EARLY + 0.123456)
    assert stamp == "2023-11-14T22:13:20.123456+00:00"
    assert datetime.fromisoformat(stamp).utcoffset().total_seconds() == 0


def test_a_message_built_without_a_creation_time_is_stamped_now_with_a_zone():
    stamp = MessagesMixin._build_message_dict(None, "assistant", "x", "response", None, None)["timestamp"]
    assert abs(datetime.fromisoformat(stamp).timestamp() - time.time()) < 5


def test_a_batch_persisted_at_one_instant_keeps_distinct_ordered_times():
    batch = [_entry(f"step {i}") for i in range(5)]  # five steps, one clock reading
    assert len({m["timestamp"] for m in batch}) == 1
    distinct_ordered_times(batch)
    parsed = [datetime.fromisoformat(m["timestamp"]) for m in batch]
    assert len(set(parsed)) == 5 and parsed == sorted(parsed)


def test_a_message_with_its_own_real_time_keeps_it():
    batch = [_entry("a", EARLY), _entry("b", EARLY + 5), _entry("c", EARLY + 5), _entry("d", EARLY + 9)]
    distinct_ordered_times(batch)
    assert batch[0]["timestamp"] == message_timestamp(EARLY)
    assert batch[1]["timestamp"] == message_timestamp(EARLY + 5)
    assert batch[3]["timestamp"] == message_timestamp(EARLY + 9)
    assert batch[1]["timestamp"] < batch[2]["timestamp"] < batch[3]["timestamp"]


class _Store(MessagesMixin):
    def __init__(self):
        self.saved = None

    async def save_session(self, session_id, messages=None, **_kw):
        self.saved = list(messages)
        return True


@pytest.mark.asyncio
async def test_add_messages_batch_stores_the_distinct_times():
    store = _Store()
    await store.add_messages_batch("s", [_entry("a"), _entry("b"), _entry("c")])
    assert len({m["timestamp"] for m in store.saved}) == 3


def test_a_turn_persisted_by_the_workflow_manager_keeps_distinct_times_in_order():
    chat_mgr = SimpleNamespace(_build_message_dict=lambda *a, **k: MessagesMixin._build_message_dict(None, *a, **k))
    manager = ChatWorkflowManager.__new__(ChatWorkflowManager)
    batch = manager._build_persist_batch(chat_mgr, [], ["first", "second", "third"], "m", None, False)
    distinct_ordered_times(batch)
    stamps = [m["timestamp"] for m in batch]
    assert len(stamps) == 3 and len(set(stamps)) == 3 and stamps == sorted(stamps)


def test_a_legacy_local_timestamp_still_parses_and_is_zone_aware():
    parsed = parse_message_timestamp("2026-11-19 20:42:26")
    assert parsed is not None and parsed.utcoffset() is not None


def test_old_and_new_formats_order_together_by_the_instant_not_by_the_text():
    old = datetime(2026, 11, 19, 12, 0, 0).astimezone()  # server-local wall time, as the old format recorded it
    legacy = {"timestamp": old.strftime("%Y-%m-%d %H:%M:%S"), "text": "old"}
    after = {"timestamp": datetime.fromtimestamp(old.timestamp() + 60, tz=timezone.utc).isoformat(), "text": "new"}
    assert sorted([after, legacy], key=timestamp_sort_key) == [legacy, after]


def test_mixed_format_streaming_groups_do_not_raise():
    mixed = [
        {"messageType": "llm_response", "text": "a", "timestamp": "2026-11-19 12:00:00"},
        {"messageType": "llm_response", "text": "longer", "timestamp": message_timestamp(EARLY)},
    ]
    DeduplicationMixin()._dedupe_streaming_messages(mixed)  # naive vs aware subtraction was a TypeError


def test_a_repost_with_the_original_timestamps_keys_to_the_same_messages_as_the_stored_batch():
    """``session_merge.message_keys`` keys a message by its id; the timestamp counts only for an id-less one."""
    from chat_history.session_merge import message_keys

    batch = [_entry(f"step {i}") for i in range(3)]
    reposted = [dict(m) for m in batch]  # what a client re-sends: the original (equal) timestamps
    distinct_ordered_times(batch)  # what was stored
    assert [m["timestamp"] for m in batch] != [m["timestamp"] for m in reposted]
    assert message_keys(batch) == message_keys(reposted)
    assert all(key[0] == "id" for key in message_keys(batch))


def test_steps_less_than_a_millisecond_apart_are_spread_to_a_millisecond_a_browser_date_can_order():
    batch = [_entry("a", EARLY), _entry("b", EARLY + 0.0001), _entry("c", EARLY + 0.0002)]
    distinct_ordered_times(batch)
    millis = [int(datetime.fromisoformat(m["timestamp"]).timestamp() * 1000) for m in batch]
    assert millis == sorted(set(millis)) and len(set(millis)) == 3
