# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Documentation Indexer Service

Issue #1385: Consolidated documentation indexing with ChromaDB as single source of truth.
Extracted from autobot-infrastructure/shared/tools/index_documentation.py and adapted
for service use (SSOT config, proper path constants, thread-safe singleton).

Replaces the dual Redis KB + ChromaDB CLI approach with a single ChromaDB-based system.
"""

import hashlib
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from constants.path_constants import PATH

from autobot_shared.ssot_config import get_ollama_url

logger = logging.getLogger(__name__)

# ============================================================================
# TIER DEFINITIONS (from CLI tool)
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

# Also index user-facing docs
TIER_3_DIRS_EXTRA = [
    "docs/user-guide",
    "docs/developer",
    "docs/plans",
]

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
# DATA CLASSES
# ============================================================================


@dataclass
class IndexResult:
    """Result of an indexing operation."""

    success: int = 0
    failed: int = 0
    skipped: int = 0
    total_files: int = 0
    elapsed_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)


# ============================================================================
# MARKDOWN PARSING (extracted from CLI tool)
# ============================================================================


def _extract_title(content: str) -> str:
    """Extract title from first H1 header or first line."""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:100]
    return "Untitled Document"


def _infer_doc_type(file_path: str) -> str:
    """Infer document type from file path."""
    path_lower = file_path.lower()
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
        (["user-guide", "install"], "user_guide"),
    ]
    for keywords, doc_type in type_keywords:
        if any(kw in path_lower for kw in keywords):
            return doc_type
    return "documentation"


def _infer_category(file_path: str) -> str:
    """Infer category from file path."""
    parts = Path(file_path).parts
    try:
        docs_idx = parts.index("docs")
        if len(parts) > docs_idx + 1:
            return parts[docs_idx + 1]
    except ValueError:
        pass
    if file_path.endswith("CLAUDE.md"):
        return "project_rules"
    return "general"


def _extract_tags(content: str, file_path: str) -> List[str]:
    """Extract relevant tags from content and path."""
    tags = set()
    for part in Path(file_path).parts:
        if part not in [
            ".",
            "..",
            "docs",
            "home",
            "kali",
            "Desktop",
            "AutoBot",
            "opt",
            "autobot",
        ]:
            tag = re.sub(r"[^a-zA-Z0-9-_]", "", part.lower())
            if tag and len(tag) > 2:
                tags.add(tag)

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
        "install",
        "setup",
    ]
    content_lower = content.lower()
    for keyword in keywords:
        if keyword in content_lower:
            tags.add(keyword)

    return list(tags)[:15]


def _estimate_tokens(text: str) -> int:
    """Estimate token count (~4 chars per token)."""
    return len(text) // 4


def _create_chunk(
    content: str,
    section: str,
    subsection: Optional[str],
    file_path: str,
    doc_type: str,
    category: str,
    title: str,
) -> Dict[str, Any]:
    """Create a chunk dictionary with metadata."""
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
    subsection_name: Optional[str],
    file_path: str,
    doc_type: str,
    category: str,
    doc_title: str,
    chunks: List[Dict[str, Any]],
) -> None:
    """Split large content into paragraph-based chunks (~800 tokens)."""
    paragraphs = full_content.split("\n\n")
    current_chunk: List[str] = []
    current_size = 0

    for para in paragraphs:
        para_tokens = _estimate_tokens(para)
        if current_size + para_tokens > 800 and current_chunk:
            chunks.append(
                _create_chunk(
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
            _create_chunk(
                "\n\n".join(current_chunk),
                section_name,
                subsection_name,
                file_path,
                doc_type,
                category,
                doc_title,
            )
        )


def _process_h3_subsections(
    h3_splits: list,
    section_name: str,
    file_path: str,
    doc_type: str,
    category: str,
    doc_title: str,
    chunks: List[Dict[str, Any]],
) -> None:
    """Process H3 subsections within an H2 section. Helper for _chunk_markdown (#1385)."""
    j = 1
    while j < len(h3_splits):
        h3_header = h3_splits[j].strip() if j < len(h3_splits) else ""
        h3_content = h3_splits[j + 1].strip() if j + 1 < len(h3_splits) else ""
        j += 2

        h3_match = re.match(r"###\s+(.+)", h3_header)
        subsection_name = h3_match.group(1) if h3_match else "Subsection"

        full = f"## {section_name}\n\n### {subsection_name}\n\n{h3_content}"
        tokens = _estimate_tokens(full)

        if tokens > 30:
            if tokens > 1000:
                _chunk_large_content(
                    full,
                    section_name,
                    subsection_name,
                    file_path,
                    doc_type,
                    category,
                    doc_title,
                    chunks,
                )
            else:
                chunks.append(
                    _create_chunk(
                        full,
                        section_name,
                        subsection_name,
                        file_path,
                        doc_type,
                        category,
                        doc_title,
                    )
                )


def _process_h2_sections(
    h2_splits: list,
    file_path: str,
    doc_type: str,
    category: str,
    doc_title: str,
    chunks: List[Dict[str, Any]],
) -> None:
    """Process H2 sections and their H3 children. Helper for _chunk_markdown (#1385)."""
    i = 1
    while i < len(h2_splits):
        h2_header = h2_splits[i].strip() if i < len(h2_splits) else ""
        h2_content = h2_splits[i + 1].strip() if i + 1 < len(h2_splits) else ""
        i += 2

        h2_match = re.match(r"##\s+(.+)", h2_header)
        section_name = h2_match.group(1) if h2_match else "Section"

        h3_splits = re.split(r"^(###\s+.+)$", h2_content, flags=re.MULTILINE)
        h2_intro = h3_splits[0].strip() if h3_splits else ""

        if h2_intro and _estimate_tokens(h2_intro) > 30:
            chunks.append(
                _create_chunk(
                    f"## {section_name}\n\n{h2_intro}",
                    section_name,
                    None,
                    file_path,
                    doc_type,
                    category,
                    doc_title,
                )
            )

        _process_h3_subsections(
            h3_splits,
            section_name,
            file_path,
            doc_type,
            category,
            doc_title,
            chunks,
        )


def _chunk_markdown(content: str, file_path: str) -> List[Dict[str, Any]]:
    """Chunk markdown content by H2/H3 sections preserving semantic boundaries."""
    chunks: List[Dict[str, Any]] = []
    doc_title = _extract_title(content)
    doc_type = _infer_doc_type(file_path)
    category = _infer_category(file_path)

    h2_splits = re.split(r"^(##\s+.+)$", content, flags=re.MULTILINE)

    # Intro content before first H2
    intro = h2_splits[0].strip() if h2_splits else ""
    if intro and _estimate_tokens(intro) > 50:
        chunks.append(
            _create_chunk(
                intro,
                "Introduction",
                None,
                file_path,
                doc_type,
                category,
                doc_title,
            )
        )

    _process_h2_sections(h2_splits, file_path, doc_type, category, doc_title, chunks)

    # Fallback: no headers found
    if not chunks and content.strip():
        _chunk_large_content(
            content,
            "Content",
            None,
            file_path,
            doc_type,
            category,
            doc_title,
            chunks,
        )

    return chunks


# ============================================================================
# FILE DISCOVERY
# ============================================================================


def _should_exclude(file_path: str) -> bool:
    """Check if file should be excluded from indexing."""
    for pattern in EXCLUDE_PATTERNS:
        if re.match(pattern, file_path):
            return True
    return False


def _discover_files(
    root_dir: Path, tier: Optional[int] = None
) -> List[Tuple[str, int]]:
    """Discover markdown files to index by tier."""
    files: List[Tuple[str, int]] = []

    if tier is None or tier == 1:
        for file_rel in TIER_1_FILES:
            file_path = root_dir / file_rel
            if file_path.exists():
                files.append((str(file_path), 1))

    if tier is None or tier == 2:
        for dir_rel in TIER_2_DIRS:
            dir_path = root_dir / dir_rel
            if dir_path.exists():
                for md_file in dir_path.rglob("*.md"):
                    file_str = str(md_file)
                    if not _should_exclude(file_str):
                        if not any(f[0] == file_str for f in files):
                            files.append((file_str, 2))

    if tier is None or tier == 3:
        all_tier3 = TIER_3_DIRS + TIER_3_DIRS_EXTRA
        for dir_rel in all_tier3:
            dir_path = root_dir / dir_rel
            if dir_path.exists():
                for md_file in dir_path.rglob("*.md"):
                    file_str = str(md_file)
                    if not _should_exclude(file_str):
                        if not any(f[0] == file_str for f in files):
                            files.append((file_str, 3))

    return files


# ============================================================================
# HASH CACHE for incremental indexing
# ============================================================================

HASH_CACHE_FILE = PATH.DATA_DIR / ".doc_index_hashes.json"


def _compute_file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of file content."""
    try:
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        logger.warning("Could not hash %s: %s", file_path, e)
        return ""


def _load_hash_cache() -> Dict[str, str]:
    """Load cached file hashes from disk."""
    if HASH_CACHE_FILE.exists():
        try:
            with open(HASH_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Could not load hash cache: %s", e)
    return {}


def _save_hash_cache(hashes: Dict[str, str]) -> None:
    """Save file hashes to disk."""
    try:
        HASH_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(HASH_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(hashes, f, indent=2)
    except Exception as e:
        logger.warning("Could not save hash cache: %s", e)


def _filter_changed_files(
    files: List[Tuple[str, int]], hash_cache: Dict[str, str], root_dir: Path
) -> Tuple[List[Tuple[str, int]], Dict[str, str]]:
    """Filter to only changed files since last indexing."""
    changed = []
    new_hashes: Dict[str, str] = {}

    for file_path, tier in files:
        rel_path = os.path.relpath(file_path, root_dir)
        current_hash = _compute_file_hash(file_path)
        new_hashes[rel_path] = current_hash

        if hash_cache.get(rel_path) != current_hash:
            changed.append((file_path, tier))

    return changed, new_hashes


# ============================================================================
# DocIndexerService
# ============================================================================


class DocIndexerService:
    """
    Documentation indexer service — ChromaDB as single source of truth.

    Issue #1385: Consolidates the dual Redis KB + ChromaDB CLI approach.
    Uses SSOT config for Ollama URL, PathConstants for project root.
    Thread-safe singleton via get_doc_indexer_service().
    """

    COLLECTION_NAME = "autobot_docs"

    def __init__(self):
        self._client = None
        self._collection = None
        self._embed_model = None
        self._initialized = False
        self._root_dir = PATH.PROJECT_ROOT

    async def initialize(self) -> bool:
        """Initialize ChromaDB client and embedding model.

        Returns:
            True if initialization successful.
        """
        if self._initialized:
            return True

        try:
            import asyncio

            from llama_index.embeddings.ollama import OllamaEmbedding
            from utils.chromadb_client import get_chromadb_client

            chromadb_path = self._root_dir / "data" / "chromadb"
            self._client = await asyncio.to_thread(
                get_chromadb_client, str(chromadb_path)
            )

            self._collection = self._client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )

            ollama_url = get_ollama_url()
            self._embed_model = OllamaEmbedding(
                model_name="nomic-embed-text", base_url=ollama_url
            )

            doc_count = self._collection.count()
            logger.info(
                "DocIndexerService initialized: collection='%s', "
                "existing_vectors=%d, ollama=%s",
                self.COLLECTION_NAME,
                doc_count,
                ollama_url,
            )
            self._initialized = True
            return True

        except Exception as e:
            logger.error("Failed to initialize DocIndexerService: %s", e)
            return False

    def needs_indexing(self) -> bool:
        """Check if collection is empty and needs initial indexing."""
        if not self._initialized or not self._collection:
            return True
        return self._collection.count() == 0

    async def get_stats(self) -> dict:
        """Get collection statistics."""
        if not self._initialized:
            return {"status": "not_initialized", "count": 0}

        count = self._collection.count()
        result: Dict[str, Any] = {
            "status": "ok",
            "count": count,
            "collection": self.COLLECTION_NAME,
        }

        if count > 0:
            from utils.chromadb_client import get_all_paginated

            sample = get_all_paginated(self._collection, include=["metadatas"])
            if sample and sample.get("metadatas"):
                files = set()
                categories: Dict[str, int] = {}
                for meta in sample["metadatas"]:
                    files.add(meta.get("file_path", "unknown"))
                    cat = meta.get("category", "unknown")
                    categories[cat] = categories.get(cat, 0) + 1
                result["files"] = len(files)
                result["categories"] = categories

        return result

    def _index_chunk(
        self,
        chunk: Dict[str, Any],
        chunk_index: int,
        total_chunks: int,
        rel_path: str,
        file_tags: List[str],
        tier: int,
    ) -> bool:
        """Index a single chunk into ChromaDB. Returns True on success."""
        priority_map = {1: "critical", 2: "high", 3: "medium"}
        chunk_id = hashlib.md5(
            f"{rel_path}:{chunk['section']}:{chunk_index}".encode()
        ).hexdigest()[:12]

        metadata: Dict[str, Any] = {
            "source": "autobot_documentation",
            "doc_type": chunk["doc_type"],
            "category": chunk["category"],
            "priority": priority_map.get(tier, "low"),
            "tier": str(tier),
            "file_path": rel_path,
            "section": chunk["section"],
            "subsection": chunk.get("subsection") or "",
            "title": chunk["title"],
            "tags": ",".join(str(t) for t in file_tags),
            "indexed_at": datetime.now().isoformat(),
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
        }

        try:
            embedding = self._embed_model.get_text_embedding(chunk["content"])
            self._collection.upsert(
                ids=[chunk_id],
                embeddings=[embedding],
                documents=[chunk["content"]],
                metadatas=[metadata],
            )
            return True
        except Exception as e:
            logger.error("Failed to index chunk %s: %s", chunk_id, e)
            return False

    async def index_file(
        self, file_path: Path, tier: int = 3, force: bool = False
    ) -> IndexResult:
        """Index a single documentation file into ChromaDB.

        Args:
            file_path: Path to the markdown file.
            tier: Priority tier (1=critical, 2=high, 3=medium).
            force: If True, skip hash check.

        Returns:
            IndexResult with counts.
        """
        import asyncio

        if not self._initialized:
            await self.initialize()

        result = IndexResult(total_files=1)
        file_str = str(file_path)

        if not file_path.exists():
            result.failed = 1
            result.errors.append(f"File not found: {file_str}")
            return result

        # Hash check for incremental
        if not force:
            rel_path = os.path.relpath(file_str, self._root_dir)
            cache = _load_hash_cache()
            current_hash = _compute_file_hash(file_str)
            if cache.get(rel_path) == current_hash:
                result.skipped = 1
                return result
            # Update cache
            cache[rel_path] = current_hash
            _save_hash_cache(cache)

        try:
            content = file_path.read_text(encoding="utf-8")
            if not content.strip():
                result.skipped = 1
                return result

            chunks = _chunk_markdown(content, file_str)
            if not chunks:
                result.skipped = 1
                return result

            rel_path = os.path.relpath(file_str, self._root_dir)
            file_tags = _extract_tags(content, file_str)

            indexed = 0
            for i, chunk in enumerate(chunks):
                ok = await asyncio.to_thread(
                    self._index_chunk,
                    chunk,
                    i,
                    len(chunks),
                    rel_path,
                    file_tags,
                    tier,
                )
                if ok:
                    indexed += 1

            result.success = 1 if indexed > 0 else 0
            result.failed = 0 if indexed > 0 else 1
            return result

        except Exception as e:
            logger.error("Error indexing %s: %s", file_str, e)
            result.failed = 1
            result.errors.append(f"{file_str}: {e}")
            return result

    async def _index_single_file_content(
        self, file_path: str, tier: int, result: IndexResult
    ) -> None:
        """Read, chunk, and index a single file. Helper for index_all (#1385)."""
        import asyncio

        rel_path = os.path.relpath(file_path, self._root_dir)
        try:
            content = Path(file_path).read_text(encoding="utf-8")
            if not content.strip():
                result.skipped += 1
                return

            chunks = _chunk_markdown(content, file_path)
            if not chunks:
                result.skipped += 1
                return

            file_tags = _extract_tags(content, file_path)
            indexed = 0
            for i, chunk in enumerate(chunks):
                ok = await asyncio.to_thread(
                    self._index_chunk,
                    chunk,
                    i,
                    len(chunks),
                    rel_path,
                    file_tags,
                    tier,
                )
                if ok:
                    indexed += 1

            if indexed > 0:
                result.success += 1
            else:
                result.failed += 1

        except Exception as e:
            logger.error("Error indexing %s: %s", rel_path, e)
            result.failed += 1
            result.errors.append(f"{rel_path}: {e}")

    def _apply_incremental_filter(
        self,
        files: List[Tuple[str, int]],
        total_result: IndexResult,
        start_time: float,
    ) -> Tuple[List[Tuple[str, int]], Dict[str, str], bool]:
        """Filter to changed files only. Helper for index_all (#1385).

        Returns (filtered_files, new_hashes, early_exit).
        """
        hash_cache = _load_hash_cache()
        original_count = len(files)
        files, new_hashes = _filter_changed_files(files, hash_cache, self._root_dir)
        skipped = original_count - len(files)
        total_result.skipped = skipped
        total_result.total_files = original_count
        logger.info(
            "Incremental mode: %d changed, %d unchanged",
            len(files),
            skipped,
        )
        if not files:
            logger.info("No files have changed — nothing to index")
            total_result.elapsed_seconds = round(time.time() - start_time, 2)
            return files, new_hashes, True
        return files, new_hashes, False

    async def index_all(self, force: bool = False) -> IndexResult:
        """Index all documentation files.

        Args:
            force: If True, re-index all files regardless of hash cache.

        Returns:
            IndexResult with aggregate counts.
        """
        start_time = time.time()

        if not self._initialized:
            if not await self.initialize():
                return IndexResult(errors=["Failed to initialize"])

        files = _discover_files(self._root_dir)
        total_result = IndexResult(total_files=len(files))

        if not files:
            logger.warning("No documentation files discovered in %s", self._root_dir)
            return total_result

        # Incremental mode: filter to changed files
        new_hashes: Dict[str, str] = {}
        if not force:
            files, new_hashes, early = self._apply_incremental_filter(
                files, total_result, start_time
            )
            if early:
                return total_result

        logger.info("Indexing %d documentation files...", len(files))
        for file_path, tier in files:
            await self._index_single_file_content(file_path, tier, total_result)

        if new_hashes:
            existing_cache = _load_hash_cache()
            existing_cache.update(new_hashes)
            _save_hash_cache(existing_cache)

        total_result.elapsed_seconds = round(time.time() - start_time, 2)

        logger.info(
            "Documentation indexing complete: %d success, %d failed, "
            "%d skipped in %.1fs (collection now has %d vectors)",
            total_result.success,
            total_result.failed,
            total_result.skipped,
            total_result.elapsed_seconds,
            self._collection.count() if self._collection else 0,
        )

        return total_result


# ============================================================================
# SINGLETON
# ============================================================================

_doc_indexer: Optional[DocIndexerService] = None
_doc_indexer_lock = threading.Lock()


def get_doc_indexer_service() -> DocIndexerService:
    """Get or create the global DocIndexerService instance (thread-safe)."""
    global _doc_indexer
    if _doc_indexer is None:
        with _doc_indexer_lock:
            if _doc_indexer is None:
                _doc_indexer = DocIndexerService()
    return _doc_indexer
