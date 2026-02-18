#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Documentation Knowledge Base Synchronization Script

Detects changes in documentation files and updates the knowledge base:
- Adds new files
- Updates modified files (removes old chunks, adds new ones)
- Removes deleted files
- Handles renamed files

Usage:
    python scripts/utilities/sync_documentation_kb.py [--dry-run] [--watch]

Arguments:
    --dry-run: Preview changes without applying them
    --watch: Continuously monitor for changes (daemon mode)
"""

import asyncio
import hashlib
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from knowledge_base import KnowledgeBase

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DocumentationSyncManager:
    """
    Manages synchronization between file system and knowledge base
    """

    def __init__(self, docs_dir: Path):
        """Initialize documentation sync manager with directory path."""
        self.docs_dir = docs_dir
        self.kb = None
        self.state_file = PROJECT_ROOT / "data" / "kb_sync_state.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self):
        """Initialize knowledge base connection"""
        self.kb = KnowledgeBase()
        await self.kb.initialize()
        logger.info("Knowledge base initialized")

    def load_sync_state(self) -> Dict:
        """
        Load previous sync state from disk

        Returns dict with:
            {
                "file_path": {
                    "content_hash": "sha256...",
                    "indexed_at": "2025-10-22T...",
                    "fact_ids": ["fact_id1", "fact_id2", ...]
                }
            }
        """
        if not self.state_file.exists():
            return {}

        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load sync state: %s", e)
            return {}

    def save_sync_state(self, state: Dict):
        """Save sync state to disk"""
        try:
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
            logger.debug("Sync state saved: %s files tracked", len(state))
        except Exception as e:
            logger.error("Failed to save sync state: %s", e)

    def scan_documentation_files(self) -> Dict[str, str]:
        """
        Scan docs directory and compute content hashes

        Returns:
            Dict[file_path: str, content_hash: str]
        """
        current_files = {}

        for md_file in self.docs_dir.rglob("*.md"):
            if md_file.is_file():
                try:
                    content = md_file.read_text(encoding="utf-8")
                    content_hash = hashlib.sha256(content.encode()).hexdigest()

                    relative_path = str(md_file.relative_to(PROJECT_ROOT))
                    current_files[relative_path] = content_hash

                except Exception as e:
                    logger.warning("Failed to read %s: %s", md_file, e)

        logger.info("Scanned %s documentation files", len(current_files))
        return current_files

    def detect_changes(
        self, current_files: Dict[str, str], previous_state: Dict[str, Dict]
    ) -> Tuple[Set[str], Set[str], Set[str]]:
        """
        Detect what changed between file system and knowledge base

        Returns:
            (added_files, modified_files, deleted_files)
        """
        current_paths = set(current_files.keys())
        previous_paths = set(previous_state.keys())

        # New files
        added = current_paths - previous_paths

        # Deleted files
        deleted = previous_paths - current_paths

        # Modified files (hash changed)
        modified = set()
        for path in current_paths & previous_paths:
            if current_files[path] != previous_state[path].get("content_hash"):
                modified.add(path)

        return added, modified, deleted

    async def remove_document_chunks(self, file_path: str, fact_ids: List[str]):
        """Remove all chunks belonging to a document"""
        removed_count = 0

        for fact_id in fact_ids:
            try:
                # Delete from vector store and Redis
                result = await self.kb.delete_fact(fact_id)
                if result.get("status") == "success":
                    removed_count += 1
            except Exception as e:
                logger.error("Failed to remove fact %s: %s", fact_id, e)

        logger.info(
            "Removed %s/%s chunks for %s", removed_count, len(fact_ids), file_path
        )
        return removed_count

    async def index_document(self, file_path: str) -> Dict:
        """
        Index a single document

        Returns:
            {
                "fact_ids": [list of fact IDs],
                "content_hash": "sha256...",
                "indexed_at": "timestamp"
            }
        """
        full_path = PROJECT_ROOT / file_path

        try:
            content = full_path.read_text(encoding="utf-8")
            content_hash = hashlib.sha256(content.encode()).hexdigest()

            # Simple chunking (can be improved)
            chunks = self._chunk_content(content)

            fact_ids = []
            for i, chunk_text in enumerate(chunks):
                metadata = {
                    "file_path": file_path,
                    "content_hash": content_hash,
                    "indexed_at": datetime.now().isoformat(),
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "content_type": "documentation",
                }

                result = await self.kb.store_fact(content=chunk_text, metadata=metadata)

                if result.get("status") == "success":
                    fact_ids.append(result["fact_id"])

            logger.info("Indexed %s: %s chunks", file_path, len(fact_ids))

            return {
                "fact_ids": fact_ids,
                "content_hash": content_hash,
                "indexed_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("Failed to index %s: %s", file_path, e)
            return {"fact_ids": [], "content_hash": "", "indexed_at": ""}

    def _chunk_content(self, content: str, max_chunk_size: int = 2000) -> List[str]:
        """Simple paragraph-based chunking"""
        paragraphs = content.split("\n\n")
        chunks = []
        current_chunk = []
        current_size = 0

        for para in paragraphs:
            para_size = len(para)
            if current_size + para_size > max_chunk_size and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [para]
                current_size = para_size
            else:
                current_chunk.append(para)
                current_size += para_size

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks

    async def _apply_sync_changes(
        self, added, modified, deleted, previous_state: Dict
    ) -> Dict:
        """
        Apply detected changes to knowledge base.

        Helper for sync (#825).

        Args:
            added: Set of added file paths
            modified: Set of modified file paths
            deleted: Set of deleted file paths
            previous_state: Previous sync state

        Returns:
            New sync state dictionary
        """
        new_state = previous_state.copy()

        # 1. Remove deleted documents
        for file_path in deleted:
            if file_path in previous_state:
                fact_ids = previous_state[file_path].get("fact_ids", [])
                await self.remove_document_chunks(file_path, fact_ids)
                del new_state[file_path]

        # 2. Update modified documents
        for file_path in modified:
            logger.info("Updating modified: %s", file_path)
            if file_path in previous_state:
                old_fact_ids = previous_state[file_path].get("fact_ids", [])
                await self.remove_document_chunks(file_path, old_fact_ids)
            result = await self.index_document(file_path)
            new_state[file_path] = result

        # 3. Add new documents
        for file_path in added:
            logger.info("Adding new: %s", file_path)
            result = await self.index_document(file_path)
            new_state[file_path] = result

        return new_state

    async def sync(self, dry_run: bool = False):
        """
        Perform full synchronization

        Process:
        1. Scan file system
        2. Load previous state
        3. Detect changes
        4. Apply changes (add/update/delete)
        5. Save new state
        """
        logger.info("=== Starting Documentation Sync ===")

        # Scan current state
        current_files = self.scan_documentation_files()
        previous_state = self.load_sync_state()

        # Detect changes
        added, modified, deleted = self.detect_changes(current_files, previous_state)

        logger.info(
            "Changes detected: +%s ~%s -%s", len(added), len(modified), len(deleted)
        )

        if dry_run:
            logger.info("[DRY RUN] No changes will be applied")
            if added:
                logger.info("Would add: %s", list(added))
            if modified:
                logger.info("Would update: %s", list(modified))
            if deleted:
                logger.info("Would delete: %s", list(deleted))
            return

        # Apply changes
        new_state = await self._apply_sync_changes(
            added, modified, deleted, previous_state
        )

        # Save new state
        self.save_sync_state(new_state)

        logger.info("=== Sync Complete ===")
        logger.info("Total documents in KB: %s", len(new_state))


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Sync documentation to knowledge base")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without applying"
    )
    parser.add_argument(
        "--watch", action="store_true", help="Watch for changes continuously"
    )
    args = parser.parse_args()

    docs_dir = PROJECT_ROOT / "docs"

    if not docs_dir.exists():
        logger.error("Documentation directory not found: %s", docs_dir)
        return

    manager = DocumentationSyncManager(docs_dir)
    await manager.initialize()

    if args.watch:
        logger.info("Starting watch mode (Ctrl+C to stop)")
        try:
            while True:
                await manager.sync(dry_run=args.dry_run)
                await asyncio.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logger.info("Watch mode stopped")
    else:
        await manager.sync(dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
