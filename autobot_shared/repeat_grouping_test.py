# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shared repeat grouping (#20664, #16333)."""

from autobot_shared.repeat_grouping import RepeatGrouper


def test_one_record_per_window_and_the_next_counts_the_repeats():
    grouper = RepeatGrouper(window_s=300)
    assert grouper.repeats_to_record("k") == 0
    assert all(grouper.repeats_to_record("k") is None for _ in range(49))
    at, repeats = grouper._recent["k"]
    grouper._recent["k"] = (at - 301, repeats)
    assert grouper.repeats_to_record("k") == 49


def test_keys_are_independent():
    grouper = RepeatGrouper(window_s=300)
    assert grouper.repeats_to_record(("alice", "/a")) == 0
    assert grouper.repeats_to_record(("alice", "/b")) == 0
    assert grouper.repeats_to_record(("bob", "/a")) == 0


def test_the_tracked_set_cant_grow_past_its_cap():
    grouper = RepeatGrouper(window_s=300, max_tracked=3)
    for number in range(20):
        assert grouper.repeats_to_record(f"person-{number}") == 0
    assert len(grouper._recent) <= 3


def test_a_full_tracker_drops_expired_keys_first_and_still_records_a_new_key():
    grouper = RepeatGrouper(window_s=300, max_tracked=2)
    assert grouper.repeats_to_record("old") == 0
    assert grouper.repeats_to_record("live") == 0
    at, repeats = grouper._recent["old"]
    grouper._recent["old"] = (at - 301, repeats)
    assert grouper.repeats_to_record("new") == 0
    assert set(grouper._recent) == {"live", "new"}


def test_a_burst_then_silence_loses_its_repeats_when_the_key_is_forgotten():
    """#20787: stated behaviour, pinned. Repeats ride only on the key's next record."""
    grouper = RepeatGrouper(window_s=300, max_tracked=1)
    assert grouper.repeats_to_record("burst") == 0
    assert all(grouper.repeats_to_record("burst") is None for _ in range(9))
    at, repeats = grouper._recent["burst"]
    grouper._recent["burst"] = (at - 301, repeats)
    assert grouper.repeats_to_record("other") == 0  # the full tracker forgets the expired key
    assert grouper.repeats_to_record("burst") == 0  # its 9 repeats are gone
