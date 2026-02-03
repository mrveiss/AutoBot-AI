#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Upload documentation files directly to knowledge base using file upload API.
Uses concurrent uploads for better performance.
"""

import glob
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

import requests


@dataclass
class UploadResult:
    """Result of a file upload operation."""
    file_path: str
    rel_path: str
    success: bool
    error: Optional[str] = None


def upload_single_file(file_path: str, project_root: str, api_url: str) -> UploadResult:
    """Upload a single file to the knowledge base."""
    rel_path = os.path.relpath(file_path, project_root)
    try:
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, "text/plain")}
            resp = requests.post(
                f"{api_url}/api/knowledge_base/add_file",
                files=files,
                timeout=15,
            )
            if resp.status_code == 200:
                return UploadResult(file_path=file_path, rel_path=rel_path, success=True)
            else:
                return UploadResult(
                    file_path=file_path,
                    rel_path=rel_path,
                    success=False,
                    error=resp.text
                )
    except Exception as e:
        return UploadResult(
            file_path=file_path,
            rel_path=rel_path,
            success=False,
            error=str(e)
        )


def upload_files_batch(files: list, project_root: str, api_url: str, max_workers: int = 5) -> list:
    """Upload multiple files concurrently using ThreadPoolExecutor."""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(upload_single_file, f, project_root, api_url): f
            for f in files
        }
        for future in as_completed(future_to_file):
            results.append(future.result())
    return results


def upload_docs():
    """Upload documentation files to knowledge base via file upload API."""
    project_root = "/home/kali/Desktop/AutoBot"
    api_url = "http://localhost:8001"  # Use proper URL from config

    # Find documentation files
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

    # Upload files concurrently (first 10)
    files_to_upload = filtered_files[:10]
    print(f"Uploading {len(files_to_upload)} files concurrently...")

    results = upload_files_batch(files_to_upload, project_root, api_url)

    # Display results
    added_count = 0
    for result in results:
        if result.success:
            print(f"✓ Uploaded: {result.rel_path}")
            added_count += 1
        else:
            print(f"❌ Failed to upload {result.rel_path}: {result.error}")

    print(f"\n✓ Successfully uploaded {added_count} documents")

    # Test search after upload (batch the two searches)
    if added_count > 0:
        try:
            search_queries = [
                {"query": "installation", "limit": 3},
                {"query": "debian", "limit": 3},
            ]

            def run_search(query_data):
                resp = requests.post(
                    f"{api_url}/api/knowledge_base/search",
                    json=query_data,
                    timeout=5,
                )
                return query_data["query"], resp

            # Run searches concurrently
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(run_search, q) for q in search_queries]
                for future in as_completed(futures):
                    query, resp = future.result()
                    if resp.status_code == 200:
                        results = resp.json()
                        print(
                            f"✓ Search test: found {len(results.get('results', []))} results for '{query}'"
                        )
                    else:
                        print(f"❌ Search test failed for '{query}': {resp.text}")

        except Exception as e:
            print(f"❌ Search test error: {str(e)}")


if __name__ == "__main__":
    upload_docs()
