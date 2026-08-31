# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``category`` default in ``get_category_distribution`` (#14047)."""

import json
from datetime import datetime, timezone

import pytest

from api.analytics_llm_patterns import LLMPatternAnalyzer
from constants.threshold_constants import CategoryDefaults


def _todays_usage_key() -> str:
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    return f"{LLMPatternAnalyzer()._usage_key}:{today}"


class _FakePipe:
    def __init__(self, records_by_key):
        self._records_by_key = records_by_key
        self._calls = []

    async def lrange(self, key, start, end):
        self._calls.append(key)

    async def execute(self):
        return [self._records_by_key.get(k, []) for k in self._calls]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeRedis:
    def __init__(self, records_by_key):
        self._records_by_key = records_by_key

    def pipeline(self):
        return _FakePipe(self._records_by_key)


def _analyzer_with_records(records_by_key):
    analyzer = LLMPatternAnalyzer()

    async def _fake_get_redis():
        return _FakeRedis(records_by_key)

    analyzer._get_redis = _fake_get_redis
    return analyzer


@pytest.mark.asyncio
async def test_missing_category_defaults_to_unknown():
    record = json.dumps({"cost": 1.0})
    analyzer = _analyzer_with_records({_todays_usage_key(): [record]})

    result = await analyzer.get_category_distribution()

    names = [c["category"] for c in result["categories"]]
    assert names == [CategoryDefaults.UNKNOWN]


@pytest.mark.asyncio
async def test_explicit_category_overrides_default():
    record = json.dumps({"cost": 1.0, "category": "coding"})
    analyzer = _analyzer_with_records({_todays_usage_key(): [record]})

    result = await analyzer.get_category_distribution()

    names = [c["category"] for c in result["categories"]]
    assert names == ["coding"]
    assert CategoryDefaults.UNKNOWN not in names
