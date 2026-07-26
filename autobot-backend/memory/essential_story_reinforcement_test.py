# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for A2 (#12553) — usage-aware effective-score reinforcement ranking.

Covers the effective-score formula, the recency factor, the now-order-sensitive
fingerprint, and the end-to-end ranking in ``_fetch_top_facts`` — including the
invariant that reinforcement disabled / weight 0 reproduces the pre-A2 pure
``quality_score`` ordering.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import memory.essential_story as es
from memory.essential_story import (
    EssentialStoryGenerator,
    _compute_facts_fingerprint,
    _effective_score,
    _recency_factor,
)

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)


def _fact(fid, quality, access=0, last_accessed=None, category="general", content=None):
    return {
        "fact_id": fid,
        "content": content or f"content-{fid}",
        "metadata": {
            "quality_score": quality,
            "access_count": access,
            "last_accessed": last_accessed or "",
            "category": category,
        },
    }


# ---- effective score -------------------------------------------------------


def test_effective_score_weight_zero_returns_raw_quality(monkeypatch):
    monkeypatch.setattr(es, "_REINFORCE_WEIGHT", 0.0)
    f = _fact("a", 0.5, access=999, last_accessed=NOW.isoformat())
    assert _effective_score(f, NOW) == 0.5


def test_effective_score_disabled_returns_raw_quality(monkeypatch):
    monkeypatch.setattr(es, "_REINFORCE_ENABLED", False)
    f = _fact("a", 0.5, access=999, last_accessed=NOW.isoformat())
    assert _effective_score(f, NOW) == 0.5


def test_effective_score_boosts_by_access(monkeypatch):
    monkeypatch.setattr(es, "_REINFORCE_ENABLED", True)
    monkeypatch.setattr(es, "_REINFORCE_WEIGHT", 0.3)
    hot = _fact("hot", 0.5, access=50)
    cold = _fact("cold", 0.5, access=0)
    assert _effective_score(hot, NOW, max_access=50) > _effective_score(cold, NOW, max_access=50)


def test_effective_score_normalized_boost_does_not_swamp_quality(monkeypatch):
    # A high-quality never-accessed fact must still beat a low-quality
    # heavily-accessed one: the usage boost is normalised + bounded by weight.
    monkeypatch.setattr(es, "_REINFORCE_ENABLED", True)
    monkeypatch.setattr(es, "_REINFORCE_WEIGHT", 0.3)
    pristine = _fact("pristine", 1.0, access=0)
    popular = _fact("popular", 0.2, access=1_000_000, last_accessed=NOW.isoformat())
    assert _effective_score(pristine, NOW, max_access=1_000_000) > _effective_score(popular, NOW, max_access=1_000_000)


def test_effective_score_no_boost_without_max_access(monkeypatch):
    # Degenerate set (nobody accessed): usage term is 0, ordering is by quality.
    monkeypatch.setattr(es, "_REINFORCE_ENABLED", True)
    monkeypatch.setattr(es, "_REINFORCE_WEIGHT", 0.3)
    f = _fact("a", 0.5, access=0)
    assert _effective_score(f, NOW, max_access=0) == 0.5


def test_effective_score_tolerates_garbage(monkeypatch):
    monkeypatch.setattr(es, "_REINFORCE_ENABLED", True)
    monkeypatch.setattr(es, "_REINFORCE_WEIGHT", 0.3)
    f = {"metadata": {"quality_score": "nan-ish", "access_count": "lots"}}
    # Falls back to 0 quality + 0 access without raising.
    assert _effective_score(f, NOW) == 0.0


# ---- recency factor --------------------------------------------------------


def test_recency_factor_now_is_one():
    assert _recency_factor(NOW.isoformat(), NOW) == 1.0


def test_recency_factor_missing_is_zero():
    assert _recency_factor("", NOW) == 0.0
    assert _recency_factor(None, NOW) == 0.0


def test_recency_factor_unparseable_is_zero():
    assert _recency_factor("not-a-date", NOW) == 0.0


def test_recency_factor_decays_with_age(monkeypatch):
    monkeypatch.setattr(es, "_REINFORCE_RECENCY_HALFLIFE_SECONDS", 30 * 24 * 3600)
    old = (NOW - timedelta(days=30)).isoformat()
    assert _recency_factor(old, NOW) == pytest.approx(0.5, abs=0.01)


# ---- fingerprint order sensitivity ----------------------------------------


def test_fingerprint_is_order_sensitive():
    a, b = _fact("a", 0.9), _fact("b", 0.8)
    assert _compute_facts_fingerprint([a, b]) != _compute_facts_fingerprint([b, a])


def test_fingerprint_stable_for_same_order():
    a, b = _fact("a", 0.9), _fact("b", 0.8)
    assert _compute_facts_fingerprint([a, b]) == _compute_facts_fingerprint([a, b])


# ---- end-to-end ranking in _fetch_top_facts --------------------------------


def _patch_kb(facts):
    kb = MagicMock()
    kb.get_all_facts = AsyncMock(return_value=facts)
    kb.record_fact_access = AsyncMock()
    return kb


@pytest.mark.asyncio
async def test_fetch_top_facts_reinforced_order(monkeypatch):
    monkeypatch.setattr(es, "_REINFORCE_ENABLED", True)
    monkeypatch.setattr(es, "_REINFORCE_WEIGHT", 0.3)
    # Equal quality; the high-access fact must be selected/ranked first.
    facts = [_fact("cold", 0.5, access=0), _fact("hot", 0.5, access=100)]
    kb = _patch_kb(facts)
    with patch("knowledge._composed.get_knowledge_base", AsyncMock(return_value=kb)):
        gen = EssentialStoryGenerator()
        selected = await gen._fetch_top_facts(max_tokens=1000)
    assert [f["fact_id"] for f in selected][0] == "hot"
    kb.record_fact_access.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_top_facts_weight_zero_matches_quality_order(monkeypatch):
    monkeypatch.setattr(es, "_REINFORCE_WEIGHT", 0.0)
    # Reinforcement off: order is pure quality desc regardless of access.
    facts = [
        _fact("low", 0.1, access=1000),
        _fact("high", 0.9, access=0),
        _fact("mid", 0.5, access=500),
    ]
    kb = _patch_kb(facts)
    with patch("knowledge._composed.get_knowledge_base", AsyncMock(return_value=kb)):
        gen = EssentialStoryGenerator()
        selected = await gen._fetch_top_facts(max_tokens=1000)
    assert [f["fact_id"] for f in selected] == ["high", "mid", "low"]


@pytest.mark.asyncio
async def test_fetch_top_facts_ties_are_deterministic(monkeypatch):
    # Equal quality + equal access: order must be stable (by fact_id), not
    # dependent on the (non-deterministic) get_all_facts scan order — otherwise
    # the order-sensitive fingerprint would thrash the cache.
    monkeypatch.setattr(es, "_REINFORCE_WEIGHT", 0.3)
    order_a = [_fact("b", 0.5, access=1), _fact("a", 0.5, access=1), _fact("c", 0.5, access=1)]
    order_b = list(reversed(order_a))
    out = []
    for facts in (order_a, order_b):
        kb = _patch_kb(facts)
        with patch("knowledge._composed.get_knowledge_base", AsyncMock(return_value=kb)):
            selected = await EssentialStoryGenerator()._fetch_top_facts(max_tokens=1000)
        out.append([f["fact_id"] for f in selected])
    assert out[0] == out[1] == ["a", "b", "c"]


def test_env_float_falls_back_on_garbage(monkeypatch):
    monkeypatch.setenv("AUTOBOT_TEST_FLOAT", "not-a-float")
    assert es._env_float("AUTOBOT_TEST_FLOAT", 0.3) == 0.3
    monkeypatch.setenv("AUTOBOT_TEST_FLOAT", "nan")
    assert es._env_float("AUTOBOT_TEST_FLOAT", 0.3) == 0.3
    monkeypatch.setenv("AUTOBOT_TEST_FLOAT", "0.7")
    assert es._env_float("AUTOBOT_TEST_FLOAT", 0.3) == 0.7
