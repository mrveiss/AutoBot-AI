#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Fresh knowledge base setup - let llama_index create everything from scratch.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# A backend tool (#18288, #18289): it drives the backend's KnowledgeBase, so it puts the backend and
# the repository root (for `autobot_shared`) on its own path and runs from any directory with no
# PYTHONPATH. #14507: it used to insert its own parent (``scripts/setup``) and then import
# ``knowledge_base`` from a directory that was never on the path; this script's success message tells
# the operator to run ``populate_knowledge_base.py`` next, so the pair broke together.
_REPO_ROOT = Path(__file__).resolve().parents[5]
for _root in (_REPO_ROOT / "autobot-backend", _REPO_ROOT):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from autobot_shared.logging_manager import get_logger  # noqa: E402

logger = get_logger(__name__)

#: The Redis database the knowledge base keeps its search index in (``KnowledgeBase.redis_db``).
_KB_DATABASE = "knowledge"

# Import centralized Redis client
from autobot_shared.redis_client import get_redis_client  # noqa: E402
from autobot_shared.redis_utils import decode_redis_list, decode_redis_value  # noqa: E402


def _log_plan(plan: dict) -> None:
    """Log what a wipe would delete, store by store."""
    for store in plan["databases"]:
        logger.info(f"   Database {store['database']}: {store['keys']} keys ({store['note']})")
        for index in store["indexes"]:
            logger.info(f"   Index {index['name']}: {index['documents']} documents")
    for collection in plan["chroma_collections"]:
        logger.info(f"   Chroma collection {collection['name']}: {collection['vectors']} vectors")
    logger.info(f"   Total keys: {plan['total_keys']}, total vectors: {plan['total_vectors']}")


async def _propose_wipe(plan: dict) -> str:
    """Raise (or reuse) the human-approval proposal for the wipe; return its approval id. Deletes nothing."""
    import getpass

    from services.kb_wipe_action import CHANNEL_OPERATOR, propose_kb_wipe
    from user_management.database import get_async_session_factory

    async with get_async_session_factory()() as db:
        approval = await propose_kb_wipe(db, getpass.getuser(), plan, channel=CHANNEL_OPERATOR)
    return str(approval.id)


def _create_test_document() -> str:
    """Create a test document for knowledge base.

    Helper for fresh_setup (Issue #825).
    """
    test_file = "/tmp/test_kb_doc.md"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("""
# AutoBot Documentation Test

AutoBot is an autonomous AI agent platform designed for enterprise use.

## Features
- Multi-agent orchestration
- Redis-based memory
- Knowledge base with vector search
- Vue.js frontend
- FastAPI backend

## Installation
To install AutoBot, follow the setup guide in the README.
""")
    return test_file


def _log_vector_dimension(r, idx_name: str) -> None:
    """Log the vector dimension of index *idx_name* from ``FT.INFO``.

    ``get_redis_client`` returns a decode_responses=True client, so FT.INFO elements arrive as str, not
    the bytes this used to index with (#13290) -- decode defensively for both wire shapes.
    """
    info = decode_redis_list(r.execute_command("FT.INFO", idx_name))
    attrs = info[info.index("attributes") + 1]
    for attr in attrs:
        if "vector" in attr:
            for i, item in enumerate(attr):
                if item == "dim":
                    logger.info(f"   Vector dimension: {attr[i+1]}")
                    break


async def _test_knowledge_base(kb, r) -> bool:
    """Test knowledge base with sample document.

    Helper for fresh_setup (Issue #825).
    """
    logger.info("\n3. Testing with sample document...")

    test_file = _create_test_document()

    # #14507: ``add_file`` is defined nowhere in the KnowledgeBase mixin chain
    # and ``search`` takes ``top_k``, not ``n_results`` (#10666) -- both calls
    # raised before this smoke test could report anything.
    result = await kb.add_document_from_file(
        file_path=test_file,
        category="documentation",
        metadata={"source": "test"},
    )

    logger.info(f"   Add result: {result}")

    if result.get("status") == "success":
        results = await kb.search("AutoBot features", top_k=2)
        logger.info(f"\n4. Search test results: {len(results)} found")
        if results:
            logger.info(f"   First result score: {results[0].get('score', 0)}")
            logger.info(f"   Content preview: {results[0].get('content', '')[:100]}...")

        logger.info("\n5. Checking created index...")
        indexes = r.execute_command("FT._LIST")
        logger.info(f"   Indexes: {indexes}")

        # #21121: the index the KB reports is the one inspected; another index in the list is not a pass.
        names = [decode_redis_value(name) for name in indexes or []]
        if kb.redis_index_name not in names:
            logger.error(f"   KB index {kb.redis_index_name!r} is missing from the knowledge database: {names}")
            return False
        _log_vector_dimension(r, kb.redis_index_name)

        return True
    else:
        logger.error(f"\n   Error: {result.get('message', 'Unknown error')}")
        return False


async def _request_wipe(dry_run: bool) -> bool:
    """Dry run lists the KB stores; otherwise request approval. Neither deletes anything (#21048)."""
    from services.kb_wipe_action import plan_kb_wipe

    plan = await plan_kb_wipe()
    _log_plan(plan)
    if dry_run:
        logger.info("   Dry run: nothing was deleted.")
        return True
    approval_id = await _propose_wipe(plan)
    logger.info(f"   Wipe requested (approval {approval_id}). Nothing is deleted until an admin approves it.")
    return True


async def _initialize_knowledge_base() -> bool:
    """Create the knowledge base and run the smoke test against the Redis database it keeps its index in."""
    # #21121: the KB creates its search index in the knowledge database, so the smoke test reads that one.
    r = get_redis_client(database=_KB_DATABASE)
    if r is None:
        logger.error(f"   Redis database {_KB_DATABASE!r} is unavailable; initialization aborted")
        return False

    logger.info("\n2. Initializing fresh knowledge base...")

    # Deferred: ``knowledge/__init__`` loads the composed class lazily (#1514),
    # so a module-scope import would pull redis, chromadb and llama_index in
    # merely to inspect this script.
    from knowledge_factory import get_knowledge_base_async

    kb = await get_knowledge_base_async()
    if kb is None:
        logger.error("   Knowledge base unavailable: initialization failed or retry cooldown active")
        return False
    logger.info(f"   Using embedding model: {kb.embedding_model_name}")
    logger.info(f"   Using Redis DB: {kb.redis_db}")
    logger.info(f"   Using index name: {kb.redis_index_name}")

    logger.info("   Knowledge base initialized!")

    return await _test_knowledge_base(kb, r)


async def fresh_setup(dry_run: bool = False, initialize: bool = False):
    """Request (or preview) a knowledge-base wipe; with ``initialize``, set up a fresh knowledge base.

    The wipe itself runs in the backend only after a human approves the request (#21048, #17038). This
    script never deletes data and offers no full wipe.
    """

    logger.info("=== Fresh Knowledge Base Setup ===")

    if not initialize:
        logger.info(
            "\n1. Knowledge base wipe (knowledge database, its search indexes and its Chroma collections only)..."
        )
        return await _request_wipe(dry_run)

    return await _initialize_knowledge_base()


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Request a knowledge-base wipe, or initialise a fresh KB.")
    parser.add_argument("--dry-run", action="store_true", help="list what the wipe would delete; delete nothing")
    parser.add_argument(
        "--initialize", action="store_true", help="after an approved wipe: create the KB and run the smoke test"
    )
    args = parser.parse_args(argv)
    if args.initialize and args.dry_run:
        parser.error("--dry-run previews the wipe; --initialize ingests a document. They cannot be combined.")
    return args


if __name__ == "__main__":
    args = _parse_args()
    success = asyncio.run(fresh_setup(dry_run=args.dry_run, initialize=args.initialize))
    if success:
        logger.info("\nDone.")
    else:
        logger.error("\n✗ Knowledge base setup failed!")
