# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared doubles for the #18825 owner-scope tests: an in-memory Redis and entity-document builders."""

from autobot_memory_graph.entities import EntityOperationsMixin
from autobot_memory_graph.owner_scope import SHARED_OWNER_ID, OwnerScope, entity_visible
from autobot_memory_graph.queries import QueryOperationsMixin
from autobot_memory_graph.relation_traversal import RelationTraversalMixin
from autobot_memory_graph.relations import RelationOperationsMixin

ALICE_ID = "11111111-1111-1111-1111-111111111111"
BOB_ID = "22222222-2222-2222-2222-222222222222"
ALICE = OwnerScope.for_user(ALICE_ID)
BOB = OwnerScope.for_user(BOB_ID)


def _doc(entity_id, name, owner, *, org=None, entity_type="conversation", tags=("conversation",), obs=("hi",)):
    """An entity document shaped like ``_build_entity_document`` output."""
    return {
        "id": entity_id,
        "type": entity_type,
        "name": name,
        "observations": list(obs),
        "metadata": {"tags": list(tags), "status": "active", "valid_to": None},
        "owner_user_id": owner,
        "owner_org_id": org,
    }


ALICE_CONV = _doc("c-alice", "Conversation alice", ALICE_ID, obs=("Summary: alice's private plan",))
BOB_CONV = _doc("c-bob", "Conversation bob", BOB_ID, obs=("Summary: bob's private plan",))
BOB_UNTAGGED = _doc("n-bob", "Note bob", BOB_ID, entity_type="note", tags=("other",))
ALICE_UNTAGGED = _doc("n-alice", "Note alice", ALICE_ID, entity_type="note", tags=("other",))
SHARED_DOC = _doc("s-1", "Conversation shared", SHARED_OWNER_ID)
LEGACY_DOC = {k: v for k, v in _doc("c-old", "Conversation old", "x").items() if not k.startswith("owner_")}


class _Pipe:
    def __init__(self, redis):
        self._redis, self._keys = redis, []

    def json(self):
        return self

    def get(self, key):
        self._keys.append(key)

    async def execute(self):
        return [self._redis.docs.get(k) for k in self._keys]


class _Json:
    def __init__(self, redis):
        self._redis = redis

    async def get(self, key):
        return self._redis.docs.get(key)


class FakeRedis:
    """Just the Redis surface the query mixin touches. ``search_down`` forces the scan fallback."""

    def __init__(self, docs, search_down=True):
        self.docs = {f"memory:entity:{d['id']}": d for d in docs}
        self.search_down = search_down
        self.commands = []

    async def execute_command(self, *args):
        self.commands.append(args)
        if self.search_down:
            raise RuntimeError("RediSearch unavailable")
        # What RediSearch returns when *its own filter is not applied*: every doc. The post-filter must hold.
        keys = list(self.docs)
        out = [len(keys)]
        for key in keys:
            out.extend([key, ["$.name", "x"]])
        return out

    async def scan_iter(self, match=None):
        for key in list(self.docs):
            yield key

    def pipeline(self):
        return _Pipe(self)

    def json(self):
        return _Json(self)


class QueryHost(QueryOperationsMixin):
    def __init__(self, docs, search_down=True):
        self.redis_client = FakeRedis(docs, search_down)

    def ensure_initialized(self):
        return None


ALL_DOCS = [ALICE_CONV, BOB_CONV, BOB_UNTAGGED, ALICE_UNTAGGED, SHARED_DOC, LEGACY_DOC]


def _names(entities):
    return {e["name"] for e in entities}


class TraversalHost(RelationTraversalMixin, EntityOperationsMixin):
    """A -> X(bob) -> C : alice owns A and C, bob owns the middle node."""

    def __init__(self):
        a = _doc("a", "A", ALICE_ID, entity_type="note")
        x = _doc("x", "X", BOB_ID, entity_type="note")
        c = _doc("c", "C", ALICE_ID, entity_type="note")
        self.redis_client = FakeRedis([a, x, c])
        self._out = {"a": [{"to": "x", "type": "related_to"}], "x": [{"to": "c", "type": "related_to"}]}

    def ensure_initialized(self):
        return None

    async def search_entities(self, query, limit=50, *, owner, **kwargs):
        hits = [d for d in self.redis_client.docs.values() if d["name"] == query]
        return [d for d in hits if entity_visible(d, owner)]

    async def _get_outgoing_relations(self, entity_id):
        return self._out.get(entity_id, [])

    async def _get_incoming_relations(self, entity_id):
        return []


class RelationHost(RelationOperationsMixin, EntityOperationsMixin, QueryHost):
    """Real ``get_relations`` / ``get_entity`` over stored edges: ``out`` and ``inc`` map entity id -> raw edges."""

    def __init__(self, docs, out=None, inc=None, search_down=True):
        super().__init__(docs, search_down)
        self._out, self._in = out or {}, inc or {}

    async def initialize(self):
        return None

    async def _get_outgoing_relations(self, entity_id):
        return list(self._out.get(entity_id, []))

    async def _get_incoming_relations(self, entity_id):
        return list(self._in.get(entity_id, []))
