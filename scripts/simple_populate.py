#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Simple script to populate KB with docs, bypassing Redis issues.
Uses concurrent uploads for better performance.
"""

import glob
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set environment to force ChromaDB
os.environ["AUTOBOT_VECTOR_STORE_TYPE"] = "chroma"

import requests

API_URL = "http://localhost:8001"


@dataclass
class AddResult:
    """Result of adding a document."""
    rel_path: str
    success: bool
    error: Optional[str] = None


def add_single_doc(file_path: str, project_root: str) -> AddResult:
    """Add a single document to the knowledge base."""
    rel_path = os.path.relpath(file_path, project_root)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.strip():
            return AddResult(rel_path=rel_path, success=False, error="Empty file")

        data = {
            "text": content,
            "title": f"Project Docs: {rel_path}",
            "source": "project-documentation",
        }

        resp = requests.post(
            f"{API_URL}/api/knowledge_base/add_text",
            json=data,
            timeout=10,
        )

        if resp.status_code == 200:
            return AddResult(rel_path=rel_path, success=True)
        else:
            return AddResult(rel_path=rel_path, success=False, error=resp.text)

    except Exception as e:
        return AddResult(rel_path=rel_path, success=False, error=str(e))


def add_docs_batch(files: list, project_root: str, max_workers: int = 5) -> list:
    """Add multiple documents concurrently."""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(add_single_doc, f, project_root): f for f in files
        }
        for future in as_completed(future_to_file):
            results.append(future.result())
    return results


def main():
    """Main entry point."""
    print("=== Simple Knowledge Base Population ===")

    # Check if system is running
    try:
        resp = requests.get(f"{API_URL}/api/system/health", timeout=2)
        print(f"✓ Backend is running: {resp.status_code}")
    except Exception:
        print("❌ Backend not running")
        print("Run: ./run_agent.sh")
        return

    # Find all documentation files
    project_root = "/home/kali/Desktop/AutoBot"
    doc_files = []

    patterns = ["README.md", "CLAUDE.md", "docs/**/*.md"]
    for pattern in patterns:
        files = glob.glob(os.path.join(project_root, pattern), recursive=True)
        doc_files.extend(files)

    # Remove duplicates and filter
    unique_files = list(set(doc_files))
    filtered_files = [
        f for f in unique_files if os.path.isfile(f) and "node_modules" not in f
    ]

    print(f"Found {len(filtered_files)} documentation files")

    # Add documents concurrently (first 15)
    files_to_add = filtered_files[:15]
    print(f"Adding {len(files_to_add)} documents concurrently...")

    try:
        results = add_docs_batch(files_to_add, project_root)

        added_count = 0
        for result in results:
            if result.success:
                print(f"✓ Added: {result.rel_path}")
                added_count += 1
            elif result.error != "Empty file":
                print(f"❌ Failed: {result.rel_path}: {result.error}")

        print(f"\n✓ Successfully added {added_count} documents via API")

        # Test search
        if added_count > 0:
            test_resp = requests.post(
                f"{API_URL}/api/knowledge_base/search",
                json={"query": "autobot", "limit": 2},
                timeout=5,
            )
            if test_resp.status_code == 200:
                search_results = test_resp.json()
                print(f"✓ Search test: found {len(search_results.get('results', []))} results")
            else:
                print(f"❌ Search test failed: {test_resp.text}")

    except requests.exceptions.RequestException:
        print("❌ Cannot connect to API, backend may not be running")
        print("Run: ./run_agent.sh")

    except Exception as e:
        print(f"❌ Error: {str(e)}")


if __name__ == "__main__":
    main()
