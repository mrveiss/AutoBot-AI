#!/usr/bin/env python3
"""Sync documentation changes to knowledge base"""

import os
import sys
import asyncio
import json
import glob
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge_base import KnowledgeBase


async def sync_docs():
    """Re-sync all documentation to ensure KB is current"""

    print("=== Knowledge Base Documentation Sync ===")

    # Clear existing project docs
    kb = KnowledgeBase()
    await kb.ainit()

    # Get all current facts
    all_facts = await kb.get_all_facts()
    removed_count = 0

    # Remove old project documentation facts
    print("Removing outdated documentation entries...")
    for fact in all_facts:
        metadata = fact.get("metadata", {})
        if metadata.get("source") in ["project-docs", "project-documentation"]:
            await kb.delete_fact(fact["id"])
            removed_count += 1

    print(f"✓ Removed {removed_count} outdated documentation entries")

    # Find all current documentation files
    project_root = "/home/kali/Desktop/AutoBot"
    doc_patterns = ["README.md", "CLAUDE.md", "docs/**/*.md"]

    all_files = []
    for pattern in doc_patterns:
        files = glob.glob(os.path.join(project_root, pattern), recursive=True)
        all_files.extend(files)

    # Remove duplicates and filter
    unique_files = list(set(all_files))
    filtered_files = [
        f for f in unique_files if os.path.isfile(f) and "node_modules" not in f
    ]

    print(f"Found {len(filtered_files)} documentation files to sync")

    # Add all current documentation via facts (more reliable than vector store)
    success_count = 0

    for file_path in sorted(filtered_files):
        try:
            rel_path = os.path.relpath(file_path, project_root)

            # Read file content
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if not content.strip():
                continue

            # Create enhanced searchable content
            searchable_text = f"FILE: {rel_path}\\nTITLE: {os.path.basename(file_path)}\\nCONTENT:\\n{content}"

            # Determine category
            if "user_guide" in rel_path:
                category = "user-guide"
            elif "developer" in rel_path:
                category = "developer-docs"
            elif "reports" in rel_path:
                category = "reports"
            elif rel_path in ["README.md", "CLAUDE.md"]:
                category = "project-overview"
            else:
                category = "documentation"

            metadata = {
                "source": "project-documentation",
                "category": category,
                "relative_path": rel_path,
                "filename": os.path.basename(file_path),
                "sync_time": datetime.now().isoformat(),
                "file_size": len(content),
            }

            # Store as searchable fact
            result = await kb.store_fact(searchable_text, metadata)

            if result["status"] == "success":
                success_count += 1
                print(f"✓ Synced: {rel_path} [{category}]")
            else:
                print(f"❌ Failed to sync {rel_path}: {result['message']}")

        except Exception as e:
            print(f"❌ Error syncing {file_path}: {str(e)}")

    print(f"\\n=== Sync Results ===")
    print(f"✓ Successfully synced: {success_count} documents")
    print(f"📁 Categories: {len(set(metadata.get('category') for metadata in []))}")

    if success_count > 0:
        # Save sync timestamp
        sync_data = {
            "last_sync": datetime.now().isoformat(),
            "documents_synced": success_count,
            "method": "full-resync",
            "removed_outdated": removed_count,
            "total_files_found": len(filtered_files),
        }

        os.makedirs("data", exist_ok=True)
        with open("data/kb_sync_state.json", "w") as f:
            json.dump(sync_data, f, indent=2)

        print(f"✅ Sync state saved to data/kb_sync_state.json")

        # Test search functionality
        print("\\n=== Testing Search Functionality ===")
        test_queries = ["debian", "installation", "autobot", "configuration"]

        for query in test_queries:
            try:
                results = await kb.get_fact(query=query)
                print(f"Search '{query}': {len(results)} results found")
            except Exception as e:
                print(f"Search '{query}': error - {str(e)}")

        print("\\n🎉 Knowledge base documentation sync completed successfully!")
        print("Users can now search for updated documentation content.")
        return True
    else:
        print("\\n💥 Knowledge base documentation sync failed!")
        return False


async def incremental_sync():
    """Sync only files that have changed since last sync (future enhancement)"""
    print("=== Incremental Knowledge Base Sync ===")

    # Load last sync state
    sync_state_path = "data/kb_sync_state.json"
    if not os.path.exists(sync_state_path):
        print("No previous sync state found, performing full sync")
        return await sync_docs()

    with open(sync_state_path, "r") as f:
        sync_state = json.load(f)

    last_sync_time = datetime.fromisoformat(sync_state["last_sync"])
    print(f"Last sync: {last_sync_time}")

    # Find files modified since last sync
    project_root = "/home/kali/Desktop/AutoBot"
    doc_patterns = ["README.md", "CLAUDE.md", "docs/**/*.md"]

    changed_files = []
    for pattern in doc_patterns:
        files = glob.glob(os.path.join(project_root, pattern), recursive=True)
        for file_path in files:
            if os.path.isfile(file_path):
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_mtime > last_sync_time:
                    changed_files.append(file_path)

    if not changed_files:
        print("✅ No documentation changes detected since last sync")
        return True

    print(f"Found {len(changed_files)} changed files:")
    for file_path in changed_files:
        print(f"  📝 {os.path.relpath(file_path, project_root)}")

    # For now, fall back to full sync if any changes detected
    # TODO: Implement true incremental sync
    print("\\nPerforming full sync due to detected changes...")
    return await sync_docs()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sync documentation to knowledge base")
    parser.add_argument(
        "--incremental",
        "-i",
        action="store_true",
        help="Perform incremental sync (only changed files)",
    )
    parser.add_argument(
        "--test", "-t", action="store_true", help="Test search functionality after sync"
    )

    args = parser.parse_args()

    if args.incremental:
        success = asyncio.run(incremental_sync())
    else:
        success = asyncio.run(sync_docs())

    sys.exit(0 if success else 1)
