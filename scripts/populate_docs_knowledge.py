#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Populate knowledge base with AutoBot documentation from docs/ folder.
This script indexes all the documentation in the docs folder to make it
searchable through the knowledge interface.
"""

import asyncio
import os
import sys
import glob
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def populate_docs_knowledge():
    """Populate knowledge base with documentation from docs/ folder."""

    print("=== Populating Knowledge Base with AutoBot Documentation ===")

    # Import knowledge base (will use current Redis setup)
    from src.knowledge_base import KnowledgeBase

    try:
        kb = KnowledgeBase()
        print(f"✓ Knowledge base initialized")

        # Wait for initialization
        await asyncio.sleep(2)

        # Find all documentation files in docs folder
        project_root = Path("/home/kali/Desktop/AutoBot")
        docs_patterns = [
            "docs/**/*.md",
            "CLAUDE.md",
            "README.md"
        ]

        exclude_patterns = [
            "**/node_modules/**",
            "**/venv/**",
            "**/test-results/**",
            "**/playwright-report/**",
            "**/.pytest_cache/**",
            "**/system-state.md"  # Skip this as it's status updates, not docs
        ]

        all_files = []
        for pattern in docs_patterns:
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

        print(f"Found {len(filtered_files)} documentation files to index")

        # Process each documentation file
        successful_adds = 0
        failed_adds = 0

        for file_path in sorted(filtered_files):
            try:
                # Read file content
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                if not content.strip():
                    print(f"⚠️  Skipping empty file: {file_path}")
                    continue

                # Determine category based on file path
                rel_path = os.path.relpath(file_path, project_root)
                if rel_path.startswith("docs/api/"):
                    category = "api_documentation"
                elif rel_path.startswith("docs/architecture/"):
                    category = "architecture_documentation"
                elif rel_path.startswith("docs/developer/"):
                    category = "developer_documentation"
                elif rel_path.startswith("docs/features/"):
                    category = "feature_documentation"
                elif rel_path.startswith("docs/security/"):
                    category = "security_documentation"
                elif rel_path.startswith("docs/troubleshooting/"):
                    category = "troubleshooting_documentation"
                elif rel_path.startswith("docs/agents/"):
                    category = "agent_documentation"
                elif rel_path == "CLAUDE.md":
                    category = "project_instructions"
                elif rel_path == "README.md":
                    category = "project_overview"
                else:
                    category = "general_documentation"

                # Add to knowledge base
                await kb.add_document(
                    content=content,
                    metadata={
                        "source": rel_path,
                        "category": category,
                        "file_type": "markdown",
                        "indexed_by": "populate_docs_knowledge.py"
                    }
                )

                print(f"✓ Added: {rel_path} (category: {category})")
                successful_adds += 1

            except Exception as e:
                print(f"❌ Failed to add {file_path}: {e}")
                failed_adds += 1

        print(f"\n=== Documentation Population Complete ===")
        print(f"✓ Successfully added: {successful_adds} documents")
        if failed_adds > 0:
            print(f"❌ Failed to add: {failed_adds} documents")

        # Get updated stats
        stats = await kb.get_stats()
        print(f"📊 Total documents in knowledge base: {stats.get('total_documents', 'unknown')}")

        return {
            "success": True,
            "documents_added": successful_adds,
            "documents_failed": failed_adds,
            "total_documents": stats.get('total_documents', 0)
        }

    except Exception as e:
        print(f"❌ Error during documentation population: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def main():
    """Main entry point"""
    result = await populate_docs_knowledge()

    if result["success"]:
        print(f"\n🎉 Documentation population completed successfully!")
        print(f"   Added {result['documents_added']} documents to knowledge base")
    else:
        print(f"\n💥 Documentation population failed: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
