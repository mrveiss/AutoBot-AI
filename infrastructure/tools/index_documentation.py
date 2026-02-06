# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Documentation Indexing Tool

Indexes AutoBot documentation into the Knowledge Base V2 (ChromaDB),
enabling the chat agent to answer questions about deployment, APIs,
architecture, troubleshooting, and project standards.

Usage:
    python tools/index_documentation.py --full          # Index all documentation
    python tools/index_documentation.py --tier 1       # Index Tier 1 (critical) docs
    python tools/index_documentation.py --file <path>  # Index specific file
    python tools/index_documentation.py --incremental  # Index only changed files
    python tools/index_documentation.py --dry-run      # Test without indexing

GitHub Issue: #250
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env file
from dotenv import load_dotenv

env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(env_path)

from src.utils.chromadb_client import get_chromadb_client

# Hash cache file for incremental indexing (Issue #400)
HASH_CACHE_FILE = PROJECT_ROOT / "data" / ".doc_index_hashes.json"

# Optional: Import knowledge base for full mode (requires Redis)
try:
    from src.knowledge_base import KnowledgeBase

    KNOWLEDGE_BASE_AVAILABLE = True
except ImportError:
    KNOWLEDGE_BASE_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================================================
# TIER DEFINITIONS
# ============================================================================

TIER_1_FILES = [
    "CLAUDE.md",
    "docs/system-state.md",
    "docs/api/COMPREHENSIVE_API_DOCUMENTATION.md",
    "docs/architecture/PHASE_5_DISTRIBUTED_ARCHITECTURE.md",
    "docs/architecture/README.md",
    "docs/architecture/data-flows.md",
    "docs/architecture/redis-schema.md",
    "docs/developer/PHASE_5_DEVELOPER_SETUP.md",
    "docs/troubleshooting/COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md",
    "docs/features/MULTIMODAL_AI_INTEGRATION.md",
    "docs/GLOSSARY.md",
    "docs/operations/disaster-recovery.md",
]

TIER_2_DIRS = [
    "docs/adr",
    "docs/features",
    "docs/implementation",
    "docs/workflow",
    "docs/operations",
]

TIER_3_DIRS = [
    "docs/security",
    "docs/deployment",
    "docs/testing",
    "docs/development",
    "docs/agents",
    "docs/guides",
]

# Files to exclude from indexing
EXCLUDE_PATTERNS = [
    r".*_old\.",
    r".*_backup\.",
    r".*\.tmp$",
    r".*\.bak$",
    r".*\.log$",
    r".*/archives/.*",
    r".*/reports/finished/.*",
    r".*/changelog/.*",
]


# ============================================================================
# MARKDOWN PARSING
# ============================================================================


def extract_title_from_content(content: str) -> str:
    """Extract title from first H1 header or first line."""
    # Look for # Title pattern
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()

    # Fall back to first non-empty line
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:100]

    return "Untitled Document"


def infer_doc_type(file_path: str) -> str:
    """Infer document type from file path (Issue #315: refactored with lookup table)."""
    path_lower = file_path.lower()

    # Keyword-to-type mapping for O(1) lookup
    type_keywords = [
        (["api"], "api"),
        (["architecture"], "architecture"),
        (["developer", "setup"], "developer"),
        (["security"], "security"),
        (["troubleshoot"], "troubleshooting"),
        (["deploy", "docker"], "deployment"),
        (["test"], "testing"),
        (["feature"], "feature"),
        (["workflow"], "workflow"),
        (["agent"], "agent_system"),
        (["claude.md"], "project_rules"),
    ]

    for keywords, doc_type in type_keywords:
        if any(kw in path_lower for kw in keywords):
            return doc_type

    return "documentation"


def infer_category(file_path: str) -> str:
    """Infer category from file path."""
    parts = Path(file_path).parts

    # Find the docs directory index
    try:
        docs_idx = parts.index("docs")
        if len(parts) > docs_idx + 1:
            return parts[docs_idx + 1]
    except ValueError:
        pass

    # For root-level files like CLAUDE.md
    if file_path.endswith("CLAUDE.md"):
        return "project_rules"

    return "general"


def extract_tags(content: str, file_path: str) -> List[str]:
    """Extract relevant tags from content and path."""
    tags = set()

    # Add path-based tags
    path_parts = Path(file_path).parts
    for part in path_parts:
        if part not in [".", "..", "docs", "home", "kali", "Desktop", "AutoBot"]:
            # Clean tag
            tag = re.sub(r"[^a-zA-Z0-9-_]", "", part.lower())
            if tag and len(tag) > 2:
                tags.add(tag)

    # Extract common keywords
    keywords = [
        "api",
        "deployment",
        "docker",
        "kubernetes",
        "redis",
        "chromadb",
        "websocket",
        "authentication",
        "security",
        "multimodal",
        "llm",
        "agent",
        "workflow",
        "terminal",
        "frontend",
        "backend",
        "npm",
        "vue",
        "fastapi",
        "python",
        "typescript",
    ]

    content_lower = content.lower()
    for keyword in keywords:
        if keyword in content_lower:
            tags.add(keyword)

    return list(tags)[:15]  # Limit to 15 tags


def estimate_tokens(text: str) -> int:
    """Estimate token count (rough approximation)."""
    # Rough estimate: 1 token ≈ 4 characters
    return len(text) // 4


def _create_chunk_dict(
    content: str,
    section: str,
    subsection: str | None,
    file_path: str,
    doc_type: str,
    category: str,
    title: str,
) -> Dict[str, Any]:
    """Create a chunk dictionary with metadata (Issue #315: extracted helper)."""
    return {
        "content": content,
        "section": section,
        "subsection": subsection,
        "file_path": file_path,
        "doc_type": doc_type,
        "category": category,
        "title": title,
    }


def _chunk_large_content(
    full_content: str,
    section_name: str,
    subsection_name: str | None,
    file_path: str,
    doc_type: str,
    category: str,
    doc_title: str,
    chunks: List[Dict[str, Any]],
) -> None:
    """Split large content into paragraph-based chunks (Issue #315: extracted helper)."""
    paragraphs = full_content.split("\n\n")
    current_chunk = []
    current_size = 0

    for para in paragraphs:
        para_tokens = estimate_tokens(para)
        if current_size + para_tokens > 800 and current_chunk:
            chunks.append(
                _create_chunk_dict(
                    "\n\n".join(current_chunk),
                    section_name,
                    subsection_name,
                    file_path,
                    doc_type,
                    category,
                    doc_title,
                )
            )
            current_chunk = [para]
            current_size = para_tokens
        else:
            current_chunk.append(para)
            current_size += para_tokens

    if current_chunk:
        chunks.append(
            _create_chunk_dict(
                "\n\n".join(current_chunk),
                section_name,
                subsection_name,
                file_path,
                doc_type,
                category,
                doc_title,
            )
        )


def chunk_markdown(content: str, file_path: str) -> List[Dict[str, Any]]:
    """
    Chunk markdown content by sections while preserving semantic boundaries.

    Args:
        content: Markdown content
        file_path: File path for metadata

    Returns:
        List of chunk dictionaries with content and metadata
    """
    chunks = []
    doc_title = extract_title_from_content(content)
    doc_type = infer_doc_type(file_path)
    category = infer_category(file_path)

    # Split by H2 sections
    h2_pattern = r"^(##\s+.+)$"
    h2_splits = re.split(h2_pattern, content, flags=re.MULTILINE)

    # First element is content before first H2
    intro_content = h2_splits[0].strip() if h2_splits else ""
    current_h2 = doc_title  # Use document title for intro section

    # Add intro chunk if substantial
    if intro_content and estimate_tokens(intro_content) > 50:
        chunks.append(
            {
                "content": intro_content,
                "section": "Introduction",
                "subsection": None,
                "file_path": file_path,
                "doc_type": doc_type,
                "category": category,
                "title": doc_title,
            }
        )

    # Process H2 sections
    i = 1
    while i < len(h2_splits):
        h2_header = h2_splits[i].strip() if i < len(h2_splits) else ""
        h2_content = h2_splits[i + 1].strip() if i + 1 < len(h2_splits) else ""
        i += 2

        # Extract H2 section name
        h2_match = re.match(r"##\s+(.+)", h2_header)
        section_name = h2_match.group(1) if h2_match else "Section"

        # Split by H3 subsections
        h3_pattern = r"^(###\s+.+)$"
        h3_splits = re.split(h3_pattern, h2_content, flags=re.MULTILINE)

        # Content before first H3
        h2_intro = h3_splits[0].strip() if h3_splits else ""

        if h2_intro and estimate_tokens(h2_intro) > 30:
            chunks.append(
                {
                    "content": f"## {section_name}\n\n{h2_intro}",
                    "section": section_name,
                    "subsection": None,
                    "file_path": file_path,
                    "doc_type": doc_type,
                    "category": category,
                    "title": doc_title,
                }
            )

        # Process H3 subsections
        j = 1
        while j < len(h3_splits):
            h3_header = h3_splits[j].strip() if j < len(h3_splits) else ""
            h3_content = h3_splits[j + 1].strip() if j + 1 < len(h3_splits) else ""
            j += 2

            # Extract H3 subsection name
            h3_match = re.match(r"###\s+(.+)", h3_header)
            subsection_name = h3_match.group(1) if h3_match else "Subsection"

            full_content = f"## {section_name}\n\n### {subsection_name}\n\n{h3_content}"
            token_count = estimate_tokens(full_content)

            # Only add substantial chunks (Issue #315: use helper for large content)
            if token_count > 30:
                if token_count > 1000:
                    _chunk_large_content(
                        full_content, section_name, subsection_name,
                        file_path, doc_type, category, doc_title, chunks
                    )
                else:
                    chunks.append(
                        _create_chunk_dict(
                            full_content, section_name, subsection_name,
                            file_path, doc_type, category, doc_title
                        )
                    )

    # If no chunks created (no headers), chunk by paragraphs (Issue #315: use helper)
    if not chunks and content.strip():
        _chunk_large_content(
            content, "Content", None,
            file_path, doc_type, category, doc_title, chunks
        )

    return chunks


# ============================================================================
# FILE DISCOVERY
# ============================================================================


def should_exclude(file_path: str) -> bool:
    """Check if file should be excluded from indexing."""
    for pattern in EXCLUDE_PATTERNS:
        if re.match(pattern, file_path):
            return True
    return False


def discover_files(
    root_dir: Path, tier: Optional[int] = None
) -> List[Tuple[str, int]]:
    """
    Discover markdown files to index.

    Args:
        root_dir: Project root directory
        tier: Optional tier to filter (1, 2, 3, or None for all)

    Returns:
        List of (file_path, tier) tuples
    """
    files = []

    if tier is None or tier == 1:
        # Tier 1: Specific critical files
        for file_rel in TIER_1_FILES:
            file_path = root_dir / file_rel
            if file_path.exists():
                files.append((str(file_path), 1))
            else:
                logger.warning(f"Tier 1 file not found: {file_path}")

    if tier is None or tier == 2:
        # Tier 2: Feature, implementation, workflow docs
        for dir_rel in TIER_2_DIRS:
            dir_path = root_dir / dir_rel
            if dir_path.exists():
                for md_file in dir_path.rglob("*.md"):
                    file_str = str(md_file)
                    if not should_exclude(file_str):
                        # Don't add duplicates from Tier 1
                        if not any(f[0] == file_str for f in files):
                            files.append((file_str, 2))

    if tier is None or tier == 3:
        # Tier 3: Security, deployment, testing, etc.
        for dir_rel in TIER_3_DIRS:
            dir_path = root_dir / dir_rel
            if dir_path.exists():
                for md_file in dir_path.rglob("*.md"):
                    file_str = str(md_file)
                    if not should_exclude(file_str):
                        if not any(f[0] == file_str for f in files):
                            files.append((file_str, 3))

    return files


# ============================================================================
# CHROMADB DIRECT MODE (No Redis Required)
# ============================================================================


class ChromaDBIndexer:
    """Direct ChromaDB indexer that doesn't require Redis."""

    def __init__(self, collection_name: str = "autobot_docs"):
        self.collection_name = collection_name
        self.client = None
        self.collection = None
        self.embed_model = None

    def initialize(self):
        """Initialize ChromaDB and embedding model."""
        from llama_index.embeddings.ollama import OllamaEmbedding

        # Initialize ChromaDB
        chromadb_path = PROJECT_ROOT / "data" / "chromadb"
        self.client = get_chromadb_client(str(chromadb_path))

        # Get or create documentation collection
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name, metadata={"hnsw:space": "cosine"}
        )

        # Initialize embedding model
        self.embed_model = OllamaEmbedding(
            model_name="nomic-embed-text", base_url="http://127.0.0.1:11434"
        )

        logger.info(
            f"ChromaDB indexer initialized: collection='{self.collection_name}', "
            f"existing vectors={self.collection.count()}"
        )

    def add_document(
        self, content: str, metadata: Dict[str, Any], doc_id: str
    ) -> Dict[str, Any]:
        """Add a document to ChromaDB."""
        try:
            # Generate embedding
            embedding = self.embed_model.get_text_embedding(content)

            # Clean metadata (ChromaDB requires flat values)
            clean_metadata = {}
            for k, v in metadata.items():
                if isinstance(v, list):
                    clean_metadata[k] = ",".join(str(x) for x in v)
                elif v is None:
                    clean_metadata[k] = ""
                else:
                    clean_metadata[k] = str(v)

            # Upsert document (update if exists, insert if not)
            self.collection.upsert(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[clean_metadata],
            )

            return {"status": "success", "doc_id": doc_id}

        except Exception as e:
            logger.error(f"Failed to add document {doc_id}: {e}")
            return {"status": "error", "message": str(e)}

    def search(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Search the collection."""
        try:
            embedding = self.embed_model.get_text_embedding(query)
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=n_results,
                include=["documents", "metadatas", "distances"],
            )
            return results
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []


# ============================================================================
# INDEXING
# ============================================================================


def index_file_sync(
    indexer: ChromaDBIndexer, file_path: str, tier: int, dry_run: bool = False
) -> Dict[str, Any]:
    """
    Index a single documentation file (synchronous version).

    Args:
        indexer: ChromaDB indexer instance
        file_path: Path to markdown file
        tier: Tier level (1-3)
        dry_run: If True, simulate without indexing

    Returns:
        Result dictionary
    """
    try:
        # Read file content
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.strip():
            return {"status": "skipped", "reason": "empty_file", "file": file_path}

        # Chunk the document
        chunks = chunk_markdown(content, file_path)

        if not chunks:
            return {"status": "skipped", "reason": "no_chunks", "file": file_path}

        # Extract file-level metadata
        rel_path = os.path.relpath(file_path, PROJECT_ROOT)
        file_tags = extract_tags(content, file_path)

        priority_map = {1: "critical", 2: "high", 3: "medium"}

        indexed_count = 0

        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(
                f"{rel_path}:{chunk['section']}:{i}".encode()
            ).hexdigest()[:12]

            metadata = {
                "source": "autobot_documentation",
                "doc_type": chunk["doc_type"],
                "category": chunk["category"],
                "priority": priority_map.get(tier, "low"),
                "tier": str(tier),
                "file_path": rel_path,
                "section": chunk["section"],
                "subsection": chunk.get("subsection"),
                "title": chunk["title"],
                "tags": file_tags,
                "indexed_at": datetime.now().isoformat(),
                "chunk_index": i,
                "total_chunks": len(chunks),
            }

            if dry_run:
                logger.info(
                    f"  [DRY-RUN] Would index chunk {i+1}/{len(chunks)}: "
                    f"{chunk['section']}/{chunk.get('subsection', 'N/A')}"
                )
                indexed_count += 1
            else:
                result = indexer.add_document(
                    content=chunk["content"], metadata=metadata, doc_id=chunk_id
                )

                if result.get("status") == "success":
                    indexed_count += 1
                else:
                    logger.warning(
                        f"  Failed to index chunk {i+1}: {result.get('message')}"
                    )

        return {
            "status": "success" if not dry_run else "dry_run",
            "file": file_path,
            "chunks": len(chunks),
            "indexed": indexed_count,
        }

    except Exception as e:
        logger.error(f"Error indexing {file_path}: {e}")
        return {"status": "error", "file": file_path, "error": str(e)}


# ============================================================================
# INCREMENTAL INDEXING (Issue #400)
# ============================================================================


def compute_file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of file content for change detection."""
    try:
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        logger.warning(f"Could not hash {file_path}: {e}")
        return ""


def load_hash_cache() -> Dict[str, str]:
    """Load cached file hashes from disk."""
    if HASH_CACHE_FILE.exists():
        try:
            with open(HASH_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load hash cache: {e}")
    return {}


def save_hash_cache(hashes: Dict[str, str]) -> None:
    """Save file hashes to disk."""
    try:
        HASH_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(HASH_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(hashes, f, indent=2)
        logger.info(f"Hash cache saved: {len(hashes)} entries")
    except Exception as e:
        logger.warning(f"Could not save hash cache: {e}")


def filter_changed_files(
    files: List[Tuple[str, int]], hash_cache: Dict[str, str]
) -> Tuple[List[Tuple[str, int]], Dict[str, str]]:
    """
    Filter files to only those that have changed since last indexing.

    Returns:
        Tuple of (changed_files, new_hash_cache)
    """
    changed_files = []
    new_hashes = {}

    for file_path, tier in files:
        rel_path = os.path.relpath(file_path, PROJECT_ROOT)
        current_hash = compute_file_hash(file_path)
        new_hashes[rel_path] = current_hash

        cached_hash = hash_cache.get(rel_path)
        if cached_hash != current_hash:
            changed_files.append((file_path, tier))
            if cached_hash:
                logger.debug(f"Changed: {rel_path}")
            else:
                logger.debug(f"New file: {rel_path}")
        else:
            logger.debug(f"Unchanged: {rel_path}")

    return changed_files, new_hashes


async def index_documentation(
    tier: Optional[int] = None,
    file: Optional[str] = None,
    incremental: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Main indexing function.

    Args:
        tier: Tier to index (1-3, or None for all)
        file: Specific file to index
        incremental: Only index changed files
        dry_run: Simulate without indexing

    Returns:
        Summary of indexing results
    """
    start_time = time.time()
    results = {"success": 0, "failed": 0, "skipped": 0, "files": []}

    # Initialize ChromaDB indexer (no Redis required)
    indexer = None
    if not dry_run:
        logger.info("Initializing ChromaDB indexer...")
        indexer = ChromaDBIndexer()
        indexer.initialize()
        logger.info("ChromaDB indexer ready")
    else:
        logger.info("[DRY-RUN] Skipping indexer initialization")

    # Discover files
    if file:
        file_path = Path(file)
        if not file_path.is_absolute():
            file_path = PROJECT_ROOT / file
        if file_path.exists():
            files = [(str(file_path), 1)]
        else:
            logger.error(f"File not found: {file_path}")
            return {"error": f"File not found: {file_path}"}
    else:
        files = discover_files(PROJECT_ROOT, tier)

    logger.info(f"Discovered {len(files)} files to index")

    # Incremental indexing with hash comparison (Issue #400)
    new_hashes = {}
    if incremental and not file:  # Skip incremental for single-file mode
        hash_cache = load_hash_cache()
        original_count = len(files)
        files, new_hashes = filter_changed_files(files, hash_cache)
        unchanged_count = original_count - len(files)
        logger.info(
            f"Incremental mode: {len(files)} changed, {unchanged_count} unchanged"
        )
        if not files:
            logger.info("No files have changed - nothing to index")
            return {
                "total_files": 0,
                "success": 0,
                "failed": 0,
                "skipped": unchanged_count,
                "unchanged": unchanged_count,
                "elapsed_seconds": round(time.time() - start_time, 2),
                "dry_run": dry_run,
                "incremental": True,
            }

    # Index each file
    for file_path, file_tier in files:
        rel_path = os.path.relpath(file_path, PROJECT_ROOT)
        logger.info(f"Indexing (Tier {file_tier}): {rel_path}")

        result = index_file_sync(indexer, file_path, file_tier, dry_run)
        results["files"].append(result)

        if result["status"] == "success" or result["status"] == "dry_run":
            results["success"] += 1
        elif result["status"] == "skipped":
            results["skipped"] += 1
        else:
            results["failed"] += 1

    elapsed = time.time() - start_time

    # Save hash cache for incremental indexing (Issue #400)
    if not dry_run and new_hashes:
        # Merge with existing cache (preserve hashes for files not in this run)
        existing_cache = load_hash_cache()
        existing_cache.update(new_hashes)
        save_hash_cache(existing_cache)

    # Summary
    summary = {
        "total_files": len(files),
        "success": results["success"],
        "failed": results["failed"],
        "skipped": results["skipped"],
        "elapsed_seconds": round(elapsed, 2),
        "dry_run": dry_run,
        "incremental": incremental,
    }

    logger.info(f"\n{'='*60}")
    logger.info("INDEXING COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Total files: {summary['total_files']}")
    logger.info(f"Success: {summary['success']}")
    logger.info(f"Failed: {summary['failed']}")
    logger.info(f"Skipped: {summary['skipped']}")
    logger.info(f"Elapsed: {summary['elapsed_seconds']}s")
    if dry_run:
        logger.info("MODE: DRY-RUN (no changes made)")
    if incremental:
        logger.info("MODE: INCREMENTAL (only changed files)")
    logger.info(f"{'='*60}")

    return summary


# ============================================================================
# CLI
# ============================================================================


def search_documentation(query: str, n_results: int = 5) -> None:
    """
    Search indexed documentation.

    Args:
        query: Search query
        n_results: Number of results to return
    """
    logger.info(f"Searching documentation for: '{query}'")
    logger.info("=" * 60)

    indexer = ChromaDBIndexer()
    indexer.initialize()

    results = indexer.search(query, n_results=n_results)

    if results and "documents" in results and results["documents"]:
        for i, (doc, meta, dist) in enumerate(
            zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ):
            score = 1 - dist
            logger.info(f"[{i+1}] Score: {score:.3f}")
            logger.info(f"    File: {meta.get('file_path', 'N/A')}")
            logger.info(f"    Section: {meta.get('section', 'N/A')}")
            if meta.get("subsection"):
                logger.info(f"    Subsection: {meta.get('subsection')}")
            logger.info(f"    Preview: {doc[:200]}...")
    else:
        logger.info("No results found")


def get_collection_stats() -> None:
    """Display collection statistics."""
    logger.info("Documentation Collection Statistics")
    logger.info("=" * 60)

    indexer = ChromaDBIndexer()
    indexer.initialize()

    count = indexer.collection.count()
    logger.info(f"Total indexed chunks: {count}")

    # Get unique files
    if count > 0:
        sample = indexer.collection.get(limit=count, include=["metadatas"])
        if sample and "metadatas" in sample:
            files = set()
            categories = {}
            for meta in sample["metadatas"]:
                file_path = meta.get("file_path", "unknown")
                files.add(file_path)
                cat = meta.get("category", "unknown")
                categories[cat] = categories.get(cat, 0) + 1

            logger.info(f"Indexed files: {len(files)}")
            logger.info("Chunks by category:")
            for cat, cnt in sorted(categories.items(), key=lambda x: -x[1]):
                logger.info(f"  - {cat}: {cnt} chunks")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Index AutoBot documentation into Knowledge Base V2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/index_documentation.py --full          # Index all documentation
  python tools/index_documentation.py --tier 1       # Index Tier 1 (critical) docs
  python tools/index_documentation.py --file CLAUDE.md  # Index specific file
  python tools/index_documentation.py --dry-run      # Test without indexing
  python tools/index_documentation.py --search "how to start autobot"  # Search docs
  python tools/index_documentation.py --stats        # Show collection statistics
        """,
    )

    parser.add_argument(
        "--full", action="store_true", help="Index all documentation (Tiers 1-3)"
    )
    parser.add_argument(
        "--tier",
        type=int,
        choices=[1, 2, 3],
        help="Index specific tier (1=critical, 2=high, 3=medium)",
    )
    parser.add_argument("--file", type=str, help="Index specific file")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only index changed files (implies --full)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate indexing without making changes",
    )
    parser.add_argument(
        "--search",
        type=str,
        help="Search indexed documentation with the given query",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show collection statistics",
    )
    parser.add_argument(
        "--results",
        type=int,
        default=5,
        help="Number of search results to return (default: 5)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Handle search mode
    if args.search:
        search_documentation(args.search, args.results)
        return

    # Handle stats mode
    if args.stats:
        get_collection_stats()
        return

    # Validate arguments for indexing mode
    # --incremental implies --full
    if args.incremental:
        args.full = True

    if not any([args.full, args.tier, args.file]):
        parser.print_help()
        print("\nError: Must specify --full, --tier, --file, --incremental, --search, or --stats")
        sys.exit(1)

    # Run indexing
    tier = None if args.full else args.tier

    result = asyncio.run(
        index_documentation(
            tier=tier,
            file=args.file,
            incremental=args.incremental,
            dry_run=args.dry_run,
        )
    )

    # Exit with error code if there were failures
    if result.get("failed", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
