#!/usr/bin/env python3
"""
Fix search by using simple text storage in Redis facts that can be searched.
"""

import asyncio
import os
import sys
import glob
import requests
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def upload_docs_as_searchable_facts():
    """Upload docs as facts that can be searched via simple text matching."""

    project_root = "/home/kali/Desktop/AutoBot"

    # Find all documentation files
    doc_files = []
    patterns = ["README.md", "CLAUDE.md", "docs/**/*.md"]
    for pattern in patterns:
        files = glob.glob(os.path.join(project_root, pattern), recursive=True)
        doc_files.extend(files)

    filtered_files = [
        f for f in set(doc_files) if os.path.isfile(f) and "node_modules" not in f
    ]

    print(f"Found {len(filtered_files)} documentation files")

    added_count = 0

    for file_path in filtered_files:
        try:
            rel_path = os.path.relpath(file_path, project_root)

            # Read file content
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if not content.strip():
                continue

            # Add searchable keywords from filename and path for better matching
            searchable_text = f"FILE: {rel_path}\nTITLE: {os.path.basename(file_path)}\nCONTENT:\n{content}"

            # Use add_text API to store as searchable fact
            data = {
                "text": searchable_text,
                "title": f"Documentation: {rel_path}",
                "source": "project-documentation",
            }

            resp = requests.post(
                "http://localhost:8001/api/knowledge_base/add_text",
                json=data,
                timeout=10,
            )

            if resp.status_code == 200:
                print(f"✓ Added: {rel_path}")
                added_count += 1
            else:
                print(f"❌ Failed: {rel_path} - {resp.text}")

        except Exception as e:
            print(f"❌ Error with {file_path}: {str(e)}")

    print(f"\n✓ Added {added_count} documents as searchable facts")

    # Test fact-based search
    print(f"\n=== Testing Fact Search ===")

    # The facts should now be searchable via simple text matching
    # Let's check if we can find documents by searching facts
    test_queries = ["debian", "installation", "autobot", "configuration"]

    for query in test_queries:
        # Try to search facts via get_fact with query parameter if available
        try:
            # Check if there's a fact search endpoint
            resp = requests.get(
                f"http://localhost:8001/api/knowledge_base/get_fact?query={query}",
                timeout=5,
            )
            if resp.status_code == 200:
                results = resp.json()
                facts = results.get("facts", [])
                print(f"Query '{query}': {len(facts)} facts found")
            else:
                print(f"Query '{query}': fact search not available")
        except Exception as e:
            print(f"Query '{query}': error - {str(e)}")


if __name__ == "__main__":
    upload_docs_as_searchable_facts()
