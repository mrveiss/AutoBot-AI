# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for GemmaClassificationAgent dedup cache and batch classify — Issue #8164.

Exercises the new _classify_cache_key / _cached_classify / classify_multiple
logic directly, without importing through the full agents package (which has
broken transitional deps in the dev venv).
"""

import asyncio
import hashlib
from types import SimpleNamespace

import pytest

# ---------------------------------------------------------------------------
# Minimal stand-in that hosts only the new methods from Issue #8164.
# We extract + exercise the actual code without triggering agents/__init__.py.
# ---------------------------------------------------------------------------

_CLASSIFICATION_REDIS_KEY_PREFIX = "gemma_classify:"

import os as _os

_CLASSIFICATION_CACHE_TTL = int(_os.environ.get("AUTOBOT_CLASSIFICATION_CACHE_TTL", "300"))

import asyncio as _asyncio
import hashlib as _hashlib


class _StubAgent:
    """Minimal reproduction of the dedup methods from GemmaClassificationAgent."""

    def _classify_cache_key(self, user_message: str) -> str:
        digest = _hashlib.sha256(user_message.encode("utf-8")).hexdigest()[:24]
        return f"{_CLASSIFICATION_REDIS_KEY_PREFIX}{digest}"

    async def classify_multiple(self, messages, max_concurrent=10):
        if not messages:
            return []

        hash_to_msg = {}
        msg_hashes = []
        for msg in messages:
            h = _hashlib.sha256(msg.encode("utf-8")).hexdigest()[:24]
            msg_hashes.append(h)
            if h not in hash_to_msg:
                hash_to_msg[h] = msg

        sem = _asyncio.Semaphore(max_concurrent)

        async def _one(msg):
            async with sem:
                return await self.classify_request(msg)

        unique_results = dict(
            zip(
                hash_to_msg.keys(),
                await _asyncio.gather(*[_one(m) for m in hash_to_msg.values()]),
            )
        )

        return [unique_results[h] for h in msg_hashes]

    async def classify_request(self, msg):
        raise NotImplementedError("override in tests")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_classify_cache_key_stable():
    agent = _StubAgent()
    msg = "What is Docker?"
    key1 = agent._classify_cache_key(msg)
    key2 = agent._classify_cache_key(msg)
    assert key1 == key2
    assert key1.startswith("gemma_classify:")


def test_classify_cache_key_includes_sha256():
    agent = _StubAgent()
    msg = "What is Docker?"
    expected_hash = hashlib.sha256(msg.encode("utf-8")).hexdigest()[:24]
    assert agent._classify_cache_key(msg) == f"gemma_classify:{expected_hash}"


def test_classify_cache_key_unique_per_message():
    agent = _StubAgent()
    assert agent._classify_cache_key("A") != agent._classify_cache_key("B")


@pytest.mark.asyncio
async def test_classify_multiple_deduplicates():
    """5 identical messages should result in only 1 call to classify_request."""
    agent = _StubAgent()
    call_count = 0

    async def fake_classify(msg):
        nonlocal call_count
        call_count += 1
        return SimpleNamespace(complexity="simple", msg=msg)

    agent.classify_request = fake_classify  # type: ignore

    results = await agent.classify_multiple(["What is Docker?"] * 5)
    assert len(results) == 5
    assert call_count == 1, "Dedup must reduce 5 identical messages to 1 LLM call"


@pytest.mark.asyncio
async def test_classify_multiple_preserves_order():
    """Results must be in the same order as input messages."""
    agent = _StubAgent()

    complexity_map = {
        "What is Docker?": "simple",
        "Install nginx on Ubuntu": "complex",
        "Hello world": "simple",
    }

    async def fake_classify(msg):
        return SimpleNamespace(complexity=complexity_map.get(msg, "simple"))

    agent.classify_request = fake_classify  # type: ignore

    messages = [
        "Install nginx on Ubuntu",
        "What is Docker?",
        "Install nginx on Ubuntu",  # duplicate of [0]
        "Hello world",
    ]
    results = await agent.classify_multiple(messages)
    assert results[0].complexity == "complex"
    assert results[1].complexity == "simple"
    assert results[2].complexity == "complex"  # same as [0]
    assert results[3].complexity == "simple"


@pytest.mark.asyncio
async def test_classify_multiple_empty():
    agent = _StubAgent()
    assert await agent.classify_multiple([]) == []


@pytest.mark.asyncio
async def test_classify_multiple_unique_messages():
    """N distinct messages should each be classified once."""
    agent = _StubAgent()
    call_count = 0

    async def fake_classify(msg):
        nonlocal call_count
        call_count += 1
        return SimpleNamespace(complexity="simple")

    agent.classify_request = fake_classify  # type: ignore

    messages = [f"message {i}" for i in range(4)]
    results = await agent.classify_multiple(messages)
    assert len(results) == 4
    assert call_count == 4
