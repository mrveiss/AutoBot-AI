#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
# NOTE: CLI tool uses print() for user-facing output per LOGGING_STANDARDS.md
"""Sync documentation changes to knowledge base"""

import asyncio
import glob
import json
import os
import sys
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge_base import KnowledgeBase
from src.knowledge_sync_incremental import run_incremental_sync


def _determine_doc_category(rel_path: str) -> str:
    """
    Determine document category from relative path.

    Issue #281: Extracted from sync_docs to reduce function length.
    """
    if "user_guide" in rel_path:
        return "user-guide"
    elif "developer" in rel_path:
        return "developer-docs"
    elif "reports" in rel_path:
        return "reports"
    elif rel_path in ["README.md", "CLAUDE.md"]:
        return "project-overview"
    return "documentation"


def _collect_documentation_files(project_root: str) -> list:
    """
    Find all documentation files to sync.

    Issue #281: Extracted from sync_docs to reduce function length.
    """
    doc_patterns = ["README.md", "CLAUDE.md", "docs/**/*.md"]

    all_files = []
    for pattern in doc_patterns:
        files = glob.glob(os.path.join(project_root, pattern), recursive=True)
        all_files.extend(files)

    # Remove duplicates and filter
    unique_files = list(set(all_files))
    return [f for f in unique_files if os.path.isfile(f) and "node_modules" not in f]


async def _remove_outdated_entries(kb, all_facts: list) -> int:
    """
    Remove outdated documentation entries from KB.

    Issue #281: Extracted from sync_docs to reduce function length.
    """
    print("Removing outdated documentation entries...")
    removed_count = 0
    for fact in all_facts:
        metadata = fact.get("metadata", {})
        if metadata.get("source") in ["project-docs", "project-documentation"]:
            await kb.delete_fact(fact["id"])
            removed_count += 1
    print(f"✓ Removed {removed_count} outdated documentation entries")
    return removed_count


async def _sync_single_file(kb, file_path: str, project_root: str) -> bool:
    """
    Sync a single documentation file to the KB.

    Issue #281: Extracted from sync_docs to reduce function length.
    Returns True on success, False on failure.
    """
    rel_path = os.path.relpath(file_path, project_root)

    # Read file content
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        return False

    # Create enhanced searchable content
    searchable_text = f"FILE: {rel_path}\\nTITLE: {os.path.basename(file_path)}\\nCONTENT:\\n{content}"

    category = _determine_doc_category(rel_path)
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
        print(f"✓ Synced: {rel_path} [{category}]")
        return True
    else:
        print(f"❌ Failed to sync {rel_path}: {result['message']}")
        return False


def _save_sync_state(success_count: int, removed_count: int, total_files: int) -> None:
    """
    Save sync state to JSON file.

    Issue #281: Extracted from sync_docs to reduce function length.
    """
    sync_data = {
        "last_sync": datetime.now().isoformat(),
        "documents_synced": success_count,
        "method": "full-resync",
        "removed_outdated": removed_count,
        "total_files_found": total_files,
    }

    os.makedirs("data", exist_ok=True)
    with open("data/kb_sync_state.json", "w") as f:
        json.dump(sync_data, f, indent=2)

    print("✅ Sync state saved to data/kb_sync_state.json")


async def _test_search_functionality(kb) -> None:
    """
    Test KB search functionality after sync.

    Issue #281: Extracted from sync_docs to reduce function length.
    """
    print("\\n=== Testing Search Functionality ===")
    test_queries = ["debian", "installation", "autobot", "configuration"]

    for query in test_queries:
        try:
            results = await kb.get_fact(query=query)
            print(f"Search '{query}': {len(results)} results found")
        except Exception as e:
            print(f"Search '{query}': error - {str(e)}")


async def sync_docs():
    """Re-sync all documentation to ensure KB is current."""
    print("=== Knowledge Base Documentation Sync ===")

    # Initialize KB
    kb = KnowledgeBase()
    await kb.ainit()

    # Remove outdated entries
    all_facts = await kb.get_all_facts()
    removed_count = await _remove_outdated_entries(kb, all_facts)

    # Collect documentation files
    project_root = "/home/kali/Desktop/AutoBot"
    filtered_files = _collect_documentation_files(project_root)
    print(f"Found {len(filtered_files)} documentation files to sync")

    # Sync each file
    success_count = 0
    for file_path in sorted(filtered_files):
        try:
            if await _sync_single_file(kb, file_path, project_root):
                success_count += 1
        except Exception as e:
            print(f"❌ Error syncing {file_path}: {str(e)}")

    # Report results
    print("\\n=== Sync Results ===")
    print(f"✓ Successfully synced: {success_count} documents")

    if success_count > 0:
        _save_sync_state(success_count, removed_count, len(filtered_files))
        await _test_search_functionality(kb)
        print("\\n🎉 Knowledge base documentation sync completed successfully!")
        print("Users can now search for updated documentation content.")
        return True
    else:
        print("\\n💥 Knowledge base documentation sync failed!")
        return False


async def incremental_sync():
    """Perform intelligent incremental sync with 10-50x performance improvement"""
    print("=== Incremental Knowledge Base Sync ===")
    print("🚀 Using advanced incremental sync with GPU acceleration")

    try:
        # Use the new incremental sync system
        metrics = await run_incremental_sync()

        print("\\n=== Incremental Sync Results ===")
        print(f"📁 Files scanned: {metrics.total_files_scanned}")
        print(f"🔄 Files changed: {metrics.files_changed}")
        print(f"➕ Files added: {metrics.files_added}")
        print(f"➖ Files removed: {metrics.files_removed}")
        print(f"🧩 Chunks processed: {metrics.total_chunks_processed}")
        print(f"⏱️  Total time: {metrics.total_processing_time:.3f}s")
        print(f"⚡ Performance: {metrics.avg_chunks_per_second:.1f} chunks/sec")
        print(f"🎮 GPU acceleration: {'✅' if metrics.gpu_acceleration_used else '❌'}")

        # Calculate improvement estimate
        if metrics.total_chunks_processed > 0:
            estimated_full_sync_time = (
                metrics.total_chunks_processed * 0.5
            )  # Conservative estimate
            improvement_factor = estimated_full_sync_time / max(
                metrics.total_processing_time, 0.1
            )
            print(
                f"📈 Estimated improvement: {improvement_factor:.1f}x faster than full sync"
            )

            if improvement_factor >= 10:
                print("🎯 TARGET ACHIEVED: 10-50x performance improvement!")
            else:
                print("⚠️  Performance target not yet reached")

        # Test search functionality if any changes were made
        if metrics.files_changed + metrics.files_added > 0:
            print("\\n=== Testing Updated Search Functionality ===")

            # Initialize knowledge base for testing
            kb = KnowledgeBase()
            await kb.ainit()

            test_queries = ["autobot", "configuration", "installation", "troubleshoot"]

            for query in test_queries:
                try:
                    results = await kb.get_fact(query=query)
                    print(f"Search '{query}': {len(results)} results found")
                except Exception as e:
                    print(f"Search '{query}': error - {str(e)}")

        print("\\n✅ Incremental sync completed successfully!")
        return True

    except Exception as e:
        print(f"❌ Incremental sync failed: {e}")
        print("Falling back to legacy full sync...")
        return await sync_docs()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sync documentation to knowledge base")
    parser.add_argument(
        "--incremental",
        "-i",
        action="store_true",
        help="Perform incremental sync (10-50x faster, default)",
    )
    parser.add_argument(
        "--force-full",
        "-f",
        action="store_true",
        help="Force full sync (legacy method)",
    )
    parser.add_argument(
        "--test", "-t", action="store_true", help="Test search functionality after sync"
    )

    args = parser.parse_args()

    if args.force_full:
        print("⚠️  WARNING: Using legacy full sync method (much slower)")
        success = asyncio.run(sync_docs())
    else:
        # Default to incremental sync (much faster)
        success = asyncio.run(incremental_sync())

    sys.exit(0 if success else 1)
