# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A fake knowledge base with one private fact per user, for the #16665 read-path tests.

The ownership manager is the real :class:`KnowledgeOwnership`, so a test exercises the one
canonical visibility decision rather than a stand-in for it.
"""

import json
from fnmatch import fnmatchcase

from autobot_shared.ssot_config import config
from knowledge.categories import CategoriesMixin
from knowledge.ownership import KnowledgeOwnership
from knowledge.quarantine import apply_quarantine, gate_response
from testkit.fake_redis_pipeline import FakeAsyncPipeline

PRIVATE_A = "alice private fact"
PRIVATE_B = "bob private fact"
SHARED = "platform wide fact"
RESEARCH = "quarantined research finding"


def _fact(fact_id: str, content: str, **meta) -> dict:
    metadata = {"source": "doc", "category": "AGENT_DIARY", **meta}
    return {
        "id": fact_id,
        "fact_id": fact_id,
        "content": content,
        "score": 0.9,
        "similarity_score": 0.95,
        "metadata": metadata,
    }


def all_facts() -> list[dict]:
    return [
        _fact("f-a", PRIVATE_A, owner_id="alice", visibility="private"),
        _fact("f-b", PRIVATE_B, owner_id="bob", visibility="private"),
        _fact("f-s", SHARED, owner_id="admin", visibility="system"),
    ]


class FakeKB:
    """Returns every fact for any query, as a vector search does before visibility is applied."""

    def __init__(self):
        self.ownership_manager = KnowledgeOwnership(None)
        self.llm = None
        self.vector_store = object()

    async def search(self, *args, **kwargs):
        return all_facts()

    async def get_all_facts(self, limit=None, offset=0):
        return all_facts()

    def get_fact(self, fact_id):
        return next((f for f in all_facts() if f["id"] == fact_id), None)

    async def record_fact_access(self, ids):
        return None


def text_of(value) -> str:
    """Every string reachable in *value*, joined, so an assertion cannot miss a nested copy."""
    return repr(value)


def quarantined_fact() -> dict:
    """A platform-wide fact held in the research quarantine: only the quarantine can hide it."""
    return _fact(
        "f-q", RESEARCH, owner_id="admin", visibility="system", collection=config.research_quarantine_collection
    )


class QuarantineGatedKB(FakeKB):
    """A KB holding one quarantined fact, read through the real quarantine gate ``KB.search`` ends with.

    A route that asks for the default read gets the gated answer; one that opted out would get the fact.
    ``dict_results`` shapes ``search`` like the enhanced mode (``{"results": [...]}``);
    ``only_quarantined`` makes the quarantined fact the sole fact, so a leak has nothing else to hide behind.
    """

    def __init__(self, dict_results: bool = False, only_quarantined: bool = False):
        super().__init__()
        self.dict_results = dict_results
        self.only_quarantined = only_quarantined

    def _held(self) -> list[dict]:
        return [quarantined_fact()] if self.only_quarantined else all_facts() + [quarantined_fact()]

    async def search(self, *args, include_unservable=False, include_quarantined=False, audit_actor=None, **kwargs):
        hits = await gate_response(self._held(), include_unservable, include_quarantined, audit_actor)
        return {"results": hits} if self.dict_results else hits

    async def get_all_facts(self, limit=None, offset=0, include_quarantined=False, audit_actor=None):
        return await apply_quarantine(self._held(), include_quarantined, audit_actor)


OPEN_META = {"owner_id": "admin", "visibility": "system"}


class SetRedis:
    """An in-memory Redis with the hash, set and string commands the category code uses (#16665, #21957).

    Hashes hold bytes keys and values, as ``hgetall`` returns them; sets hold the strings written.
    """

    def __init__(self):
        self.hashes: dict = {}
        self.sets: dict = {}
        self.strings: dict = {}
        self.reads: list = []  # every hash read command, so a test can show a count made none
        self.pipelines: list = []  # every pipeline handed out; each records what it executed
        self.next_pipeline_errors: list = []  # errors the next pipeline raises on EXEC, before applying anything
        self.after_metadata_read = None  # one-shot async hook: runs right after the next ``metadata`` hget

    @staticmethod
    def _b(value) -> bytes:
        return value if isinstance(value, bytes) else str(value).encode("utf-8")

    def pipeline(self, transaction: bool = True):
        errors, self.next_pipeline_errors = self.next_pipeline_errors, []
        pipe = FakeAsyncPipeline(self, transaction=transaction, execute_errors=errors)
        self.pipelines.append(pipe)
        return pipe

    def executed_batches(self) -> list:
        """Each EXEC that reached Redis, as ``[(command, key, ...), ...]``, in order."""
        return [batch for pipe in self.pipelines for batch in pipe.executed]

    async def get(self, key):
        return self.strings.get(key)

    async def set(self, key, value):
        self.strings[key] = self._b(value)

    async def delete(self, *keys):
        for key in keys:
            self.sets.pop(key, None)
            self.hashes.pop(key, None)

    async def scan_iter(self, match="*", count=None):
        for key in [k for k in list(self.sets) if fnmatchcase(k, match)]:
            yield key.encode("utf-8")

    async def sadd(self, key, *values):
        self.sets.setdefault(key, set()).update(values)

    async def srem(self, key, *values):
        self.sets.get(key, set()).difference_update(values)

    async def smembers(self, key):
        return {m.encode("utf-8") for m in self.sets.get(key, set())}

    async def sdiff(self, first, *others):
        gone = set().union(*(self.sets.get(k, set()) for k in others))
        return {m.encode("utf-8") for m in self.sets.get(first, set()) - gone}

    async def hset(self, key, field=None, value=None, mapping=None):
        row = self.hashes.setdefault(key, {})
        for name, val in {**({field: value} if field else {}), **(mapping or {})}.items():
            row[self._b(name)] = self._b(val)

    async def hget(self, key, field):
        self.reads.append(("hget", key))
        value = self.hashes.get(key, {}).get(self._b(field))
        if field == "metadata" and self.after_metadata_read:
            hook, self.after_metadata_read = self.after_metadata_read, None
            await hook()
        return value

    async def hgetall(self, key):
        self.reads.append(("hgetall", key))
        return dict(self.hashes.get(key, {}))

    async def hmget(self, key, fields, *more):
        self.reads.append(("hmget", key))
        return [self.hashes.get(key, {}).get(self._b(f)) for f in [*fields, *more]]

    async def hscan(self, key, cursor=0, match=None, count=None):
        self.reads.append(("hscan", key))
        return 0, dict(self.hashes.get(key, {}))

    async def hkeys(self, key):
        self.reads.append(("hkeys", key))
        return list(self.hashes.get(key, {}))

    async def hvals(self, key):
        self.reads.append(("hvals", key))
        return list(self.hashes.get(key, {}).values())

    async def hincrby(self, key, field, amount):
        return amount


class CategoryKB(CategoriesMixin):
    """The real ``CategoriesMixin`` over :class:`SetRedis`; facts enter through the real assign path."""

    def __init__(self):
        self._aioredis_client = True
        self._redis = SetRedis()
        self.ownership_manager = KnowledgeOwnership(None)

    def redis(self):
        return self._redis

    async def _get_category_data(self, category_id):
        return {"path": "research"}

    async def add_fact(self, fact_id: str, category_id: str | None = "cat1", **meta) -> None:
        """Store a fact hash and, unless *category_id* is None, categorise it by the production code."""
        metadata = json.dumps({**OPEN_META, **meta})
        await self._redis.hset(f"fact:{fact_id}", mapping={"content": f"fact {fact_id}", "metadata": metadata})
        if category_id:
            await self._assign_fact_to_category(fact_id, category_id)
