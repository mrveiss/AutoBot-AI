#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Fix search by using simple text storage in Redis facts that can be searched.
Uses concurrent uploads for better performance.
"""

import glob
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

import requests

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API_URL = "http://localhost:8001"


@dataclass
class UploadResult:
    """Result of uploading a document."""
    rel_path: str
    success: bool
    error: Optional[str] = None


@dataclass
class SearchResult:
    """Result of a search query."""
    query: str
    count: int
    error: Optional[str] = None


def upload_single_doc(file_path: str, project_root: str) -> UploadResult:
    """Upload a single document as a searchable fact."""
    rel_path = os.path.relpath(file_path, project_root)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.strip():
            return UploadResult(rel_path=rel_path, success=False, error="Empty file")

        searchable_text = f"FILE: {rel_path}\nTITLE: {os.path.basename(file_path)}\nCONTENT:\n{content}"

        data = {
            "text": searchable_text,
            "title": f"Documentation: {rel_path}",
            "source": "project-documentation",
        }

        resp = requests.post(
            f"{API_URL}/api/knowledge_base/add_text",
            json=data,
            timeout=10,
        )

        if resp.status_code == 200:
            return UploadResult(rel_path=rel_path, success=True)
        else:
            return UploadResult(rel_path=rel_path, success=False, error=resp.text)

    except Exception as e:
        return UploadResult(rel_path=rel_path, success=False, error=str(e))


def upload_docs_batch(files: list, project_root: str, max_workers: int = 5) -> list:
    """Upload multiple documents concurrently."""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(upload_single_doc, f, project_root): f for f in files
        }
        for future in as_completed(future_to_file):
            results.append(future.result())
    return results


def search_single_query(query: str) -> SearchResult:
    """Execute a single search query."""
    try:
        resp = requests.get(
            f"{API_URL}/api/knowledge_base/get_fact?query={query}",
            timeout=5,
        )
        if resp.status_code == 200:
            results = resp.json()
            facts = results.get("facts", [])
            return SearchResult(query=query, count=len(facts))
        else:
            return SearchResult(query=query, count=0, error="fact search not available")
    except Exception as e:
        return SearchResult(query=query, count=0, error=str(e))


def search_queries_batch(queries: list, max_workers: int = 4) -> list:
    """Execute multiple search queries concurrently."""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_query = {
            executor.submit(search_single_query, q): q for q in queries
        }
        for future in as_completed(future_to_query):
            results.append(future.result())
    return results


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
    print(f"Uploading {len(filtered_files)} documents concurrently...")

    # Upload all documents concurrently
    results = upload_docs_batch(filtered_files, project_root)

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
