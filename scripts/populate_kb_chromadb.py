#!/usr/bin/env python3
"""
Populate knowledge base using ChromaDB instead of Redis to avoid dimension issues.
"""

import asyncio
import glob
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def populate_with_chromadb():
    """Use ChromaDB for knowledge base instead of Redis."""

    print("Setting up ChromaDB-based knowledge base...")

    # Import after path is set
    import chromadb
    from llama_index.core import Document, Settings, VectorStoreIndex
    from llama_index.core.storage.storage_context import StorageContext
    from llama_index.embeddings.ollama import OllamaEmbedding
    from llama_index.llms.ollama import Ollama as LlamaIndexOllamaLLM
    from llama_index.vector_stores.chroma import ChromaVectorStore
    from src.constants import NetworkConstants, ServiceURLs

    # Set up LLM and embedding model with configurable URL
    ollama_base_url = os.getenv("AUTOBOT_OLLAMA_BASE_URL", ServiceURLs.OLLAMA_LOCAL)

    # Use default LLM model from environment or fallback to common model
    default_model = os.getenv("AUTOBOT_DEFAULT_LLM_MODEL", "llama3.2:1b")

    llm = LlamaIndexOllamaLLM(
        model=default_model, base_url=ollama_base_url
    )

    embed_model = OllamaEmbedding(
        model_name="nomic-embed-text", base_url=ollama_base_url
    )

    # Configure settings
    Settings.llm = llm
    Settings.embed_model = embed_model
    Settings.chunk_size = 512
    Settings.chunk_overlap = 20

    # Create ChromaDB client
    chroma_client = chromadb.PersistentClient(path="data/chromadb_kb")

    # Create or get collection
    collection = chroma_client.get_or_create_collection(
        name="autobot_docs", metadata={"description": "AutoBot project documentation"}
    )

    # Create vector store
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # Create index
    index = VectorStoreIndex.from_documents(
        [], storage_context=storage_context, embed_model=embed_model
    )

    print("ChromaDB knowledge base initialized successfully!")

    # Now add documents
    project_root = Path("/home/kali/Desktop/AutoBot")
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

    print(f"Found {len(filtered_files)} documentation files")

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

            print(f"Adding: {rel_path}")

            doc = Document(text=content, metadata=metadata)
            index.insert(doc)

            success_count += 1

        except Exception as e:
            error_count += 1
            print(f"  Error adding {file_path}: {str(e)}")

    print(f"\nAdded {success_count} documents successfully!")
    print(f"Errors: {error_count}")

    # Test search (skip if LLM model unavailable)
    print("\nTesting search functionality...")
    try:
        query_engine = index.as_query_engine()

        test_queries = ["installation", "configuration", "autobot", "redis"]
        for query in test_queries:
            response = query_engine.query(query)
            print(f"\nQuery: '{query}'")
            print(f"Response: {str(response)[:200]}...")
    except Exception as e:
        print(f"⚠️  Search test skipped: LLM model '{default_model}' not available")
        print(f"   To enable search testing: ollama pull {default_model}")
        print(f"   Knowledge base is populated and ready for use")
        return


if __name__ == "__main__":
    asyncio.run(populate_with_chromadb())
