# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Documentation Indexer Service

Issue #1385: Consolidated documentation indexing with ChromaDB as single source of truth.
Extracted from autobot-infrastructure/shared/tools/index_documentation.py and adapted for
service use (SSOT config, proper path constants, thread-safe singleton).

Replaces the dual Redis KB + ChromaDB CLI approach with a single ChromaDB-based system.
"""

import asyncio
import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

from autobot_shared.async_compat import fire_and_forget
from autobot_shared.kb_doc_set import in_doc_set
from autobot_shared.logging_manager import get_logger
from services.knowledge.index_cache_paths import doc_index_hashes

if TYPE_CHECKING:
    from services.knowledge.sync_queue import SyncQueueEntry, SyncReason  # noqa: F401

from autobot_shared.ssot_config import get_ollama_url
from constants.path_constants import PATH
from constants.threshold_constants import CategoryDefaults
from knowledge.chunk_identity import carry_store_id, stamp_chunk_id
from knowledge.platform_docs import PLATFORM_DOCS_GRANT, PLATFORM_DOCS_GRANT_VERSION
from knowledge.query_sanitizer import sanitize_document as _sanitize_document
from services.knowledge import doc_index_store_guard as store_guard
from services.knowledge.doc_index_orphans import chunk_base_id, reindex_file
from services.knowledge.doc_markdown_chunks import (
    _chunk_markdown,
    _extract_tags,
    _parse_frontmatter,
)
from services.knowledge.doc_taxonomy import category_of
from services.knowledge.synthesis_schema_loader import SynthesisSchema, load_synthesis_schema

logger = get_logger(__name__)

# ============================================================================
# EMBEDDING-DIMENSION GUARD (Issue #10420)
# ============================================================================

# Map of embedding model name -> vector dimension. A Chroma collection's
# dimension is fixed at creation, so swapping models (e.g. all-minilm 384 ->
# nomic-embed-text 768) without migrating makes every upsert fail with a
# dimension-mismatch error. We compare the active model's dimension against the
# dimension recorded in an existing collection's provenance metadata.
_KNOWN_DIMS: Dict[str, int] = {
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
    "all-minilm": 384,
    "bge-small-en-v1.5": 384,
    "bge-large-en-v1.5": 1024,
    "text-embedding-ada-002": 1536,
}

# Destructive recreate is OPT-IN only. Default is safe (off): on a mismatch the
# operator gets a single actionable error instead of an index that is silently
# wiped. Mirrors the connector-store env-bool convention (credential_store.py).
AUTO_REINDEX_ON_DIM_MISMATCH_ENV = "AUTOBOT_KNOWLEDGE_AUTO_REINDEX_ON_DIM_MISMATCH"


def _auto_reindex_on_dim_mismatch() -> bool:
    """Return True when the operator has opted into destructive dim-mismatch recreate."""
    return os.environ.get(AUTO_REINDEX_ON_DIM_MISMATCH_ENV, "false").strip().lower() in ("1", "true", "yes")


# ============================================================================
# TIER DEFINITIONS: a priority order over kb_doc_set, and a curated subset of it (#20063)
# ============================================================================

TIER_1_FILES = [
    "CLAUDE.md",
    "docs/api/COMPREHENSIVE_API_DOCUMENTATION.md",
    "docs/architecture/DISTRIBUTED_ARCHITECTURE.md",
    "docs/architecture/README.md",
    "docs/architecture/data-flows.md",
    "docs/architecture/redis-schema.md",
    "docs/developer/DEVELOPER_SETUP.md",
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
    r".*/_index\.md$",
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
# FILE DISCOVERY
# ============================================================================


def _should_exclude(file_path: str) -> bool:
    """Check if file should be excluded from indexing."""
    for pattern in EXCLUDE_PATTERNS:
        if re.match(pattern, file_path):
            return True
    return False


def _discover_files(root_dir: Path, tier: int | None = None) -> List[Tuple[str, int]]:
    """Discover markdown files to index by tier; only files in the canonical doc set qualify (#20063)."""
    found: dict[str, int] = {}

    def add(path: Path, number: int) -> None:
        if in_doc_set(path.relative_to(root_dir).as_posix()):
            found.setdefault(str(path), number)

    if tier is None or tier == 1:
        for file_rel in TIER_1_FILES:
            if (root_dir / file_rel).exists():
                add(root_dir / file_rel, 1)

    for number, dirs in ((2, TIER_2_DIRS), (3, TIER_3_DIRS + TIER_3_DIRS_EXTRA)):
        if tier is None or tier == number:
            for dir_rel in dirs:
                for md_file in (root_dir / dir_rel).rglob("*.md"):
                    if not _should_exclude(str(md_file)):
                        add(md_file, number)

    return list(found.items())


# ============================================================================
# HASH CACHE for incremental indexing
# ============================================================================

# None: the shared user cache, resolved on use, never at import (index_cache_paths, #19553); tests pin a path.
HASH_CACHE_FILE: Path | None = None


def _compute_file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of the grant version plus file content.

    Resolves symlinks so the hash reflects the target file's content (#4382).
    Returns empty string on PermissionError, OSError, or RuntimeError (e.g.
    circular symlinks raise RuntimeError on Python 3.10+); callers must
    preserve the cached hash when empty to avoid false-changed detection.
    """
    try:
        resolved = str(Path(file_path).resolve())
        with open(resolved, "rb") as f:
            return hashlib.sha256(PLATFORM_DOCS_GRANT_VERSION + f.read()).hexdigest()  # #16664
    except (PermissionError, OSError, RuntimeError) as e:
        logger.warning("Cannot hash %s: %s", file_path, e)
        return ""


def _load_hash_cache() -> Dict[str, str]:
    """Load cached file hashes from disk."""
    if doc_index_hashes(HASH_CACHE_FILE).exists():
        try:
            with open(doc_index_hashes(HASH_CACHE_FILE), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Could not load hash cache: %s", e)
    return {}


def _save_hash_cache(hashes: Dict[str, str]) -> None:
    """Save file hashes to disk."""
    try:
        doc_index_hashes(HASH_CACHE_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(doc_index_hashes(HASH_CACHE_FILE), "w", encoding="utf-8") as f:
            json.dump(hashes, f, indent=2)
    except Exception as e:
        logger.warning("Could not save hash cache: %s", e)


def _normalize_path(file_path: str, root_dir: Path) -> Tuple[str, str]:
    """Return (normalized_abs_path, rel_path) for a file.

    Resolves the file path to handle symlinks and ensure consistent
    path separators across platforms (#4382).  If the resolved path
    escapes root_dir (e.g. after project relocation), or if resolution
    fails due to a circular symlink (#4433), falls back to the original
    path so relpath always returns a valid key.
    """
    try:
        resolved = str(Path(file_path).resolve())
        rel_path = os.path.relpath(resolved, str(root_dir.resolve()))
    except (ValueError, OSError, RuntimeError):
        # ValueError: Windows cross-drive relpath.
        # OSError/RuntimeError: circular symlinks (Python 3.10 raises
        #   RuntimeError("Symlink loop …") wrapping the underlying ELOOP OSError).
        # Fall back to the original path so we still get a usable relative key.
        resolved = file_path
        rel_path = os.path.relpath(file_path, str(root_dir))
    return resolved, rel_path


def _filter_changed_files(
    files: List[Tuple[str, int]], hash_cache: Dict[str, str], root_dir: Path
) -> Tuple[List[Tuple[str, int]], Dict[str, str]]:
    """Filter to only changed files since last indexing.

    Edge cases handled (#4382):
    - Symlinks: paths are resolved before hashing so the hash reflects
      target content, not the symlink inode.
    - Path normalization: resolved paths eliminate platform separator
      differences and double-slash ambiguities.
    - Permission errors: _compute_file_hash returns "" when a file
      cannot be read.  Preserving the cached hash avoids treating a
      temporarily unreadable file as "changed" and avoids storing an
      empty hash that would trigger re-indexing once permissions are
      restored.
    """
    changed = []
    new_hashes: Dict[str, str] = {}

    for file_path, tier in files:
        _, rel_path = _normalize_path(file_path, root_dir)
        current_hash = _compute_file_hash(file_path)

        if not current_hash:
            # File is unreadable (permission error or gone); keep whatever
            # was in the cache so the file is not falsely marked as changed.
            cached = hash_cache.get(rel_path, "")
            new_hashes[rel_path] = cached
            if hash_cache.get(rel_path) != cached:
                changed.append((file_path, tier))
            continue

        new_hashes[rel_path] = current_hash
        if hash_cache.get(rel_path) != current_hash:
            changed.append((file_path, tier))

    return changed, new_hashes


def _select_files(root_dir: Path, tier: int | None = None, category: str | None = None) -> List[Tuple[str, int]]:
    """Discover files for ``tier`` (None = all), keeping only those in ``category`` when given (#18129)."""
    files = _discover_files(root_dir, tier)
    if category:
        files = [(p, t) for p, t in files if category_of(p, root_dir) == category]
    return files


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

    def __init__(
        self,
        llm_service: Any | None = None,
        org_id: str | None = None,
    ) -> None:
        self._client = None
        self._collection = None
        self._embed_model = None
        self._initialized = False
        self._root_dir = PATH.PROJECT_ROOT
        # Issue #4564: optional LLM service for KB synthesis
        self._llm_service = llm_service
        # Issue #4451: per-org embedding model selection (None => __default__)
        self._org_id = org_id
        self.embedding_model_name: str | None = None
        # Issue #10420: set when a dimension-mismatch recreate wiped the
        # collection, so the next index_all() forces a full re-embed.
        self._needs_reindex = False
        self.synthesis_schema: SynthesisSchema = self._load_schema()

    def _load_schema(self) -> SynthesisSchema:
        """Load synthesis schema from YAML; warn and return empty schema if absent."""
        schema = load_synthesis_schema()
        if not schema.collections:
            logger.warning("Synthesis schema is absent or empty — schema-driven synthesis disabled")
        else:
            logger.debug(
                "Loaded synthesis schema: %d collection(s)",
                len(schema.collections),
            )
        return schema

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

            from knowledge.backends import get_default_client
            from utils.chromadb_client import chromadb_endpoint

            chromadb_path = self._root_dir / "data" / "chromadb"
            # get_default_client takes only **kwargs (#6613) — pass db_path
            # explicitly. Positional call raised TypeError at init, falling
            # the indexer back to slow SCAN paths.
            self._client = await asyncio.to_thread(get_default_client, db_path=str(chromadb_path))
            self._store = chromadb_endpoint(str(chromadb_path))

            ollama_url = get_ollama_url()

            # Issue #4451: per-org embedding model config, SSOT fallback.
            # Resolved before collection creation so embedding_model metadata
            # can be written at first-create time (#7427).
            from services.knowledge.org_knowledge_config import (
                get_org_knowledge_config_service,
            )

            effective = await get_org_knowledge_config_service().get_effective(self._org_id)
            embed_model_name = effective.embedding_model  # org override, else ssot; empty fails init (#18143)
            self.embedding_model_name = embed_model_name

            # Embed model is created first so the collection guard can probe the
            # model's true dimension when it is not in _KNOWN_DIMS (#10420).
            self._embed_model = OllamaEmbedding(
                model_name=embed_model_name, base_url=ollama_url, client_kwargs={"headers": store_guard.caller_tag()}
            )

            embed_dim = await asyncio.to_thread(
                self._resolve_embed_dim, embed_model_name, effective.embedding_dimension
            )
            self._collection = await asyncio.to_thread(self._resolve_collection, embed_model_name, embed_dim)

            doc_count = store_guard.read_count(self._collection)
            logger.info(
                "DocIndexerService initialized: store='%s', collection='%s', "
                "existing_vectors=%d, ollama=%s, embed_model=%s, org_id=%s",
                self._store,
                self.COLLECTION_NAME,
                doc_count,
                ollama_url,
                embed_model_name,
                self._org_id or "__default__",
            )
            self._initialized = True
            return True

        except Exception as e:
            logger.error("Failed to initialize DocIndexerService: %s", e)
            return False

    def _read_collection_provenance(self, name: str):
        """Return stored EmbeddingProvenance of an existing collection, else None (#10420)."""
        from autobot_shared.embedding_provenance import provenance_from_metadata

        existing = [c for c in self._client.list_collections() if getattr(c, "name", None) == name]
        if not existing:
            return None
        return provenance_from_metadata(getattr(existing[0], "metadata", None))

    def _create_collection(self, name: str, model_name: str, embed_dim):
        """Create (or get) the collection, writing embedding provenance metadata (#10420)."""
        from autobot_shared.embedding_provenance import (
            EmbeddingProvenance,
            provenance_to_metadata,
        )

        provenance_meta = (
            provenance_to_metadata(EmbeddingProvenance(model_name, embed_dim)) if embed_dim is not None else {}
        )
        return self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine", **provenance_meta},
        )

    def _peek_collection_dim(self, name: str):
        """Return an existing collection's actual vector dimension, or None (#10420).

        Fallback for legacy collections created before provenance metadata: the
        dimension is read directly from a stored vector so a mismatch is still
        detected instead of dropping every chunk.
        """
        try:
            coll = self._client.get_collection(name)
            if coll.count() == 0:
                return None
            peek = coll.peek(limit=1)
            embs = peek.get("embeddings") if isinstance(peek, dict) else None
            if embs is not None and len(embs) > 0 and embs[0] is not None:
                return len(embs[0])
        except Exception as e:  # collection absent / peek unsupported — no guard
            logger.debug("#10420: could not peek collection dim for '%s': %s", name, e)
        return None

    def _handle_dim_mismatch(self, old_model: str, old_dim: int, model_name: str, embed_dim: int) -> None:
        """Recreate the collection (flag ON) or raise once (flag OFF) on a dim mismatch (#10420)."""
        from autobot_shared.embedding_provenance import EmbeddingMismatchError

        if not _auto_reindex_on_dim_mismatch():
            raise EmbeddingMismatchError(
                f"#10420: collection '{self.COLLECTION_NAME}' was built with model "
                f"'{old_model}' (dim {old_dim}) but the active model "
                f"'{model_name}' produces dim {embed_dim}. Every upsert would be rejected. "
                f"Set {AUTO_REINDEX_ON_DIM_MISMATCH_ENV}=true to delete and re-index the "
                f"collection at the new dimension (old vectors are unusable), or revert to "
                f"the original embedding model."
            )
        logger.warning(
            "#10420: embedding dimension changed for collection '%s' "
            "(%s dim %d -> %s dim %d); %s is set — deleting and re-indexing "
            "(old vectors are unusable at the new dimension)",
            self.COLLECTION_NAME,
            old_model,
            old_dim,
            model_name,
            embed_dim,
            AUTO_REINDEX_ON_DIM_MISMATCH_ENV,
        )
        self._client.delete_collection(self.COLLECTION_NAME)
        self._needs_reindex = True

    def _resolve_embed_dim(self, model_name: str, configured_dim):
        """Resolve the active model's embedding dimension (#10420).

        Priority: explicit org config > _KNOWN_DIMS lookup > live probe. The
        probe makes mismatch detection work for any model (e.g. a 3072-dim
        model not in _KNOWN_DIMS), instead of silently skipping the guard and
        dropping every chunk.
        """
        if configured_dim:
            return int(configured_dim)
        known = _KNOWN_DIMS.get(model_name)
        if known is not None:
            return known
        try:
            vec = self._embed_model.get_text_embedding("dimension probe")
            return len(vec) if vec else None
        except Exception as e:  # ollama unavailable / model error — fall back to no guard
            logger.warning("#10420: could not probe embedding dimension for '%s': %s", model_name, e)
            return None

    def _resolve_collection(self, model_name: str, embed_dim=None):
        """Resolve the docs collection, guarding against an embedding-dimension mismatch (#10420).

        A Chroma collection's dimension is fixed at creation. If the active
        model's dimension differs from the existing collection's recorded
        dimension, every upsert would be rejected. ``_handle_dim_mismatch``
        either recreates the collection (opt-in, destructive) or raises once
        with an actionable message instead of flooding the log per chunk.

        ``embed_dim`` is the active model's dimension (probed by the caller for
        models outside ``_KNOWN_DIMS``); it falls back to the static lookup.
        """
        if embed_dim is None:
            embed_dim = _KNOWN_DIMS.get(model_name)
        stored = self._read_collection_provenance(self.COLLECTION_NAME)
        if stored is not None:
            old_dim, old_model = stored.dim, stored.model_name
        else:
            old_dim, old_model = self._peek_collection_dim(self.COLLECTION_NAME), "(legacy/unknown)"
        if old_dim is not None and embed_dim is not None and old_dim != embed_dim:
            self._handle_dim_mismatch(old_model, old_dim, model_name, embed_dim)
        return self._create_collection(self.COLLECTION_NAME, model_name, embed_dim)

    def needs_indexing(self) -> bool:
        """Check if collection is empty and needs initial indexing."""
        if not self._initialized or not self._collection:
            return True
        # Issue #10420: a dim-mismatch recreate wiped the index — force re-embed.
        # getattr guard keeps __new__-built fixtures (which skip __init__) safe.
        if getattr(self, "_needs_reindex", False):
            return True
        return store_guard.read_count(self._collection) == 0

    def _full_reindex_reason(self) -> str | None:
        """Why this run must re-embed everything (None: it need not); refuses on an unknown or moved store (#20886)."""
        if not self._initialized or not self._collection:
            return "indexer not initialized"
        return store_guard.reindex_reason(
            count=store_guard.read_count(self._collection),
            needs_reindex=getattr(self, "_needs_reindex", False),
            cache_entries=len(_load_hash_cache()),
            hash_override=HASH_CACHE_FILE,
            current=self._store,
        )

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
                    cat = meta.get("category", CategoryDefaults.UNKNOWN)
                    categories[cat] = categories.get(cat, 0) + 1
                result["files"] = len(files)
                result["categories"] = categories

        return result

    @staticmethod
    def _is_oversized_error(exc: Exception) -> bool:
        """Return True if *exc* indicates the embedding model rejected an oversized input.

        Covers error messages from Ollama, OpenAI, and similar providers that surface
        token/context-length violations as plain-text exceptions.
        """
        msg = str(exc).lower()
        _OVERSIZED_KEYWORDS = (
            "too large",
            "too long",
            "token",
            "sequence length",
            "context length",
            "input length",
            "max_length",
            "exceeds",
            "truncat",
            "overflow",
        )
        return any(kw in msg for kw in _OVERSIZED_KEYWORDS)

    _embed_progress = store_guard.EmbedProgress()  # reset per index_all run (#20886)
    _store = ""  # where initialize() opened the vector store; set per instance (#20886)
    embedding_model_name: str | None = None  # set by initialize(); class default keeps __new__-built fixtures safe

    def _embed_and_upsert(self, content: str, chunk_id: str, metadata: Dict[str, Any]) -> None:
        """Embed *content* and upsert into ChromaDB. Raises on failure."""
        embedding = self._embed_model.get_text_embedding(content)
        self._collection.upsert(
            ids=[chunk_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[stamp_chunk_id(metadata, chunk_id)],  # #18142: the Chroma id is also the stored chunk_id
        )
        self._embed_progress.tick()

    def _split_and_embed(
        self,
        content: str,
        chunk_id: str,
        metadata: Dict[str, Any],
        rel_path: str,
        depth: int = 0,
        max_depth: int = 4,
    ) -> bool:
        """Recursively split oversized content and embed each piece (#4702).

        Attempts to embed *content* directly.  If the model rejects it as
        oversized and *depth* < *max_depth*, the content is split in half and
        each half is retried recursively (up to 1/16th of the original at
        depth 4).  Returns True when at least one sub-chunk is stored.
        """
        if not content:
            return False
        try:
            self._embed_and_upsert(content, chunk_id, metadata)
            return True
        except Exception as e:
            if not self._is_oversized_error(e) or depth >= max_depth:
                logger.warning(
                    "Dropping chunk %s (depth=%d, chars=%d): %s",
                    chunk_id,
                    depth,
                    len(content),
                    e,
                )
                return False

        logger.warning(
            "Oversized chunk — splitting at depth %d " "(doc=%s, chunk_id=%s, chars=%d)",
            depth,
            rel_path,
            chunk_id,
            len(content),
        )
        mid = len(content) // 2
        left = content[:mid].strip()
        right = content[mid:].strip()
        left_ok = self._split_and_embed(
            left,
            f"{chunk_id}_L{depth}",
            {**metadata, "chunk_id_parent": chunk_id, "split_depth": depth},
            rel_path,
            depth + 1,
            max_depth,
        )
        right_ok = self._split_and_embed(
            right,
            f"{chunk_id}_R{depth}",
            {**metadata, "chunk_id_parent": chunk_id, "split_depth": depth},
            rel_path,
            depth + 1,
            max_depth,
        )
        return left_ok or right_ok

    def _index_chunk(
        self,
        chunk: Dict[str, Any],
        chunk_index: int,
        total_chunks: int,
        rel_path: str,
        file_tags: List[str],
        tier: int,
        index_run: str = "",
    ) -> bool:
        """Index a single chunk into ChromaDB.

        If the embedding model rejects the chunk as oversized, the content is
        split recursively up to max_depth=4 (at most 1/16th of original size).
        A WARNING is logged when splitting occurs so the failure is always
        visible (fixes #4665 — chunks were previously dropped silently with no
        diagnostic; #4702 — single-level split could still drop large halves).

        Returns True when at least one (sub-)chunk was stored successfully.
        """
        priority_map = {1: "critical", 2: "high", 3: "medium"}
        chunk_id = chunk_base_id(rel_path, chunk["section"], chunk_index)

        metadata: Dict[str, Any] = {
            "source": "autobot_documentation",
            **PLATFORM_DOCS_GRANT,  # #16664: stamped at write so reads need no special case
            "doc_type": chunk["doc_type"],
            "category": chunk["category"],
            "priority": priority_map.get(tier, "low"),
            "tier": str(tier),
            "file_path": rel_path,
            "section": chunk["section"],
            "subsection": chunk.get("subsection") or "",
            "title": chunk["title"],
            "tags": ",".join(str(t) for t in file_tags),
            "indexed_at": datetime.now(tz=timezone.utc).isoformat(),
            "index_run": index_run,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            # Issue #4681: evolutionary lineage fields.
            # lineage_parent_id and lineage_source_run_id are populated by
            # LineageService.stamp_upsert() after synthesis runs; seeded with
            # defaults on initial index so callers can always read them.
            "lineage_parent_id": "",
            "lineage_version": 1,
            "lineage_source_run_id": "",
        }

        return self._split_and_embed(chunk["content"], chunk_id, metadata, rel_path)

    def _check_hash_and_update_cache(self, file_str: str, force: bool) -> bool:
        """Check incremental hash cache; update cache entry if changed. Issue #2735.

        Returns True if the file should be skipped (hash unchanged and not forced).
        Extracted from index_file to keep parent under 65 lines.

        Uses normalized (resolved) paths for consistent cache keys (#4382).
        """
        if force:
            return False
        _, rel_path = _normalize_path(file_str, self._root_dir)
        cache = _load_hash_cache()
        current_hash = _compute_file_hash(file_str)
        if not current_hash:
            # Unreadable file: preserve cached hash and skip to avoid false-changed.
            return True
        if cache.get(rel_path) == current_hash:
            return True
        cache[rel_path] = current_hash
        _save_hash_cache(cache)
        store_guard.save_recorded_store(self._store, HASH_CACHE_FILE)
        return False

    async def _index_file_chunks(self, file_str: str, content: str, rel_path: str, tier: int) -> tuple[int, int]:
        """Chunk content and index all chunks; return (success_count, chunk_count). Issue #2735."""
        body, fm_tags, fm_aliases = _parse_frontmatter(content)
        # Issue #5064: sanitize ingested content before chunking / embedding.
        body = _sanitize_document(body, source="doc_indexer").sanitized_text
        chunks = _chunk_markdown(body, file_str)
        if not chunks:
            return 0, 0

        file_tags = _extract_tags(body, file_str)
        file_tags = list(dict.fromkeys(fm_tags + fm_aliases + file_tags))[:20]
        # Ids hash the section name: a renamed section leaves an orphan, dropped only once the new chunks are stored.
        indexed = await reindex_file(self._collection, self._index_chunk, chunks, rel_path, file_tags, tier)
        return indexed, len(chunks)

    async def index_file(self, file_path: Path, tier: int = 3, force: bool = False) -> IndexResult:
        """Index one markdown file at a priority tier; force skips the hash check, never the store guard (#20886)."""
        if not self._initialized:
            await self.initialize()

        file_str = str(file_path)
        if not file_path.exists():
            return IndexResult(total_files=1, failed=1, errors=[f"File not found: {file_str}"])
        try:
            # Unconditional, so force cannot bypass it; before the cache or store record is touched (#20886).
            reason = self._full_reindex_reason()
            force = force or bool(reason)
        except (store_guard.CollectionCountUnknown, store_guard.StoreLocationChanged) as e:
            logger.error("Doc indexer refusing to index %s: %s", file_str, e)
            return IndexResult(total_files=1, failed=1, errors=[str(e)])
        if self._check_hash_and_update_cache(file_str, force):
            return IndexResult(total_files=1, skipped=1)
        return await self._embed_one_file(file_path, tier)

    async def _embed_one_file(self, file_path: Path, tier: int) -> IndexResult:
        """Read, chunk and embed one file; a failure is returned as a failed result."""
        file_str = str(file_path)
        try:
            # #7467: was sync `file_path.read_text` blocking the event loop.
            content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
            if not content.strip():
                return IndexResult(total_files=1, skipped=1)
            rel_path = os.path.relpath(file_str, self._root_dir)
            indexed, total_chunks = await self._index_file_chunks(file_str, content, rel_path, tier)
            if total_chunks == 0:
                return IndexResult(total_files=1, skipped=1)
            return IndexResult(total_files=1, success=int(indexed > 0), failed=int(indexed == 0))
        except Exception as e:
            logger.error("Error indexing %s: %s", file_str, e)
            return IndexResult(total_files=1, failed=1, errors=[f"{file_str}: {e}"])

    async def _index_single_file_content(self, file_path: str, tier: int, result: IndexResult) -> None:
        """Read, chunk, and index a single file. Helper for index_all (#1385)."""
        rel_path = os.path.relpath(file_path, self._root_dir)
        try:
            # #7467: was sync `Path(file_path).read_text` blocking the event loop.
            content = await asyncio.to_thread(Path(file_path).read_text, encoding="utf-8")
            if not content.strip():
                result.skipped += 1
                return

            indexed, total_chunks = await self._index_file_chunks(file_path, content, rel_path, tier)
            if total_chunks == 0:
                result.skipped += 1
                return

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

    def _find_collection_config(self, indexed_paths: List[str]):
        """Return the first CollectionConfig whose paths overlap with indexed_paths.

        Matches when any indexed path contains one of the collection's path prefixes
        as a substring (e.g. ``docs/architecture`` found in an absolute path).
        Returns None if no collection matches or the schema is empty.
        """
        for col_cfg in self.synthesis_schema.collections:
            for cfg_path in col_cfg.paths:
                if any(cfg_path in p for p in indexed_paths):
                    return col_cfg
        return None

    async def _run_kb_synthesis(self, indexed_paths: List[str]) -> None:
        """Run KBSynthesizer after tier ingest (best-effort, Issue #4564/#4614).

        Looks up the matching CollectionConfig from synthesis_schema and passes it
        to synthesize_docs() so the schema-driven prompt_template is used.
        Errors are logged and swallowed so indexing is never interrupted.
        KBSynthesizer is imported lazily to avoid circular imports.
        """
        try:
            from services.knowledge.kb_synthesizer import get_kb_synthesizer

            synthesizer = get_kb_synthesizer(self._llm_service)
            collection_config = self._find_collection_config(indexed_paths)
            if collection_config:
                logger.debug(
                    "DocIndexerService: synthesis using collection config '%s'",
                    collection_config.name,
                )
            await synthesizer.synthesize_docs(indexed_paths, collection_config=collection_config)
        except Exception:
            logger.exception("DocIndexerService: KB synthesis failed (non-fatal)")

    def plan(self, force: bool = False, tier: int | None = None, category: str | None = None) -> List[Tuple[str, int]]:
        """Files index_all would embed (the dry-run view, #18129); touches no store."""
        files = _select_files(self._root_dir, tier, category)
        return files if force else _filter_changed_files(files, _load_hash_cache(), self._root_dir)[0]

    def resolve_tier(self, file_path: Path) -> int:
        """Tier of a discovered file; 3 when it is outside the discovery set (#18129)."""
        return dict(_discover_files(self._root_dir)).get(str(file_path), 3)

    async def index_all(self, force: bool = False, tier: int | None = None, category: str | None = None) -> IndexResult:
        """Index every documentation file (or one ``tier`` / ``category``); force ignores the hash cache."""
        start_time = time.time()

        if not self._initialized:
            if not await self.initialize():
                return IndexResult(errors=["Failed to initialize"])

        files = _select_files(self._root_dir, tier, category)
        total_result = IndexResult(total_files=len(files))

        if not files:
            logger.warning("No documentation files discovered in %s", self._root_dir)
            return total_result
        force, refused = self._begin_run(force, len(files))
        if refused:
            return refused
        planned = self._plan_run(force, files, total_result, start_time)
        if planned is None:
            return total_result
        files, new_hashes = planned

        logger.info("Indexing %d documentation files...", len(files))
        indexed_paths = await self._index_listed_files(files, total_result, start_time)
        if indexed_paths:  # Issue #4564: KBSynthesizer after ingest (best-effort)
            fire_and_forget(self._run_kb_synthesis(indexed_paths), name="doc-indexer-kb-synthesis")
        self._record_run(new_hashes)
        total_result.elapsed_seconds = round(time.time() - start_time, 2)
        store_guard.log_run_summary(total_result, self._collection)
        return total_result

    def _begin_run(self, force: bool, file_count: int) -> tuple[bool, IndexResult | None]:
        """Log the run start and decide force; a refusal comes back as a failed result (#20886)."""
        store_guard.log_run_start(self.embedding_model_name, get_ollama_url())
        self._embed_progress = store_guard.EmbedProgress()
        try:
            return self._resolve_force(force), None
        except (store_guard.CollectionCountUnknown, store_guard.StoreLocationChanged) as e:
            logger.error("Doc indexer refusing to re-embed: %s", e)
            return force, IndexResult(total_files=file_count, errors=[str(e)])

    def _plan_run(self, force, files, total_result, start_time):
        """(files to embed, new hashes), or None when nothing changed. Force hashes every file."""
        if force:
            return _filter_changed_files(files, {}, self._root_dir)
        files, new_hashes, early = self._apply_incremental_filter(files, total_result, start_time)
        return None if early else (files, new_hashes)

    def _resolve_force(self, force: bool) -> bool:
        """Whether this run re-embeds everything; raises on an unknown count or a moved store (#20886)."""
        reason = None if force else self._full_reindex_reason()  # empty collection forces a full index (#4350)
        if reason or force:
            logger.info("Full reindex: %s", reason or "force requested")
        self._needs_reindex = False  # #10420: the dim-mismatch recreate is honoured by this run
        return force or bool(reason)

    async def _index_listed_files(
        self, files: List[Tuple[str, int]], total_result: IndexResult, start_time: float
    ) -> List[str]:
        """Index each file in turn with per-file progress; return the paths that stored chunks."""
        return await store_guard.index_listed_files(
            self._index_single_file_content, files, total_result, start_time, self._embed_progress, self._root_dir
        )

    def _record_run(self, new_hashes: Dict[str, str]) -> None:
        """Persist the hash cache (a failed document gets no hash) and the store this run embedded into."""
        if new_hashes:
            failed = [_normalize_path(p, self._root_dir)[1] for p in self._embed_progress.failed]
            recorded = store_guard.load_recorded_store(HASH_CACHE_FILE)
            same_store = recorded in (None, self._store)
            _save_hash_cache(store_guard.surviving_hashes(_load_hash_cache(), new_hashes, failed, same_store))
            store_guard.save_recorded_store(self._store, HASH_CACHE_FILE)

    async def open_store_for_adoption(self) -> tuple[str, Any]:
        """The configured store and its existing collection, without initialising or recreating it (#20886)."""
        return await store_guard.open_store_for_adoption(self._root_dir, self.COLLECTION_NAME)

    async def rebuild_from_scratch(self) -> IndexResult:
        """Delete the collection and re-index only what the current tree contains (#16934).

        Even ``index_all(force=True)`` never removes a chunk: discovery walks files
        that exist now, so a chunk from a file absent here (e.g. one indexed from a
        branch before Issue #16934 gated indexing to main-at-origin-tip) survives
        indefinitely. Deleting the collection first is the only way to guarantee that.
        """
        if not self._initialized:
            if not await self.initialize():
                return IndexResult(errors=["Failed to initialize"])
        self._client.delete_collection(self.COLLECTION_NAME)
        self._initialized = False
        self._collection = None
        return await self.index_all(force=True)

    async def enqueue_reindex(
        self,
        document_path: str,
        reason: "SyncReason | str" = "manual",
    ) -> "SyncQueueEntry":
        """Persist a re-indexing work item instead of re-embedding in-line.

        Issue #4453: routing re-indexing through :class:`DocumentSyncQueue`
        gives us retry, priority ordering, and crash-safety that the old
        fire-and-forget path lacked.  Callers that need an immediate synchronous
        index should continue to use :meth:`index_file` directly.

        ``reason`` accepts either a :class:`SyncReason` enum value or the
        string form (``content_changed`` / ``model_updated`` / ``manual``).
        """
        from services.knowledge.sync_queue import (
            SyncReason,
            get_document_sync_queue,
        )

        reason_enum = reason if isinstance(reason, SyncReason) else SyncReason(reason)
        return await get_document_sync_queue().enqueue_sync(document_path, reason_enum)

    async def search(self, query: str, n_results: int = 5) -> List[Any]:
        """Query the autobot_docs ChromaDB collection.

        Issue #4953: expose doc search so RAGService can merge results with
        the main KB, giving the agent access to AutoBot's own documentation.

        Returns RankedResult objects (from advanced_rag_optimizer).
        Returns an empty list if not initialised, collection is empty, or on
        any error — callers always receive a safe (possibly empty) list.
        """
        from advanced_rag_optimizer import RankedResult

        if not self._initialized or self._collection is None or self._embed_model is None:
            return []

        doc_count = self._collection.count()
        if doc_count == 0:
            return []

        k = min(n_results, doc_count)
        try:
            embedding: list = await asyncio.to_thread(self._embed_model.get_text_embedding, query)
            raw = await asyncio.to_thread(
                self._collection.query,
                query_embeddings=[embedding],
                n_results=k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.warning("autobot_docs search failed: %s", exc)
            return []

        documents = raw.get("documents", [[]])[0]
        metadatas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]
        row_ids = (raw.get("ids") or [[""] * len(documents)])[0]

        results = []
        for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
            score = max(0.0, 1.0 - dist)  # ChromaDB cosine distance → similarity score
            results.append(
                RankedResult(
                    content=doc or "",
                    metadata={**carry_store_id(meta, row_ids[i] if i < len(row_ids) else ""), "source": "autobot_docs"},
                    semantic_score=score,
                    keyword_score=0.0,
                    hybrid_score=score,
                    relevance_rank=i,
                    source_path=meta.get("file_path", ""),
                    chunk_index=int(meta.get("chunk_index", i)),
                )
            )
        return results


# ============================================================================
# SINGLETON
# ============================================================================

_doc_indexer: DocIndexerService | None = None
_doc_indexer_lock = threading.Lock()


def get_doc_indexer_service(llm_service: Any | None = None) -> DocIndexerService:
    """Get or create the global DocIndexerService instance (thread-safe).

    Args:
        llm_service: LLM service for KB synthesis.  When omitted the factory
            resolves the process-level singleton from ``services.llm_service``
            so DocIndexerService is never created with ``llm_service=None``.
    """
    global _doc_indexer
    if _doc_indexer is None:
        with _doc_indexer_lock:
            if _doc_indexer is None:
                if llm_service is None:
                    try:
                        from services.llm_service import get_llm_service

                        llm_service = get_llm_service()
                    except Exception:
                        logger.warning(
                            "get_doc_indexer_service: could not resolve LLM service " "— KB synthesis will be disabled"
                        )
                _doc_indexer = DocIndexerService(llm_service=llm_service)
    return _doc_indexer
