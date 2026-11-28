#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Simple script to populate KB with docs, bypassing Redis issues.
Uses concurrent uploads for better performance.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from autobot_shared.paths import project_root
from kb_api_upload import API_URL, upload_docs  # the one uploader (#19339)
from populate_knowledge_base import collect_documentation_files



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
    # #14517: was a shell placeholder in a plain string literal, so every glob below
    # matched nothing and the run added no documents while reporting success. Named
    # ``root``: assigning to the imported ``project_root`` would shadow it as a
    # local and raise UnboundLocalError on the call itself.
    root = str(project_root())
    # The one documentation set and exclude list: the canonical populate script's (#19339).
    filtered_files = collect_documentation_files(Path(root))

    print(f"Found {len(filtered_files)} documentation files")

    # Add documents concurrently (first 15)
    files_to_add = filtered_files[:15]
    print(f"Adding {len(files_to_add)} documents concurrently...")

    try:
        results = upload_docs(files_to_add, root, "Project Docs")

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
