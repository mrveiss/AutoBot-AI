#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Fix search by using simple text storage in Redis facts that can be searched.
Uses concurrent uploads for better performance.
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Runs from any directory with no PYTHONPATH: put the repository root on the path for
# `autobot_shared` (#18964).
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from autobot_shared.paths import project_root  # noqa: E402
from kb_api_upload import API_URL, upload_docs  # noqa: E402  # the one uploader (#19339)
from populate_knowledge_base import collect_documentation_files  # noqa: E402



@dataclass
class QueryResult:
    """Result of a search query."""

    query: str
    count: int
    error: Optional[str] = None


def _searchable_text(rel_path: str, file_path: str, content: str) -> str:
    """The fact text this script stores: a FILE/TITLE header the plain-text search can match."""
    return f"FILE: {rel_path}\nTITLE: {os.path.basename(file_path)}\nCONTENT:\n{content}"


def search_single_query(query: str) -> QueryResult:
    """Execute a single search query."""
    try:
        resp = requests.get(
            f"{API_URL}/api/knowledge_base/get_fact?query={query}",
            timeout=5,
        )
        if resp.status_code == 200:
            results = resp.json()
            facts = results.get("facts", [])
            return QueryResult(query=query, count=len(facts))
        else:
            return QueryResult(query=query, count=0, error="fact search not available")
    except Exception as e:
        return QueryResult(query=query, count=0, error=str(e))


def search_queries_batch(queries: list, max_workers: int = 4) -> list:
    """Execute multiple search queries concurrently."""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_query = {executor.submit(search_single_query, q): q for q in queries}
        for future in as_completed(future_to_query):
            results.append(future.result())
    return results


def upload_docs_as_searchable_facts():
    """Upload docs as facts that can be searched via simple text matching."""
    # #14517: was a shell placeholder in a plain string literal, so every glob below
    # matched nothing and the run reported "Found 0 documentation files" as success.
    # Named ``root``: assigning to the imported ``project_root`` would make it a
    # function-local name and raise UnboundLocalError on the call itself.
    root = str(project_root())

    # The one documentation set and exclude list: the canonical populate script's (#19339).
    filtered_files = collect_documentation_files(Path(root))

    print(f"Found {len(filtered_files)} documentation files")
    print(f"Uploading {len(filtered_files)} documents concurrently...")

    # Upload all documents concurrently
    results = upload_docs(filtered_files, root, "Documentation", render=_searchable_text)

    added_count = 0
    for result in results:
        if result.success:
            print(f"✓ Added: {result.rel_path}")
            added_count += 1
        elif result.error != "Empty file":
            print(f"❌ Failed: {result.rel_path} - {result.error}")

    print(f"\n✓ Added {added_count} documents as searchable facts")

    # Test fact-based search concurrently
    print("\n=== Testing Fact Search ===")
    test_queries = ["debian", "installation", "autobot", "configuration"]

    search_results = search_queries_batch(test_queries)

    for result in search_results:
        if result.error:
            print(f"Query '{result.query}': {result.error}")
        else:
            print(f"Query '{result.query}': {result.count} facts found")


if __name__ == "__main__":
    upload_docs_as_searchable_facts()
