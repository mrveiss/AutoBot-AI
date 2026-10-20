# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The fact store's `active_only` read serves the invalidation path, not serving (#18820).

The temporal invalidation job reads facts through ``get_facts_by_criteria(active_only=True)`` to decide what
to invalidate and which stored facts a new one contradicts. It must therefore see a fact that is flagged active
but future-dated or past its ``valid_until`` -- the very facts it exists to act on. Filtering them with the
serving predicate would make a future-dated fact impossible to invalidate.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from models.atomic_fact import AtomicFact, FactType, TemporalType
from services.fact_extraction_service import FactExtractionService

_NOW = datetime.now(tz=timezone.utc)


def _stored(**overrides) -> str:
    fields = dict(
        subject="s",
        predicate="is",
        object="x",
        fact_type=FactType.FACT,
        temporal_type=TemporalType.DYNAMIC,
        confidence=0.9,
        source="test",
        extraction_method="manual",
        valid_from=_NOW - timedelta(days=1),
    )
    fields.update(overrides)
    return json.dumps(AtomicFact(**fields).to_dict())


class _Pipe:
    def __init__(self, store: dict) -> None:
        self._store, self._keys = store, []

    def hget(self, key: str, _field: str) -> None:
        self._keys.append(key)

    async def execute(self) -> list:
        return [self._store.get(key) for key in self._keys]


class _Redis:
    def __init__(self, facts: dict) -> None:
        self._facts = {f"fact:{fact_id}": data for fact_id, data in facts.items()}
        self._ids = set(facts)

    async def smembers(self, _key: str) -> set:
        return set(self._ids)

    def pipeline(self) -> _Pipe:
        return _Pipe(self._facts)


async def _criteria(facts: dict, **kwargs):
    """What `get_facts_by_criteria` returns -- the call both temporal-invalidation sites make."""
    service = object.__new__(FactExtractionService)
    service.redis_client = _Redis(facts)
    service.fact_storage_prefix = "fact:"
    service.fact_index_key = "facts"
    return await service.get_facts_by_criteria(**kwargs)


@pytest.mark.asyncio
async def test_a_future_dated_active_fact_is_returned_to_the_invalidation_path() -> None:
    future = _stored(valid_from=_NOW + timedelta(days=30))
    got = await _criteria({"future": future}, active_only=True)
    assert len(got) == 1


@pytest.mark.asyncio
async def test_a_date_expired_but_still_active_fact_is_returned_to_the_invalidation_path() -> None:
    expired = _stored(valid_until=_NOW - timedelta(hours=1))
    assert len(await _criteria({"expired": expired}, active_only=True)) == 1


@pytest.mark.asyncio
async def test_an_inactive_fact_is_not_returned_by_active_only() -> None:
    assert await _criteria({"gone": _stored(is_active=False)}, active_only=True) == []


@pytest.mark.asyncio
async def test_active_only_false_returns_an_inactive_fact() -> None:
    """Contrast: the flag filter applies only when `active_only` asks for it."""
    assert len(await _criteria({"gone": _stored(is_active=False)}, active_only=False)) == 1
