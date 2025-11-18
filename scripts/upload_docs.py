#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Upload documentation files directly to knowledge base using file upload API.
"""

import os
import glob
import requests
from src.constants import NetworkConstants, ServiceURLs


def upload_docs():
    project_root = "/home/kali/Desktop/AutoBot"

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

    added_count = 0

    for file_path in filtered_files[:10]:  # First 10 files
        try:
            rel_path = os.path.relpath(file_path, project_root)

            # Upload file
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f, "text/plain")}

                resp = requests.post(
                    "ServiceURLs.BACKEND_LOCAL/api/knowledge_base/add_file",
                    files=files,
                    timeout=15,
                )

                if resp.status_code == 200:
                    print(f"✓ Uploaded: {rel_path}")
                    added_count += 1
                else:
                    print(f"❌ Failed to upload {rel_path}: {resp.text}")

        except Exception as e:
            print(f"❌ Error uploading {file_path}: {str(e)}")

    print(f"\n✓ Successfully uploaded {added_count} documents")

    # Test search after upload
    if added_count > 0:
        try:
            test_resp = requests.post(
                "ServiceURLs.BACKEND_LOCAL/api/knowledge_base/search",
                json={"query": "installation", "limit": 3},
                timeout=5,
            )
            if test_resp.status_code == 200:
                results = test_resp.json()
                print(
                    f"✓ Search test: found {len(results.get('results', []))} results for 'installation'"
                )

                # Try debian search too
                debian_resp = requests.post(
                    "ServiceURLs.BACKEND_LOCAL/api/knowledge_base/search",
                    json={"query": "debian", "limit": 3},
                    timeout=5,
                )
                if debian_resp.status_code == 200:
                    debian_results = debian_resp.json()
                    print(
                        f"✓ Search test: found {len(debian_results.get('results', []))} results for 'debian'"
                    )
            else:
                print(f"❌ Search test failed: {test_resp.text}")
        except Exception as e:
            print(f"❌ Search test error: {str(e)}")


if __name__ == "__main__":
    upload_docs()
