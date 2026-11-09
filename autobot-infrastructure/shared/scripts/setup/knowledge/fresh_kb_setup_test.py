# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for setup/knowledge/fresh_kb_setup — the FT.INFO vector-dimension walk (#13290).

Only ``_test_knowledge_base``'s FT.INFO walk is covered here; the rest of the
script (``fresh_setup``) drives real Redis flush/index-drop calls and a real
``KnowledgeBase``, which is out of scope for a fake-client unit test.
"""

import importlib.util
import pathlib
import sys
import types

import pytest

_MODULE_PATH = pathlib.Path(__file__).with_name("fresh_kb_setup.py")


def _load_module():
    """Import fresh_kb_setup by path — its directory is not a package."""
    spec = importlib.util.spec_from_file_location("setup_knowledge_fresh_kb_setup", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["setup_knowledge_fresh_kb_setup"] = module
    spec.loader.exec_module(module)
    return module


fresh_kb_setup = _load_module()


class FakeRedis:
    """Answers FT._LIST / FT.INFO like a decode_responses=True client.

    ``get_redis_client`` returns a ``decode_responses=True`` client
    (``autobot_shared/redis_management/config.py:61,153``), so both replies
    are nested lists of ``str`` — mocking ``bytes`` would let a
    bytes-literal-indexing bug pass vacuously (#13290).
    """

    def execute_command(self, *args):
        if args[0] == "FT._LIST":
            return ["llama_index"]
        if args[0] == "FT.INFO":
            return ["attributes", [["identifier", "vector", "attribute", "vector", "dim", "768"]]]
        return "OK"


class FakeKnowledgeBase:
    """Answers ingest/search like a successful run without touching llama_index.

    #14507: this used to answer ``add_file(**kwargs)`` and ``search(*a, **kw)``
    -- a shape the real ``KnowledgeBase`` never produced. ``add_file`` is
    defined nowhere in the mixin chain and ``search`` takes ``top_k``, not
    ``n_results``, so the fake made two dead calls look alive. Both signatures
    now mirror the real ones (``knowledge/documents.py``, ``knowledge/search.py``)
    and reject anything they would reject.
    """

    redis_index_name = "llama_index"

    async def add_document_from_file(self, file_path: str, category: str = "general", metadata=None):
        return {"status": "success"}

    async def search(self, query, top_k=10, similarity_top_k=None, filters=None, mode="auto"):
        return []


@pytest.mark.asyncio
async def test_test_knowledge_base_reads_a_decoded_ft_info_reply(caplog):
    """#13290: bytes-literal indexing on a decoded FT.INFO reply crashed the script.

    ``attrs_idx = info.index(b"attributes")`` on a ``str``-element list
    raises ``ValueError``, and this block is not wrapped in a try/except, so
    the whole setup script aborted after already reporting a successful
    ingest and search — the crash happened in the verification step, not
    the setup itself.
    """
    redis = FakeRedis()
    kb = FakeKnowledgeBase()

    with caplog.at_level("INFO", logger=fresh_kb_setup.logger.name):
        result = await fresh_kb_setup._test_knowledge_base(kb, redis)

    assert result is True
    assert "Vector dimension: 768" in caplog.text


class _Plan:
    """A plan shaped like ``plan_kb_wipe``'s, for the script's two entry modes."""

    value = {
        "databases": [{"database": "knowledge", "keys": 3, "indexes": [], "note": "Not atomic"}],
        "chroma_collections": [{"name": "autobot_memory", "vectors": 8}],
        "total_keys": 3,
        "total_vectors": 8,
    }


async def _plan():
    return _Plan.value


@pytest.mark.asyncio
async def test_dry_run_lists_the_plan_and_neither_proposes_nor_deletes(monkeypatch, caplog):
    """#21048: ``--dry-run`` only reads; no approval is raised and no delete command is issued."""
    from services import kb_wipe_action

    monkeypatch.setattr(kb_wipe_action, "plan_kb_wipe", _plan)
    proposed = []

    async def fake_propose(plan):
        proposed.append(plan)
        return "id"

    monkeypatch.setattr(fresh_kb_setup, "_propose_wipe", fake_propose)
    with caplog.at_level("INFO", logger=fresh_kb_setup.logger.name):
        assert await fresh_kb_setup.fresh_setup(dry_run=True) is True
    assert proposed == [] and "Database knowledge: 3 keys" in caplog.text
    assert "Chroma collection autobot_memory: 8 vectors" in caplog.text


@pytest.mark.asyncio
async def test_a_bare_run_only_requests_approval(monkeypatch):
    """#21048: running the script proposes the wipe through the approval gate and deletes nothing itself."""
    from services import kb_wipe_action

    monkeypatch.setattr(kb_wipe_action, "plan_kb_wipe", _plan)
    proposed = []

    async def fake_propose(plan):
        proposed.append(plan)
        return "approval-1"

    monkeypatch.setattr(fresh_kb_setup, "_propose_wipe", fake_propose)
    assert await fresh_kb_setup.fresh_setup() is True
    assert proposed == [_Plan.value]


def test_the_script_has_no_delete_calls_left():
    source = _MODULE_PATH.read_text(encoding="utf-8")
    assert "flushdb" not in source and "DROPINDEX" not in source and "flushall" not in source.lower()


@pytest.mark.asyncio
async def test_initialize_reads_the_knowledge_database_never_main(monkeypatch):
    """#21121: the smoke test reads FT._LIST where the KB keeps its index, so a ``main`` read fails here."""
    asked = []
    clients = {"knowledge": FakeRedis(), "main": types.SimpleNamespace(execute_command=lambda *a: [])}

    def fake_client(database="main", **_):
        asked.append(database)
        return clients[database]

    class _KB(FakeKnowledgeBase):
        embedding_model_name, redis_db, redis_index_name = "m", 1, "llama_index"

    async def fake_kb():
        return _KB()

    monkeypatch.setattr(fresh_kb_setup, "get_redis_client", fake_client)
    monkeypatch.setitem(sys.modules, "knowledge_factory", types.SimpleNamespace(get_knowledge_base_async=fake_kb))
    assert await fresh_kb_setup.fresh_setup(initialize=True) is True
    assert asked == ["knowledge"]


@pytest.mark.asyncio
async def test_smoke_test_inspects_the_kb_index_not_the_first_one_listed(caplog):
    """#21121: FT.INFO runs on ``kb.redis_index_name``; a different first index is not a pass."""

    class TwoIndexes(FakeRedis):
        def execute_command(self, *args):
            self.asked = getattr(self, "asked", []) + [args]
            if args[0] == "FT._LIST":
                return ["other_index", "llama_index"]
            return super().execute_command(*args)

    redis = TwoIndexes()
    with caplog.at_level("INFO", logger=fresh_kb_setup.logger.name):
        assert await fresh_kb_setup._test_knowledge_base(FakeKnowledgeBase(), redis) is True
    assert ("FT.INFO", "llama_index") in redis.asked and ("FT.INFO", "other_index") not in redis.asked


@pytest.mark.asyncio
async def test_smoke_test_fails_when_the_kb_index_is_missing():
    class OtherOnly(FakeRedis):
        def execute_command(self, *args):
            return ["other_index"] if args[0] == "FT._LIST" else super().execute_command(*args)

    assert await fresh_kb_setup._test_knowledge_base(FakeKnowledgeBase(), OtherOnly()) is False


def test_dry_run_with_initialize_is_an_argument_error():
    with pytest.raises(SystemExit):
        fresh_kb_setup._parse_args(["--dry-run", "--initialize"])
