#!/usr/bin/env python3
"""
Populate knowledge base with ChromaDB to avoid Redis dimension issues.
"""

import asyncio
import os
import sys
import glob
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def populate_knowledge_base_chromadb():
    """Populate knowledge base using ChromaDB."""

    print("=== Populating Knowledge Base with ChromaDB ===")

    # Force ChromaDB by setting environment
    os.environ["AUTOBOT_VECTOR_STORE_TYPE"] = "chroma"

    # Import and initialize knowledge base
    from src.knowledge_base import KnowledgeBase

    kb = KnowledgeBase()
    print(f"Vector store type: {kb.vector_store_type}")

    # Initialize
    await kb.ainit()

    if kb.vector_store is None:
        print("❌ Failed to initialize vector store")
        return False

    print("✓ Knowledge base initialized with ChromaDB")

    # Find all documentation files
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

    # Add files to knowledge base
    for file_path in sorted(filtered_files):
        try:
            rel_path = os.path.relpath(file_path, project_root)

            # Categorize the document
            if "docs/guides" in rel_path:
                category = "user-guide"
            elif "docs/development" in rel_path:
                category = "developer-docs"
            elif "docs/reports" in rel_path:
                category = "reports"
            elif rel_path in ["README.md", "CLAUDE.md"]:
                category = "project-overview"
            else:
                category = "documentation"

            metadata = {
                "source": "project-docs",
                "category": category,
                "relative_path": rel_path,
                "filename": os.path.basename(file_path),
            }

            print(f"Adding: {rel_path} [{category}]")

            result = await kb.add_file(
                file_path=file_path, file_type="txt", metadata=metadata
            )

            if result["status"] == "success":
                success_count += 1
            else:
                error_count += 1
                print(f"  ❌ {result['message']}")

        except Exception as e:
            error_count += 1
            print(f"  ❌ Error adding {file_path}: {str(e)}")

    print(f"\n=== Results ===")
    print(f"✓ Successfully added: {success_count} documents")
    print(f"❌ Errors: {error_count}")

    # Test search functionality
    if success_count > 0:
        print(f"\n=== Testing Search ===")
        test_queries = ["installation", "configuration", "autobot", "debian"]

        for query in test_queries:
            try:
                results = await kb.search(query, n_results=2)
                print(f"Query '{query}': {len(results)} results")
                if results:
                    print(
                        f"  Top result: {results[0].get('metadata', {}).get('filename', 'Unknown')}"
                    )
            except Exception as e:
                print(f"  ❌ Search failed: {e}")

    return success_count > 0


if __name__ == "__main__":
    success = asyncio.run(populate_knowledge_base_chromadb())
    if success:
        print("\n🎉 Knowledge base population completed!")
    else:
        print("\n💥 Knowledge base population failed!")
