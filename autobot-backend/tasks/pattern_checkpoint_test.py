# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The completed-analysis checkpoint key covers the detection settings, and round-trips (#20513)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from tasks.pattern_checkpoint import (
    checkpoint_options,
    load_path_checkpoint,
    path_checkpoint_key,
    save_path_checkpoint,
)

_FLAGS = ("enable_clone_detection", "enable_anti_pattern_detection", "enable_regex_detection", "enable_complexity_analysis")


def _request(**overrides):
    values = {flag: True for flag in _FLAGS} | {"similarity_threshold": 0.8}
    return SimpleNamespace(**(values | overrides))


def _key(request) -> str:
    return path_checkpoint_key("/scan", "src-1", checkpoint_options(request))


def test_key_is_stable_for_identical_settings():
    assert _key(_request()) == _key(_request())


@pytest.mark.parametrize("flag", _FLAGS)
def test_key_changes_when_a_detection_flag_changes(flag):
    assert _key(_request()) != _key(_request(**{flag: False}))


def test_key_changes_when_similarity_threshold_changes():
    assert _key(_request()) != _key(_request(similarity_threshold=0.5))


@pytest.mark.asyncio
async def test_save_then_load_round_trips_through_redis():
    store: dict = {}
    redis = SimpleNamespace(
        get=AsyncMock(side_effect=lambda key: store.get(key)),
        set=AsyncMock(side_effect=lambda key, value, ex=None: store.__setitem__(key, value)),
    )
    options = checkpoint_options(_request())
    with patch("autobot_shared.redis_client.get_async_redis_client", AsyncMock(return_value=redis)):
        await save_path_checkpoint("/scan", {"patterns": 3}, "src-1", options)
        assert await load_path_checkpoint("/scan", "src-1", options) == {"patterns": 3}
        assert await load_path_checkpoint("/scan", "src-2", options) is None
        other = checkpoint_options(_request(enable_regex_detection=False))
        assert await load_path_checkpoint("/scan", "src-1", other) is None
