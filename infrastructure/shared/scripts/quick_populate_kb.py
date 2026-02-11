#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Quick script to populate knowledge base with some test documents
"""

import asyncio
import os
import sys

import logging

logger = logging.getLogger(__name__)

from knowledge_base import KnowledgeBase

logging.basicConfig(level=logging.INFO)


def _get_test_documents() -> list:
    """Get test documents for knowledge base.

    Helper for main (Issue #825).
    """
    return [
        {
            "title": "AutoBot Overview",
            "content": (
                "AutoBot is an autonomous Linux administration platform"
                " that helps manage and automate system tasks."
            ),
            "source": "README.md",
            "category": "documentation/root",
        },
        {
            "title": "Getting Started Guide",
            "content": (
                "To get started with AutoBot, run the setup.sh script"
                " which will install all dependencies and configure"
                " your environment."
            ),
            "source": "docs/getting-started.md",
            "category": "documentation/guides",
        },
        {
            "title": "API Documentation",
            "content": (
                "AutoBot provides a comprehensive REST API with over"
                " 500 endpoints for system management, AI operations,"
                " and workflow automation."
            ),
            "source": "docs/api/overview.md",
            "category": "documentation/api",
        },
        {
            "title": "Architecture Overview",
            "content": (
                "AutoBot uses a distributed VM architecture with 6"
                " specialized VMs: Frontend, NPU Worker, Redis,"
                " AI Stack, Browser, and Backend."
            ),
            "source": "docs/architecture.md",
            "category": "documentation/architecture",
        },
        {
            "title": "CLAUDE Instructions",
            "content": (
                "This document contains important instructions and"
                " fixes for the AutoBot system. Always follow"
                " distributed architecture rules."
            ),
            "source": "CLAUDE.md",
            "category": "documentation/root",
        },
    ]


async def _wait_for_kb_initialization(kb) -> bool:
    """Wait for knowledge base to initialize.

    Helper for main (Issue #825).

    Returns:
        True if initialized, False if failed
    """
    max_wait = 15
    for i in range(max_wait):
        if kb.redis_client is not None and kb.vector_store is not None:
            logger.info(f"Knowledge base initialized after {i} seconds")
            return True
        await asyncio.sleep(1)

    if kb.redis_client is None:
        logger.error("❌ Redis client failed to initialize after 15 seconds")
        return False

    if kb.vector_store is None:
        logger.info(
            "❌ Vector store failed to initialize, but continuing with Redis operations"
        )

    return True


async def _add_documents_to_kb(kb, documents: list) -> None:
    """Add documents to knowledge base.

    Helper for main (Issue #825).
    """
    logger.info(f"Adding {len(documents)} documents to knowledge base...")

    for doc in documents:
        doc_key = f"doc:{doc['source'].replace('/', '_')}"
        kb.redis_client.hset(
            doc_key,
            mapping={
                "title": doc["title"],
                "content": doc["content"],
                "source": doc["source"],
                "category": doc["category"],
            },
        )

        if kb.vector_store is not None:
            try:
                result = await kb.add_document(
                    content=f"{doc['title']}\n\n{doc['content']}",
                    metadata={
                        "title": doc["title"],
                        "source": doc["source"],
                        "category": doc["category"],
                    },
                )

                if result.get("status") == "success":
                    logger.info(f"✅ Added to vector store: {doc['title']}")
                else:
                    msg = result.get('message', 'Unknown error')
                    logger.info(
                        "❌ Failed to add to vector store:"
                        " %s - %s", doc['title'], msg,
                    )
            except Exception as e:
                logger.error(f"❌ Exception adding to vector store: {doc['title']} - {e}")
        else:
            logger.info(
                f"⚠️ Vector store not available, skipping vector indexing for: {doc['title']}"
            )

        logger.info(f"Added: {doc['title']}")


async def _verify_and_test_kb(kb) -> None:
    """Verify documents and test search.

    Helper for main (Issue #825).
    """
    all_doc_keys = kb.redis_client.keys("doc:*")
    logger.info(f"\nVerification: Found {len(all_doc_keys)} documents in Redis")

    if kb.vector_store is not None:
        try:
            results = await kb.search("AutoBot", similarity_top_k=3)
            logger.info(f"Test search for 'AutoBot' returned {len(results)} results")

            if results:
                logger.info(
                    f"Sample result: {results[0].get('text', 'No text')[:100]}..."
                )
        except Exception as e:
            logger.error(f"❌ Search test failed: {e}")
    else:
        logger.warning("⚠️ Vector store not available, skipping search test")


async def main():
    """Populate knowledge base with test documents."""
    try:
        kb = KnowledgeBase()

        if not await _wait_for_kb_initialization(kb):
            return

        documents = _get_test_documents()
        await _add_documents_to_kb(kb, documents)
        await _verify_and_test_kb(kb)

        logger.info("\nKnowledge base populated successfully!")

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
