# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The code-graph writer and reader must name the same collection (#17254).

They did not. The writer was handed `doc_svc._collection` (`autobot_docs`); the
reader queried `autobot_code` filtering `record_type: node|edge`; and the sole
writer of `autobot_code` never writes that key. `GET /impact` therefore answered
"nothing is affected" with `indexed: true` — a confident wrong answer to "what
breaks if I change this?".

Neither shared collection was safe to host the graph either: each is recreated
wholesale by its own primary writer (`chromadb_storage.py` and `doc_indexer.py`
both call `delete_collection`), so the other subsystem's next re-index would
destroy it. Hence a dedicated collection, and hence this guard — the failure was
silent, survived a closed issue (#4835), and is invisible to any test that does
not compare the two sides.

Static on purpose: CI has no ChromaDB, and the defect is a disagreement between
two source files, which is exactly what static reading can prove.

Mutation check: point either side back at `autobot_code` or `autobot_docs` and
this goes red naming both sides.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

_ROOT = repo_root()
_STORAGE = _ROOT / "autobot-backend" / "api" / "codebase_analytics" / "storage.py"
_READER = _ROOT / "autobot-backend" / "api" / "codebase_analytics" / "endpoints" / "impact.py"
_ROUTE = _ROOT / "autobot-backend" / "api" / "knowledge_population.py"
#: The worker moved out of knowledge_population.py, which sits at its size
#: ceiling and may not grow (#5060) -- the route stays there, the indexing does not.
_WRITER = _ROOT / "autobot-backend" / "api" / "knowledge_code_indexing.py"


def _text(path):
    return path.read_text(encoding="utf-8")


def test_the_graph_collection_is_its_own_store():
    """Not autobot_code, not autobot_docs — both are wiped by their own writer."""
    storage = _text(_STORAGE)
    match = re.search(r'^CODE_GRAPH_COLLECTION\s*=\s*"([^"]+)"', storage, re.M)

    assert match, "CODE_GRAPH_COLLECTION is no longer declared in storage.py"
    name = match.group(1)
    assert name not in {"autobot_code", "autobot_docs"}, (
        f"the code graph is back in {name}, which its other writer recreates with "
        "delete_collection — the graph would vanish on that subsystem's next re-index"
    )


def test_reader_and_writer_use_the_same_accessor():
    """The two sides must resolve the collection through one helper, not two names."""
    reader, writer = _text(_READER), _text(_WRITER)

    assert (
        "get_code_graph_collection" in reader
    ), "impact.py no longer resolves the graph collection through the shared accessor"
    # Either accessor is fine -- require_* wraps the async getter and raises
    # rather than returning None. What must not happen is the indexer naming a
    # collection of its own again.
    assert (
        "code_graph_collection" in writer
    ), "the indexer no longer resolves the graph collection through the shared accessor"


def test_the_reader_does_not_query_the_inventory_collection():
    """autobot_code holds type=function|class|import, never record_type."""
    reader = _text(_READER)

    assert "get_code_collection" not in reader.replace("get_code_graph_collection", ""), (
        "impact.py reads the inventory collection again; its writer never emits "
        "record_type, so every query would return an empty reach set"
    )


def test_the_indexer_endpoint_is_routed():
    """#4835: the body was complete and the decorator was missing, twice."""
    route_file = _text(_ROUTE)
    index_code_at = route_file.index("async def index_code(")
    preceding = route_file[:index_code_at]

    assert preceding.rstrip().endswith('@router.post("/index/code")'), (
        "index_code has no route decorator — the indexer has no HTTP trigger, and the "
        "status endpoint reports on a job nothing can start (#4835)"
    )
