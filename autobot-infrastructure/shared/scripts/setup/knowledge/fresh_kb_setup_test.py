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
    """Answers add_file/search like a successful ingest without touching llama_index."""

    async def add_file(self, **_kwargs):
        return {"status": "success"}

    async def search(self, *_args, **_kwargs):
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
