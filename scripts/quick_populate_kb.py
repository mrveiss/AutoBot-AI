#!/usr/bin/env python3
"""
Quick script to populate knowledge base with some test documents
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge_base import KnowledgeBase
import logging

logging.basicConfig(level=logging.INFO)

async def main():
    try:
        kb = KnowledgeBase()
        await kb.ainit()

        # Add some test documents
        documents = [
            {
                "title": "AutoBot Overview",
                "content": "AutoBot is an autonomous Linux administration platform that helps manage and automate system tasks.",
                "source": "README.md",
                "category": "documentation/root"
            },
            {
                "title": "Getting Started Guide",
                "content": "To get started with AutoBot, run the setup.sh script which will install all dependencies and configure your environment.",
                "source": "docs/getting-started.md",
                "category": "documentation/guides"
            },
            {
                "title": "API Documentation",
                "content": "AutoBot provides a comprehensive REST API with over 500 endpoints for system management, AI operations, and workflow automation.",
                "source": "docs/api/overview.md",
                "category": "documentation/api"
            },
            {
                "title": "Architecture Overview",
                "content": "AutoBot uses a distributed VM architecture with 6 specialized VMs: Frontend, NPU Worker, Redis, AI Stack, Browser, and Backend.",
                "source": "docs/architecture.md",
                "category": "documentation/architecture"
            },
            {
                "title": "CLAUDE Instructions",
                "content": "This document contains important instructions and fixes for the AutoBot system. Always follow distributed architecture rules.",
                "source": "CLAUDE.md",
                "category": "documentation/root"
            }
        ]

        print(f"Adding {len(documents)} documents to knowledge base...")

        for doc in documents:
            # Add to Redis as document
            doc_key = f"doc:{doc['source'].replace('/', '_')}"
            kb.redis_client.hset(doc_key, mapping={
                "title": doc["title"],
                "content": doc["content"],
                "source": doc["source"],
                "category": doc["category"]
            })

            # Also add to vector store for search
            await kb.add_text_with_semantic_chunking(
                content=f"{doc['title']}\n\n{doc['content']}",
                metadata={
                    "title": doc["title"],
                    "source": doc["source"],
                    "category": doc["category"]
                }
            )

            print(f"Added: {doc['title']}")

        # Verify documents are in Redis
        all_doc_keys = kb.redis_client.keys("doc:*")
        print(f"\nVerification: Found {len(all_doc_keys)} documents in Redis")

        # Test search
        results = await kb.search("AutoBot", top_k=3)
        print(f"Test search for 'AutoBot' returned {len(results)} results")

        print("\nKnowledge base populated successfully!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())