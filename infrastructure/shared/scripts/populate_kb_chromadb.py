#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Populate knowledge base using ChromaDB instead of Redis to avoid dimension issues.
"""

import asyncio
import glob
import logging
import os
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _find_documentation_files(project_root: Path) -> list:
    """
    Find documentation files to index.

    Issue #281: Extracted from populate_with_chromadb to reduce function length.

    Args:
        project_root: Root directory of the project.

    Returns:
        List of filtered file paths.
    """
    doc_patterns = ["README.md", "CLAUDE.md", "docs/**/*.md", "*.md"]
    exclude_patterns = [
        "**/node_modules/**",
        "**/venv/**",
        "**/test-results/**",
        "**/playwright-report/**",
        "**/.pytest_cache/**",
    ]

    all_files = []
    for pattern in doc_patterns:
        files = glob.glob(str(project_root / pattern), recursive=True)
        all_files.extend(files)

    unique_files = set(all_files)
    filtered_files = []

    for file_path in unique_files:
        should_exclude = False
        for exclude in exclude_patterns:
            if glob.fnmatch.fnmatch(file_path, exclude):
                should_exclude = True
                break

        if not should_exclude and os.path.isfile(file_path):
            filtered_files.append(file_path)

    return filtered_files


def _add_documents_to_index(
    filtered_files: list, project_root: Path, index, Document
) -> tuple:
    """
    Add documents to the ChromaDB index.

    Issue #281: Extracted from populate_with_chromadb to reduce function length.

    Args:
        filtered_files: List of file paths to index.
        project_root: Root directory for relative paths.
        index: VectorStoreIndex instance.
        Document: Document class for creating documents.

    Returns:
        Tuple of (success_count, error_count).
    """
    success_count = 0
    error_count = 0

    for file_path in sorted(filtered_files)[:10]:  # Start with first 10 files
        try:
            rel_path = os.path.relpath(file_path, project_root)

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if not content.strip():
                continue

            metadata = {
                "source": "project-docs",
                "relative_path": rel_path,
                "filename": os.path.basename(file_path),
            }

            logger.info("Adding: %s", rel_path)

            doc = Document(text=content, metadata=metadata)
            index.insert(doc)

            success_count += 1

        except Exception as e:
            error_count += 1
            logger.error("  Error adding %s: %s", file_path, e)

    return success_count, error_count


async def populate_with_chromadb():
    """
    Use ChromaDB for knowledge base instead of Redis.

    Issue #281: Extracted file discovery to _find_documentation_files() and
    document processing to _add_documents_to_index() to reduce function length
    from 134 to ~55 lines.
    """
    logger.info("Setting up ChromaDB-based knowledge base...")

    # Import after path is set
    import chromadb
    from llama_index.core import Document, Settings, VectorStoreIndex
    from llama_index.core.storage.storage_context import StorageContext
    from llama_index.embeddings.ollama import OllamaEmbedding
    from llama_index.llms.ollama import Ollama as LlamaIndexOllamaLLM
    from llama_index.vector_stores.chroma import ChromaVectorStore
    from src.constants import ServiceURLs

    # Set up LLM and embedding model with configurable URL
    ollama_base_url = os.getenv("AUTOBOT_OLLAMA_BASE_URL", ServiceURLs.OLLAMA_LOCAL)

    # Use ModelConstants for centralized model configuration
    from src.constants.model_constants import ModelConstants

    default_model = ModelConstants.DEFAULT_OLLAMA_MODEL

    llm = LlamaIndexOllamaLLM(model=default_model, base_url=ollama_base_url)

    embed_model = OllamaEmbedding(
        model_name="nomic-embed-text", base_url=ollama_base_url
    )

    # Configure settings
    Settings.llm = llm
    Settings.embed_model = embed_model
    Settings.chunk_size = 512
    Settings.chunk_overlap = 20

    # Create ChromaDB client and index
    chroma_client = chromadb.PersistentClient(path="data/chromadb_kb")
    collection = chroma_client.get_or_create_collection(
        name="autobot_docs", metadata={"description": "AutoBot project documentation"}
    )
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_documents(
        [], storage_context=storage_context, embed_model=embed_model
    )

    logger.info("ChromaDB knowledge base initialized successfully!")

    # Issue #281: Use extracted helpers
    project_root = Path("/home/kali/Desktop/AutoBot")
    filtered_files = _find_documentation_files(project_root)
    logger.info("Found %d documentation files", len(filtered_files))

    success_count, error_count = _add_documents_to_index(
        filtered_files, project_root, index, Document
    )

    logger.info("Added %d documents successfully!", success_count)
    logger.info("Errors: %d", error_count)

    # Test search (skip if LLM model unavailable)
    logger.info("Testing search functionality...")
    try:
        query_engine = index.as_query_engine()

        test_queries = ["installation", "configuration", "autobot", "redis"]
        for query in test_queries:
            response = query_engine.query(query)
            logger.info("Query: '%s'", query)
            logger.info("Response: %s...", str(response)[:200])
    except Exception:
        logger.warning(
            "Search test skipped: LLM model '%s' not available", default_model
        )
        logger.info("To enable search testing: ollama pull %s", default_model)
        logger.info("Knowledge base is populated and ready for use")
        return


if __name__ == "__main__":
    asyncio.run(populate_with_chromadb())
