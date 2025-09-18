#!/usr/bin/env python3
"""
Load documentation into AutoBot knowledge base
This script indexes all documentation for vector search and RAG capabilities
"""

import asyncio
import json
from pathlib import Path


async def load_documents_to_knowledge_base(kb_path: str = "/app/knowledge_base"):
    """Load all documents from knowledge base directory into vector DB"""

    # Import after environment is set up
    from src.knowledge_base import KnowledgeBase

    kb = KnowledgeBase()

    # Load index
    index_path = Path(kb_path) / "index.json"
    if index_path.exists():
        with open(index_path) as f:
            index = json.load(f)
    else:
        print(f"Warning: No index.json found at {index_path}")
        index = {"categories": {}}

    documents_loaded = 0

    # Process each category
    for category_id, category_info in index.get("categories", {}).items():
        category_path = Path(kb_path) / category_id
        if not category_path.exists():
            continue

        print(f"\n📁 Processing category: {category_info['name']}")

        # Find all documents
        for pattern in index.get("auto_index_patterns", ["*.md", "*.txt"]):
            for doc_path in category_path.rglob(pattern):
                if doc_path.is_file():
                    try:
                        print(f"  📄 Loading: {doc_path.name}")

                        # Read document content
                        content = doc_path.read_text(encoding="utf-8")

                        # Create metadata
                        metadata = {
                            "source": str(doc_path),
                            "category": category_id,
                            "category_name": category_info["name"],
                            "filename": doc_path.name,
                            "file_type": doc_path.suffix,
                        }

                        # Add to knowledge base
                        await kb.add_document(
                            content=content,
                            metadata=metadata,
                            doc_id=f"{category_id}/{doc_path.name}",
                        )

                        documents_loaded += 1

                    except Exception as e:
                        print(f"  ❌ Error loading {doc_path}: {e}")

    print(f"\n✅ Loaded {documents_loaded} documents into knowledge base")

    # Create search index
    print("\n🔍 Creating search index...")
    await kb.create_search_index()

    print("\n🎉 Knowledge base setup complete!")


if __name__ == "__main__":
    # Set up environment
    import sys

    sys.path.insert(0, "/app")
    sys.path.insert(0, "/app/src")

    # Run loader
    asyncio.run(load_documents_to_knowledge_base())
