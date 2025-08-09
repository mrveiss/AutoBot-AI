#!/usr/bin/env python3
"""
Simple script to populate KB with docs, bypassing Redis issues.
"""

import os
import sys
import glob
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set environment to force ChromaDB
os.environ["AUTOBOT_VECTOR_STORE_TYPE"] = "chroma"

print("=== Simple Knowledge Base Population ===")

# Check if system is running
import requests

try:
    resp = requests.get("http://localhost:8001/api/system/health", timeout=2)
    print(f"✓ Backend is running: {resp.status_code}")
except:
    print("❌ Backend not running, starting with direct KB access")

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

# Use requests to add via API if backend is running
try:
    added_count = 0
    for file_path in filtered_files[:15]:  # Start with first 15
        try:
            rel_path = os.path.relpath(file_path, project_root)

            # Read file content
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if not content.strip():
                continue

            # Use the add_text API endpoint
            data = {
                "text": content,
                "title": f"Project Docs: {rel_path}",
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
                print(f"❌ Failed to add {rel_path}: {resp.text}")

        except Exception as e:
            print(f"❌ Error with {file_path}: {str(e)}")

    print(f"\n✓ Successfully added {added_count} documents via API")

    # Test search
    if added_count > 0:
        test_resp = requests.post(
            "http://localhost:8001/api/knowledge_base/search",
            json={"query": "autobot", "limit": 2},
            timeout=5,
        )
        if test_resp.status_code == 200:
            results = test_resp.json()
            print(f"✓ Search test: found {len(results.get('results', []))} results")
        else:
            print(f"❌ Search test failed: {test_resp.text}")

except requests.exceptions.RequestException:
    print("❌ Cannot connect to API, backend may not be running")
    print("Run: ./run_agent.sh")

except Exception as e:
    print(f"❌ Error: {str(e)}")
