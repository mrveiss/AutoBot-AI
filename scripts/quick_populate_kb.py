#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
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
    """Populate knowledge base with test documents."""
    try:
        kb = KnowledgeBase()

        # Wait for Redis initialization to complete
        max_wait = 15  # Maximum 15 seconds
        for i in range(max_wait):
            if kb.redis_client is not None and kb.vector_store is not None:
                print(f"Knowledge base initialized after {i} seconds")
                break
            await asyncio.sleep(1)

        if kb.redis_client is None:
            print("❌ Redis client failed to initialize after 15 seconds")
            return

        if kb.vector_store is None:
            print("❌ Vector store failed to initialize, but continuing with Redis operations")
            # We can still add documents to Redis even without vector store

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

            # Also add to vector store for search (if available)
            if kb.vector_store is not None:
                try:
                    result = await kb.add_document(
                        content=f"{doc['title']}\n\n{doc['content']}",
                        metadata={
                            "title": doc["title"],
                            "source": doc["source"],
                            "category": doc["category"]
                        }
                    )

                    if result.get("status") == "success":
                        print(f"✅ Added to vector store: {doc['title']}")
                    else:
                        print(f"❌ Failed to add to vector store: {doc['title']} - {result.get('message', 'Unknown error')}")
                except Exception as e:
                    print(f"❌ Exception adding to vector store: {doc['title']} - {e}")
            else:
                print(f"⚠️ Vector store not available, skipping vector indexing for: {doc['title']}")

            print(f"Added: {doc['title']}")

        # Verify documents are in Redis
        all_doc_keys = kb.redis_client.keys("doc:*")
        print(f"\nVerification: Found {len(all_doc_keys)} documents in Redis")

        # Test search (if vector store available)
        if kb.vector_store is not None:
            try:
                results = await kb.search("AutoBot", similarity_top_k=3)
                print(f"Test search for 'AutoBot' returned {len(results)} results")

                # Show a sample result if any found
                if results:
                    print(f"Sample result: {results[0].get('text', 'No text')[:100]}...")
            except Exception as e:
                print(f"❌ Search test failed: {e}")
        else:
            print("⚠️ Vector store not available, skipping search test")

        print("\nKnowledge base populated successfully!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
