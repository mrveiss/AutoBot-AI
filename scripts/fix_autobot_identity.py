#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Fix AutoBot Identity in Knowledge Base

This script ensures AutoBot's identity documentation is properly indexed in the knowledge base
to prevent hallucinations about being a Meta AI model or Transformers character.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.knowledge_base import KnowledgeBase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Main function to fix AutoBot identity in knowledge base"""
    try:
        # Initialize knowledge base
        logger.info("Initializing knowledge base...")
        kb = KnowledgeBase()

        # Check if AutoBot identity document exists
        identity_file = project_root / "data" / "system_knowledge" / "autobot_identity.md"

        if not identity_file.exists():
            logger.error(f"AutoBot identity file not found at {identity_file}")
            return

        logger.info(f"Found AutoBot identity file at {identity_file}")

        # Read the identity document
        with open(identity_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Create document metadata
        metadata = {
            "source": "system_knowledge/autobot_identity.md",
            "type": "system_documentation",
            "category": "identity",
            "priority": "critical",
            "title": "AutoBot Identity and Capabilities",
            "keywords": ["autobot", "identity", "what is autobot", "capabilities", "architecture", "linux", "automation"]
        }

        # Add to knowledge base with high priority
        logger.info("Adding AutoBot identity to knowledge base...")
        try:
            # Method 1: Try direct addition if method exists
            if hasattr(kb, 'add_document'):
                await kb.add_document(content, metadata)
                logger.info("Successfully added AutoBot identity using add_document method")
            elif hasattr(kb, 'add_documents'):
                await kb.add_documents([{"content": content, "metadata": metadata}])
                logger.info("Successfully added AutoBot identity using add_documents method")
            else:
                logger.warning("Knowledge base doesn't have standard add methods, trying alternative approach...")

                # Method 2: Try through vector store if available
                if hasattr(kb, 'vector_store') and kb.vector_store:
                    from llama_index.core import Document
                    doc = Document(text=content, metadata=metadata)
                    kb.vector_store.add([doc])
                    logger.info("Successfully added AutoBot identity through vector store")
                else:
                    logger.error("Could not find suitable method to add document to knowledge base")
                    return

        except Exception as e:
            logger.error(f"Error adding document to knowledge base: {e}")
            return

        # Test search to verify
        logger.info("Testing knowledge base search for 'what is autobot'...")
        try:
            if hasattr(kb, 'search'):
                results = await kb.search("what is autobot", limit=5)
            elif hasattr(kb, 'query'):
                results = await kb.query("what is autobot", limit=5)
            else:
                logger.warning("Could not test search - no search method found")
                results = []

            if results:
                logger.info(f"Search returned {len(results)} results")
                for i, result in enumerate(results[:2], 1):
                    logger.info(f"Result {i}: {result.get('title', 'No title')} (score: {result.get('score', 'N/A')})")
            else:
                logger.warning("Search returned no results - identity may not be indexed yet")

        except Exception as e:
            logger.error(f"Error testing search: {e}")

        logger.info("AutoBot identity fix completed!")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
