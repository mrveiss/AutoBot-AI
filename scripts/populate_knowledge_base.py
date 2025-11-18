#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Script to populate the knowledge base with all project documentation.
"""

import asyncio
import os
import sys
import glob
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge_base import KnowledgeBase


async def add_documentation_to_kb():
    """Add all project documentation to the knowledge base."""
    kb = KnowledgeBase()
    await kb.ainit()

    # Base paths for documentation
    project_root = Path("/home/kali/Desktop/AutoBot")

    # Define documentation patterns to include
    doc_patterns = [
        "README.md",
        "CLAUDE.md",
        "docs/**/*.md",
        "prompts/**/*.md",
        "*.md",  # Any markdown files in root
    ]

    # Files to exclude (e.g., test results, node_modules)
    exclude_patterns = [
        "**/node_modules/**",
        "**/venv/**",
        "**/test-results/**",
        "**/playwright-report/**",
        "**/.pytest_cache/**",
    ]

    all_files = []

    # Collect all documentation files
    for pattern in doc_patterns:
        files = glob.glob(str(project_root / pattern), recursive=True)
        all_files.extend(files)

    # Remove duplicates and filter out excluded patterns
    unique_files = set(all_files)
    filtered_files = []

    for file_path in unique_files:
        # Check if file should be excluded
        should_exclude = False
        for exclude in exclude_patterns:
            if glob.fnmatch.fnmatch(file_path, exclude):
                should_exclude = True
                break

        if not should_exclude and os.path.isfile(file_path):
            filtered_files.append(file_path)

    print(f"Found {len(filtered_files)} documentation files to add to knowledge base")

    # Add each file to the knowledge base
    success_count = 0
    error_count = 0

    for file_path in sorted(filtered_files):
        try:
            # Get relative path for better organization
            rel_path = os.path.relpath(file_path, project_root)

            # Determine category based on path
            if rel_path.startswith("docs/developer"):
                category = "developer-docs"
            elif rel_path.startswith("docs/user_guide"):
                category = "user-guide"
            elif rel_path.startswith("docs/reports"):
                category = "reports"
            elif rel_path.startswith("prompts"):
                category = "prompts"
            elif rel_path == "README.md":
                category = "main-readme"
            elif rel_path == "CLAUDE.md":
                category = "claude-instructions"
            else:
                category = "documentation"

            metadata = {
                "source": "project-docs",
                "category": category,
                "relative_path": rel_path,
                "doc_type": "markdown",
            }

            print(f"Adding: {rel_path} [{category}]")

            result = await kb.add_file(
                file_path=file_path,
                file_type="txt",  # Markdown files are treated as text
                metadata=metadata,
            )

            if result["status"] == "success":
                success_count += 1
            else:
                error_count += 1
                print(f"  Error: {result.get('message', 'Unknown error')}")

        except Exception as e:
            error_count += 1
            print(f"  Exception adding {file_path}: {str(e)}")

    print(f"\nKnowledge base population complete!")
    print(f"Successfully added: {success_count} files")
    print(f"Errors: {error_count} files")

    # Test search functionality
    print("\nTesting search functionality...")
    test_queries = [
        "installation",
        "configuration",
        "embedding",
        "redis",
        "ollama",
        "vue",
        "debian",
    ]

    for query in test_queries:
        results = await kb.search(query, n_results=2)
        print(f"\nSearch for '{query}': {len(results)} results")
        if results:
            print(
                f"  First result: {results[0].get('metadata', {}).get('relative_path', 'Unknown')}"
            )


if __name__ == "__main__":
    asyncio.run(add_documentation_to_kb())
