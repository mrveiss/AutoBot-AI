# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The memory lifecycle view reads and never writes (#12631, umbrella #12630).

The endpoint exists so an operator can see what the nightly decay would delete
before enabling it. That makes two properties load-bearing:

* **It must never delete.** A preview that mutates is not a preview.
* **The preview must agree with the deleter.** If "would this be pruned" were
  computed separately from "prune this", an operator could approve a list that
  does not match what runs. So the tests drive the real predicate rather than a
  restatement of it.

The sections are also asserted to degrade *independently*: one unreachable store
must not blank the half that is readable, because an empty payload cannot be told
apart from a system that genuinely has no facts.
"""

from __future__ import annotations

import inspect
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

pytest.importorskip("fastapi")

from api import memory_lifecycle  # noqa: E402

_NOW = datetime(2026, 8, 19, tzinfo=timezone.utc)
_EPOCH = _NOW - timedelta(days=400)


def _fact(fact_id: str, *, quality: float, access: int, age_days: int, protected: bool = False) -> Dict[str, Any]:
    created = _NOW - timedelta(days=age_days)
    meta: Dict[str, Any] = {
        "quality_score": quality,
        "access_count": access,
        "last_accessed": (created + timedelta(days=1)).isoformat(),
        "timestamp": created.isoformat(),
    }
    if protected:
        # A real protection marker: `unique_key` denotes deliberately curated
        # knowledge, which a low access_count must not condemn (#12554).
        meta["unique_key"] = f"curated:{fact_id}"
    return {"fact_id": fact_id, "content": f"fact {fact_id}", "timestamp": created.isoformat(), "metadata": meta}


class _FakeKB:
    """A stateful stand-in that records whether anything tried to delete.

    Stateful rather than a MagicMock on purpose: with a mock, "the store still
    holds every fact" and "nothing was ever asked for" look identical, so the
    read-only assertion would pass against an endpoint that deleted everything.
    """

    def __init__(self, facts: List[Dict[str, Any]]):
        self._facts = {f["fact_id"]: f for f in facts}
        self.deletes: List[str] = []

    def ensure_initialized(self) -> None:
        """The real prune path calls this first; the fake is always ready."""

    def count(self) -> int:
        return len(self._facts)

    async def get_all_facts(self, limit: int = 5000) -> List[Dict[str, Any]]:
        return list(self._facts.values())

    async def delete_fact(self, fact_id: str) -> bool:  # pragma: no cover - must not run
        self.deletes.append(fact_id)
        self._facts.pop(fact_id, None)
        return True

    # The two helpers and the prune path are the REAL implementations, bound to
    # this fake's storage — so the preview exercises the shipped predicate.
    async def list_facts_with_usage(self, limit: int = 5000):
        from knowledge.facts import FactsMixin

        return await FactsMixin.list_facts_with_usage(self, limit=limit)

    @staticmethod
    def prune_config_snapshot():
        from knowledge.facts import FactsMixin

        return FactsMixin.prune_config_snapshot()

    def _prune_candidate_details(self, facts, quality_floor, cutoff, epoch):
        from knowledge.facts import FactsMixin

        return FactsMixin._prune_candidate_details(self, facts, quality_floor, cutoff, epoch)

    def _schedule_bm25_refresh(self):  # pragma: no cover - not exercised by a dry run
        pass

    async def consolidate_facts(self, **kwargs):
        from knowledge.facts import FactsMixin

        return await FactsMixin.consolidate_facts(self, **kwargs)


@pytest.fixture
def seeded():
    """Three facts: one hot, one cold-but-protected, one genuinely prunable."""
    return _FakeKB(
        [
            _fact("hot", quality=0.9, access=40, age_days=300),
            _fact("protected", quality=0.01, access=0, age_days=300, protected=True),
            _fact("prunable", quality=0.01, access=0, age_days=300),
        ]
    )


@pytest.mark.asyncio
async def test_the_preview_never_deletes(seeded, monkeypatch):
    """The invariant. A preview that mutates is not a preview."""
    monkeypatch.setattr("knowledge.get_knowledge_base", lambda: _async(seeded), raising=False)
    before = seeded.count()

    section = await _decay_with(seeded, monkeypatch)

    assert seeded.deletes == [], f"the preview deleted {seeded.deletes}"
    assert seeded.count() == before
    assert "prune_preview" in section


@pytest.mark.asyncio
async def test_the_preview_lists_the_fact_the_deleter_would_remove(seeded, monkeypatch):
    """Agreement with the deleter, not merely a non-empty list.

    Driving the real predicate is the point: a preview computed by a second
    implementation could list a different set and nothing would notice.
    """
    section = await _decay_with(seeded, monkeypatch)
    previewed = {c["fact_id"] for c in section["prune_preview"]}
    assert previewed == {"prunable"}, f"preview disagrees with the predicate: {previewed}"


@pytest.mark.asyncio
async def test_each_preview_entry_carries_the_values_that_qualified_it(seeded, monkeypatch):
    """Rule names tell an operator nothing they cannot read off the rule.

    The values tell them whether the floor is set where they meant it.
    """
    section = await _decay_with(seeded, monkeypatch)
    reasons = section["prune_preview"][0]["reasons"]
    assert any("below floor" in r for r in reasons)
    assert any("never recalled" in r for r in reasons)
    assert any("older than cutoff" in r for r in reasons)


@pytest.mark.asyncio
async def test_hot_and_cold_are_ordered_opposite_ways(seeded, monkeypatch):
    """Both ends are reported. Showing one would leave the other invisible,
    which is how this area went dark to begin with."""
    section = await _reinforcement_with(seeded, monkeypatch, limit=3)
    hot = [f["fact_id"] for f in section["hot"]]
    cold = [f["fact_id"] for f in section["cold"]]
    assert hot[0] == "hot", f"hottest fact is not first: {hot}"
    assert cold[0] != "hot", f"the hottest fact leads the cold list: {cold}"
    assert set(hot) == set(cold), "the two ends describe different fact sets"


@pytest.mark.asyncio
async def test_a_failing_section_does_not_blank_the_other(monkeypatch):
    """Independent degradation. A single try/except around both would return an
    empty payload, indistinguishable from a system with no facts."""

    async def _boom(*_a, **_k):
        raise RuntimeError("store unreachable")

    monkeypatch.setattr(memory_lifecycle, "_decay_section", _boom)
    monkeypatch.setattr(
        memory_lifecycle,
        "_reinforcement_section",
        lambda limit: _async({"hot": [{"fact_id": "x"}], "cold": []}),
    )

    body = await memory_lifecycle.get_memory_lifecycle.__wrapped__(limit=5, admin_check=True)

    assert body["degraded"] is True
    assert body["reinforcement"]["hot"], "the readable half was blanked by the other half's failure"


@pytest.mark.asyncio
async def test_degraded_is_false_when_both_sections_answer(monkeypatch):
    """Guard the guard: if degraded were hardcoded true, every test above would
    still pass while the flag carried no information."""
    monkeypatch.setattr(memory_lifecycle, "_decay_section", lambda limit: _async({"last_run": "x"}))
    monkeypatch.setattr(memory_lifecycle, "_reinforcement_section", lambda limit: _async({"hot": [], "cold": []}))

    body = await memory_lifecycle.get_memory_lifecycle.__wrapped__(limit=5, admin_check=True)
    assert body["degraded"] is False


def _async(value):
    async def _inner(*_a, **_k):
        return value

    return _inner()


async def _decay_with(kb, monkeypatch) -> Dict[str, Any]:
    monkeypatch.setattr("knowledge.get_knowledge_base", lambda: _async(kb), raising=False)
    monkeypatch.setattr(
        "autobot_shared.redis_client.get_async_redis_client",
        lambda **_k: _async(None),
        raising=False,
    )
    monkeypatch.setenv("AUTOBOT_FACTS_PRUNE_EPOCH", _EPOCH.isoformat())
    import importlib

    import knowledge.facts as facts_mod

    importlib.reload(facts_mod)
    return await memory_lifecycle._decay_section(limit=10)


async def _reinforcement_with(kb, monkeypatch, limit: int) -> Dict[str, Any]:
    monkeypatch.setattr("knowledge.get_knowledge_base", lambda: _async(kb), raising=False)
    return await memory_lifecycle._reinforcement_section(limit)


@pytest.mark.asyncio
async def test_a_last_run_failure_does_not_blank_the_rest_of_the_section(seeded, monkeypatch):
    """Independent degradation applies WITHIN the decay section too.

    Review found this section claimed independent degradation in its docstring
    while a Redis blip on the last-run key discarded the already-computed config
    and the not-yet-attempted preview — the coupling the top-level split exists
    to avoid, one level down.
    """
    monkeypatch.setattr("knowledge.get_knowledge_base", lambda: _async(seeded), raising=False)

    def _explode(**_k):
        raise RuntimeError("redis down")

    monkeypatch.setattr("autobot_shared.redis_client.get_async_redis_client", _explode, raising=False)
    monkeypatch.setenv("AUTOBOT_FACTS_PRUNE_EPOCH", _EPOCH.isoformat())
    import importlib

    import knowledge.facts as facts_mod

    importlib.reload(facts_mod)

    section = await memory_lifecycle._decay_section(limit=10)

    assert section["last_run"] is None
    assert section.get("last_run_unavailable") is True
    assert section["config"], "the config snapshot was discarded by an unrelated failure"
    assert {c["fact_id"] for c in section["prune_preview"]} == {"prunable"}


# ---------------------------------------------------------------------------
# #12631 review: the reader must read the database the writer writes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_last_run_is_read_from_the_database_the_writer_uses(seeded, monkeypatch):
    """The reader and the writer must agree on the logical Redis database.

    `memory:consolidate_facts:last_run` is written by
    `workers/consolidate_tasks.py` with ``database="analytics"``. This endpoint
    originally read it with ``database="main"`` — a different logical database,
    so the key was never found and ``last_run`` was permanently ``None``.

    That is a silent failure, not a loud one: the endpoint's own error path
    already answers ``None`` for "could not read it", so a wrong-database read
    is indistinguishable from a Redis blip. The whole point of this PR is that
    the key "had no readers"; a reader pointed at the wrong database is still
    no reader.

    So the database is asserted at the seam rather than eyeballed: the client
    factory is captured and its ``database`` argument compared against the
    writer's own.
    """
    requested: List[str] = []

    class _Client:
        async def get(self, _key):
            return b"2026-08-21T00:00:00+00:00"

    async def _capture(*_args, **kwargs):
        requested.append(kwargs.get("database"))
        return _Client()

    monkeypatch.setattr(
        "autobot_shared.redis_client.get_async_redis_client", _capture, raising=False
    )

    section = await _decay_with(seeded, monkeypatch)

    assert requested, "the last-run lookup never asked for a Redis client"

    from workers import consolidate_tasks

    writer_src = inspect.getsource(consolidate_tasks._get_redis)
    writer_db = re.search(r'database="([a-z_]+)"', writer_src)
    assert writer_db, "could not determine the writer's database — repoint this test"

    assert requested[0] == writer_db.group(1), (
        f"the reader asked for database={requested[0]!r} but "
        f"workers/consolidate_tasks.py writes the key to "
        f"{writer_db.group(1)!r} — the key will never be found"
    )
    assert section.get("last_run"), "a readable last_run must be surfaced, not dropped"
