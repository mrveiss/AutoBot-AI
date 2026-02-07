#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Documentation Indexing Script for AutoBot Knowledge Base

This script indexes all AutoBot documentation into the knowledge base system,
enabling users to search and access documentation directly from the chat interface.

Features:
- Recursive markdown file discovery
- Intelligent document chunking by section headers
- Automatic metadata extraction (title, category, file path)
- Category taxonomy management
- Batch vectorization with progress tracking
- Duplicate detection and handling

Usage:
    python scripts/utilities/index_documentation.py [--reindex] [--category CATEGORY]

Arguments:
    --reindex: Force reindex all documentation (clears existing docs)
    --category: Only index specific category (e.g., 'developer', 'api')
    --dry-run: Preview what would be indexed without actually indexing
"""

import asyncio
import hashlib
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env file
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from src.knowledge_base import KnowledgeBase

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ===== CATEGORY TAXONOMY =====

CATEGORY_TAXONOMY = {
    # Order matters - more specific categories first
    "architecture": {
        "name": "Architecture",
        "description": "System architecture and design",
        "patterns": [
            "/architecture/",
            "DISTRIBUTED_ARCHITECTURE",
            "VISUAL_ARCHITECTURE",
        ],
    },
    "developer": {
        "name": "Developer Guide",
        "description": "Setup, architecture, and development documentation",
        "patterns": ["/developer/", "PHASE_5_DEVELOPER_SETUP"],
    },
    "api": {
        "name": "API Reference",
        "description": "Complete API endpoint documentation",
        "patterns": ["/api/", "COMPREHENSIVE_API_DOCUMENTATION"],
    },
    "troubleshooting": {
        "name": "Troubleshooting",
        "description": "Problem resolution and debugging guides",
        "patterns": ["/troubleshooting/", "COMPREHENSIVE_TROUBLESHOOTING"],
    },
    "deployment": {
        "name": "Deployment",
        "description": "Deployment strategies and guides",
        "patterns": ["/deployment/", "DOCKER", "CI_PIPELINE"],
    },
    "security": {
        "name": "Security",
        "description": "Security implementation and guidelines",
        "patterns": ["/security/", "SECURITY_"],
    },
    "features": {
        "name": "Features",
        "description": "Feature documentation and guides",
        "patterns": ["/features/", "SYSTEM_STATUS", "OPTIMIZATION"],
    },
    "testing": {
        "name": "Testing",
        "description": "Testing frameworks and guides",
        "patterns": ["/testing/", "TEST_", "_TEST"],
    },
    "workflow": {
        "name": "Workflow",
        "description": "Workflow orchestration and automation",
        "patterns": ["/workflow/", "WORKFLOW_"],
    },
    "guides": {
        "name": "User Guides",
        "description": "User guides and tutorials",
        "patterns": ["/guides/", "/user_guide/", "GUIDE"],
    },
    "implementation": {
        "name": "Implementation",
        "description": "Implementation summaries and reports",
        "patterns": ["/implementation/", "IMPLEMENTATION_"],
    },
    "agents": {
        "name": "Agent System",
        "description": "Agent architecture and guides",
        "patterns": ["/agents/", "AGENT_", "multi-agent"],
    },
    "general": {
        "name": "General Documentation",
        "description": "Miscellaneous documentation",
        "patterns": ["README", "CLAUDE.md", "decisions.md"],
    },
}


def detect_category(file_path: Path) -> str:
    """Detect category based on file path and name patterns - prioritizes directory paths"""
    file_path_str = str(file_path)
    file_name = file_path.name

    # Check each category in order (more specific first)
    for category, config in CATEGORY_TAXONOMY.items():
        for pattern in config["patterns"]:
            # Check directory path first (more reliable)
            if pattern.startswith("/") and pattern in file_path_str:
                return category
            # Then check filename patterns
            elif not pattern.startswith("/") and pattern in file_name:
                return category

    return "general"


def extract_title_from_markdown(content: str, file_path: Path) -> str:
    """Extract title from markdown content (first H1 header or filename)"""
    # Try to find first H1 header
    h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if h1_match:
        return h1_match.group(1).strip()

    # Fall back to filename without extension
    return file_path.stem.replace("_", " ").replace("-", " ").title()


def chunk_markdown_by_sections(
    content: str, max_chunk_size: int = 2000
) -> List[Tuple[str, str]]:
    """
    Chunk markdown document by section headers for optimal search granularity.

    Returns:
        List of (section_title, section_content) tuples
    """
    chunks = []

    # Split by headers (H1, H2, H3)
    sections = re.split(r"\n(#{1,3}\s+.+)\n", content)

    if len(sections) == 1:
        # No headers found - chunk by size
        for i in range(0, len(content), max_chunk_size):
            chunk = content[i : i + max_chunk_size]
            chunks.append(("Content", chunk))
        return chunks

    current_section = "Introduction"
    current_content = sections[0] if sections else ""

    for i in range(1, len(sections), 2):
        if i < len(sections):
            header = sections[i].strip()
            # Extract header text (remove # symbols)
            section_title = re.sub(r"^#+\s+", "", header)

            # Save previous section if content exists
            if current_content.strip():
                # If section is too large, split further
                if len(current_content) > max_chunk_size:
                    for j in range(0, len(current_content), max_chunk_size):
                        chunk = current_content[j : j + max_chunk_size]
                        chunk_title = (
                            f"{current_section} (Part {j // max_chunk_size + 1})"
                        )
                        chunks.append((chunk_title, chunk))
                else:
                    chunks.append((current_section, current_content))

            # Start new section
            current_section = section_title
            current_content = sections[i + 1] if i + 1 < len(sections) else ""

    # Add last section
    if current_content.strip():
        if len(current_content) > max_chunk_size:
            for j in range(0, len(current_content), max_chunk_size):
                chunk = current_content[j : j + max_chunk_size]
                chunk_title = f"{current_section} (Part {j // max_chunk_size + 1})"
                chunks.append((chunk_title, chunk))
        else:
            chunks.append((current_section, current_content))

    return chunks


def generate_content_hash(content: str) -> str:
    """Generate SHA-256 hash of content for duplicate detection"""
    return hashlib.sha256(content.encode()).hexdigest()


def _check_already_indexed(
    kb, content_hash: str, file_path: Path, title: str
) -> Optional[Dict[str, Any]]:
    """
    Check if document is already indexed in Redis.

    Issue #281: Extracted from index_document to reduce function length.

    Returns:
        Skip result dict if already indexed, None otherwise.
    """
    existing_hash_key = f"doc_hash:{content_hash}"
    if kb.redis_client.exists(existing_hash_key):
        logger.info("Document already indexed (unchanged): %s", file_path.name)
        return {
            "status": "skipped",
            "reason": "already_indexed",
            "file": str(file_path),
            "title": title,
        }
    return None


async def _index_document_chunks(
    kb, chunks: list, title: str, category: str, file_path: Path, content_hash: str
) -> list:
    """
    Index each document chunk into the knowledge base.

    Issue #281: Extracted from index_document to reduce function length.

    Returns:
        List of indexed fact IDs.
    """
    indexed_chunks = []
    for section_title, chunk_content in chunks:
        if not chunk_content.strip():
            continue

        # Prepare metadata
        metadata = {
            "title": title,
            "section": section_title,
            "category": category,
            "file_path": str(file_path.relative_to(PROJECT_ROOT)),
            "content_hash": content_hash,
            "indexed_at": datetime.now().isoformat(),
            "content_type": "documentation",
            "doc_type": "markdown",
            "total_chunks": len(chunks),
            "chunk_index": len(indexed_chunks),
        }

        # Store chunk as fact with vectorization
        result = await kb.store_fact(content=chunk_content, metadata=metadata)

        if result["status"] == "success":
            indexed_chunks.append(result["fact_id"])
        else:
            logger.error(
                "Failed to index chunk: %s", result.get("message", "Unknown error")
            )

    return indexed_chunks


def _store_document_hash(
    kb, content_hash: str, file_path: Path, title: str, chunks_count: int
) -> None:
    """
    Store document hash in Redis to prevent duplicate indexing.

    Issue #281: Extracted from index_document to reduce function length.
    """
    kb.redis_client.setex(
        f"doc_hash:{content_hash}",
        86400 * 30,  # 30 days TTL
        json.dumps(
            {
                "file_path": str(file_path),
                "title": title,
                "chunks": chunks_count,
                "indexed_at": datetime.now().isoformat(),
            }
        ),
    )


async def index_document(
    kb: KnowledgeBase, file_path: Path, category: str, reindex: bool = False
) -> Dict[str, Any]:
    """
    Index a single markdown document into the knowledge base.

    Args:
        kb: KnowledgeBase instance
        file_path: Path to markdown file
        category: Document category
        reindex: Force reindex even if already indexed

    Returns:
        Dict with indexing results
    """
    try:
        # Read file content
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.strip():
            logger.warning("Skipping empty file: %s", file_path)
            return {"status": "skipped", "reason": "empty_file", "file": str(file_path)}

        # Extract metadata
        title = extract_title_from_markdown(content, file_path)
        content_hash = generate_content_hash(content)

        # Check if already indexed (unless reindex flag set)
        if not reindex:
            skip_result = _check_already_indexed(kb, content_hash, file_path, title)
            if skip_result:
                return skip_result

        # Chunk document and index
        chunks = chunk_markdown_by_sections(content)
        logger.info("Processing %s: %s chunks", file_path.name, len(chunks))

        indexed_chunks = await _index_document_chunks(
            kb, chunks, title, category, file_path, content_hash
        )

        # Store document hash to prevent duplicate indexing
        _store_document_hash(kb, content_hash, file_path, title, len(indexed_chunks))

        return {
            "status": "success",
            "file": str(file_path),
            "title": title,
            "category": category,
            "chunks_indexed": len(indexed_chunks),
            "fact_ids": indexed_chunks,
        }

    except Exception as e:
        logger.error("Error indexing %s: %s", file_path, e)
        return {"status": "error", "file": str(file_path), "error": str(e)}


async def discover_documentation_files(
    docs_dir: Path, category_filter: Optional[str] = None
) -> List[Tuple[Path, str]]:
    """
    Discover all markdown documentation files.

    Returns:
        List of (file_path, category) tuples
    """
    discovered_files = []

    # Recursively find all .md files
    for md_file in docs_dir.rglob("*.md"):
        # Skip archived documents
        if "archive" in str(md_file).lower() or "processed_" in str(md_file):
            continue

        # Detect category
        category = detect_category(md_file)

        # Apply category filter if specified
        if category_filter and category != category_filter:
            continue

        discovered_files.append((md_file, category))

    # Also check root directory for key files
    root_files = [PROJECT_ROOT / "CLAUDE.md", PROJECT_ROOT / "README.md"]

    for root_file in root_files:
        if root_file.exists():
            category = detect_category(root_file)
            if not category_filter or category == category_filter:
                discovered_files.append((root_file, category))

    return discovered_files


async def index_all_documentation(
    reindex: bool = False, category_filter: Optional[str] = None, dry_run: bool = False
) -> Dict[str, Any]:
    """
    Index all AutoBot documentation into knowledge base.

    Args:
        reindex: Force reindex all documentation
        category_filter: Only index specific category
        dry_run: Preview without actually indexing

    Returns:
        Summary of indexing operation
    """
    logger.info("Starting documentation indexing...")

    # Initialize knowledge base
    kb = KnowledgeBase()
    await kb.initialize()

    if not kb.initialized:
        logger.error("Failed to initialize knowledge base")
        return {"status": "error", "message": "Knowledge base initialization failed"}

    # Discover documentation files
    docs_dir = PROJECT_ROOT / "docs"
    discovered_files = await discover_documentation_files(docs_dir, category_filter)

    logger.info("Discovered %s documentation files", len(discovered_files))

    if dry_run:
        logger.info("DRY RUN - Preview of files to be indexed:")
        for file_path, category in discovered_files:
            logger.info("  [%15s] %s", category, file_path.relative_to(PROJECT_ROOT))
        return {
            "status": "dry_run",
            "total_files": len(discovered_files),
            "files": [str(f[0].relative_to(PROJECT_ROOT)) for f in discovered_files],
        }

    # Index each document
    results = {
        "total_files": len(discovered_files),
        "indexed": 0,
        "skipped": 0,
        "errors": 0,
        "total_chunks": 0,
        "files": [],
    }

    for i, (file_path, category) in enumerate(discovered_files, 1):
        logger.info(
            "[%s/%s] Indexing: %s (%s)",
            i,
            len(discovered_files),
            file_path.name,
            category,
        )

        result = await index_document(kb, file_path, category, reindex)
        results["files"].append(result)

        if result["status"] == "success":
            results["indexed"] += 1
            results["total_chunks"] += result.get("chunks_indexed", 0)
        elif result["status"] == "skipped":
            results["skipped"] += 1
        else:
            results["errors"] += 1

        # Progress update every 10 files
        if i % 10 == 0:
            logger.info("Progress: %s/%s files processed", i, len(discovered_files))

    # Close knowledge base
    await kb.close()

    # Summary
    logger.info("=" * 80)
    logger.info("DOCUMENTATION INDEXING COMPLETE")
    logger.info("=" * 80)
    logger.info("Total Files: %s", results["total_files"])
    logger.info("Indexed: %s", results["indexed"])
    logger.info("Skipped: %s", results["skipped"])
    logger.info("Errors: %s", results["errors"])
    logger.info("Total Chunks: %s", results["total_chunks"])
    logger.info("=" * 80)

    return results


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Index AutoBot documentation into knowledge base"
    )
    parser.add_argument(
        "--reindex", action="store_true", help="Force reindex all documentation"
    )
    parser.add_argument("--category", type=str, help="Only index specific category")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without actually indexing"
    )

    args = parser.parse_args()

    try:
        results = await index_all_documentation(
            reindex=args.reindex, category_filter=args.category, dry_run=args.dry_run
        )

        # Write results to file
        results_file = (
            PROJECT_ROOT
            / "logs"
            / f"doc_indexing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        results_file.parent.mkdir(exist_ok=True)

        with open(results_file, "w") as f:
            json.dump(results, f, indent=2)

        logger.info("Results written to: %s", results_file)

        return 0 if results.get("errors", 0) == 0 else 1

    except Exception as e:
        logger.error("Documentation indexing failed: %s", e)
        import traceback

        logger.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
