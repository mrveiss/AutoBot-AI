# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Documentation Indexer Service

Issue #1385: Consolidated documentation indexing with ChromaDB as single source of truth.
Extracted from autobot-infrastructure/shared/tools/index_documentation.py and adapted
for service use (SSOT config, proper path constants, thread-safe singleton).

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

from autobot_shared.logging_manager import get_logger

if TYPE_CHECKING:
    from services.knowledge.sync_queue import SyncQueueEntry, SyncReason  # noqa: F401

from autobot_shared.ssot_config import get_ollama_url
from constants.path_constants import PATH
from knowledge.query_sanitizer import sanitize_document as _sanitize_document
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
# TIER DEFINITIONS (from CLI tool)
# ============================================================================

TIER_1_FILES = [
    "CLAUDE.md",
    "docs/system-state.md",
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


def _parse_frontmatter(content: str) -> Tuple[str, List[str], List[str]]:
    """Strip Obsidian YAML frontmatter and return (body, tags, aliases).

    Recognises a leading ``---`` block. Returns the content after the closing
    ``---`` together with any ``tags`` and ``aliases`` values found inside it.
    If no frontmatter is present the original content is returned unchanged
    with empty tag and alias lists.
    """
    if not content.startswith("---"):
        return content, [], []

    end = content.find("\n---", 3)
    if end == -1:
        return content, [], []

    fm_block = content[3:end]
    body = content[end + 4 :].lstrip("\n")

    fm_tags: List[str] = []
    fm_aliases: List[str] = []

    # Parse simple YAML list values for 'tags' and 'aliases' keys.
    current_key: str | None = None
    for line in fm_block.splitlines():
        key_match = re.match(r"^(\w+)\s*:", line)
        if key_match:
            current_key = key_match.group(1)
            inline = line[key_match.end() :].strip()
            if inline and current_key in ("tags", "aliases"):
                target = fm_tags if current_key == "tags" else fm_aliases
                target.append(inline.lstrip("- ").strip())
        elif line.strip().startswith("-") and current_key in ("tags", "aliases"):
            target = fm_tags if current_key == "tags" else fm_aliases
            target.append(line.strip().lstrip("- ").strip())

    return body, fm_tags, fm_aliases


def _estimate_tokens(text: str) -> int:
    """Estimate token count (~4 chars per token)."""
    return len(text) // 4


def _create_chunk(
    content: str,
    section: str,
    subsection: str | None,
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
    subsection_name: str | None,
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


def _discover_files(root_dir: Path, tier: int | None = None) -> List[Tuple[str, int]]:
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
    """Compute SHA-256 hash of file content.

    Resolves symlinks so the hash reflects the target file's content (#4382).
    Returns empty string on PermissionError, OSError, or RuntimeError (e.g.
    circular symlinks raise RuntimeError on Python 3.10+); callers must
    preserve the cached hash when empty to avoid false-changed detection.
    """
    try:
        resolved = str(Path(file_path).resolve())
        with open(resolved, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except (PermissionError, OSError, RuntimeError) as e:
        logger.warning("Cannot hash %s: %s", file_path, e)
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

            chromadb_path = self._root_dir / "data" / "chromadb"
            # get_default_client takes only **kwargs (#6613) — pass db_path
            # explicitly. Positional call raised TypeError at init, falling
            # the indexer back to slow SCAN paths.
            self._client = await asyncio.to_thread(get_default_client, db_path=str(chromadb_path))

            ollama_url = get_ollama_url()

            # Issue #4451: per-org embedding model config, SSOT fallback.
            # Resolved before collection creation so embedding_model metadata
            # can be written at first-create time (#7427).
            from services.knowledge.org_knowledge_config import (
                get_org_knowledge_config_service,
            )

            effective = await get_org_knowledge_config_service().get_effective(self._org_id)
            embed_model_name = effective.embedding_model or "nomic-embed-text"
            self.embedding_model_name = embed_model_name

            # Embed model is created first so the collection guard can probe the
            # model's true dimension when it is not in _KNOWN_DIMS (#10420).
            self._embed_model = OllamaEmbedding(model_name=embed_model_name, base_url=ollama_url)

            embed_dim = await asyncio.to_thread(
                self._resolve_embed_dim, embed_model_name, effective.embedding_dimension
            )
            self._collection = await asyncio.to_thread(
                self._resolve_collection, embed_model_name, embed_dim
            )

            doc_count = self._collection.count()
            logger.info(
                "DocIndexerService initialized: collection='%s', "
                "existing_vectors=%d, ollama=%s, embed_model=%s, org_id=%s",
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

    def _embed_and_upsert(
        self,
        content: str,
        chunk_id: str,
        metadata: Dict[str, Any],
    ) -> None:
        """Embed *content* and upsert into ChromaDB. Raises on failure."""
        embedding = self._embed_model.get_text_embedding(content)
        self._collection.upsert(
            ids=[chunk_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[metadata],
        )

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
        chunk_id = hashlib.md5(
            f"{rel_path}:{chunk['section']}:{chunk_index}".encode(), usedforsecurity=False
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
            "indexed_at": datetime.now(tz=timezone.utc).isoformat(),
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
        return False

    async def _index_file_chunks(self, file_str: str, content: str, rel_path: str, tier: int) -> tuple[int, int]:
        """Chunk content and index all chunks; return (success_count, chunk_count). Issue #2735.

        Extracted from index_file to keep parent under 65 lines.
        """
        import asyncio

        body, fm_tags, fm_aliases = _parse_frontmatter(content)
        # Issue #5064: sanitize ingested content before chunking / embedding.
        body = _sanitize_document(body, source="doc_indexer").sanitized_text
        chunks = _chunk_markdown(body, file_str)
        if not chunks:
            return 0, 0

        file_tags = _extract_tags(body, file_str)
        file_tags = list(dict.fromkeys(fm_tags + fm_aliases + file_tags))[:20]
        indexed = 0
        for i, chunk in enumerate(chunks):
            ok = await asyncio.to_thread(self._index_chunk, chunk, i, len(chunks), rel_path, file_tags, tier)
            if ok:
                indexed += 1
        return indexed, len(chunks)

    async def index_file(self, file_path: Path, tier: int = 3, force: bool = False) -> IndexResult:
        """Index a single documentation file into ChromaDB.

        Args:
            file_path: Path to the markdown file.
            tier: Priority tier (1=critical, 2=high, 3=medium).
            force: If True, skip hash check.

        Returns:
            IndexResult with counts.
        """
        if not self._initialized:
            await self.initialize()

        result = IndexResult(total_files=1)
        file_str = str(file_path)

        if not file_path.exists():
            result.failed = 1
            result.errors.append(f"File not found: {file_str}")
            return result

        if self._check_hash_and_update_cache(file_str, force):
            result.skipped = 1
            return result

        try:
            # #7467: was sync `file_path.read_text` blocking the event loop.
            content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
            if not content.strip():
                result.skipped = 1
                return result

            rel_path = os.path.relpath(file_str, self._root_dir)
            indexed, total_chunks = await self._index_file_chunks(file_str, content, rel_path, tier)

            if total_chunks == 0:
                result.skipped = 1
                return result

            result.success = 1 if indexed > 0 else 0
            result.failed = 0 if indexed > 0 else 1
            return result

        except Exception as e:
            logger.error("Error indexing %s: %s", file_str, e)
            result.failed = 1
            result.errors.append(f"{file_str}: {e}")
            return result

    async def _index_single_file_content(self, file_path: str, tier: int, result: IndexResult) -> None:
        """Read, chunk, and index a single file. Helper for index_all (#1385)."""
        rel_path = os.path.relpath(file_path, self._root_dir)
        try:
            # #7467: was sync `Path(file_path).read_text` blocking the event loop.
            content = await asyncio.to_thread(Path(file_path).read_text, encoding="utf-8")
            if not content.strip():
                result.skipped += 1
                return

            body, fm_tags, fm_aliases = _parse_frontmatter(content)
            # Issue #5064: sanitize ingested content before chunking / embedding.
            body = _sanitize_document(body, source="doc_indexer").sanitized_text
            chunks = _chunk_markdown(body, file_path)
            if not chunks:
                result.skipped += 1
                return

            file_tags = _extract_tags(body, file_path)
            file_tags = list(dict.fromkeys(fm_tags + fm_aliases + file_tags))[:20]
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

        # If collection is empty, force full indexing regardless of cache (#4350)
        if not force and self.needs_indexing():
            logger.info(
                "Collection empty — forcing full indexing despite cache to ensure " "documentation is available"
            )
            force = True
        # Issue #10420: a dim-mismatch recreate has now been honoured by forcing
        # a full re-embed; clear the flag so a later init is idempotent.
        self._needs_reindex = False

        # Incremental mode: filter to changed files
        new_hashes: Dict[str, str] = {}
        if not force:
            files, new_hashes, early = self._apply_incremental_filter(files, total_result, start_time)
            if early:
                return total_result
        else:
            # In force mode, compute hashes for all files to update cache
            hash_cache = {}  # Empty cache treats all as changed
            files, new_hashes = _filter_changed_files(files, hash_cache, self._root_dir)

        logger.info("Indexing %d documentation files...", len(files))
        indexed_paths: List[str] = []
        for file_path, tier in files:
            before = total_result.success
            await self._index_single_file_content(file_path, tier, total_result)
            if total_result.success > before:
                indexed_paths.append(file_path)

        # Issue #4564: trigger KBSynthesizer after ingest (best-effort, non-blocking)
        if indexed_paths:
            asyncio.ensure_future(self._run_kb_synthesis(indexed_paths))

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

        Returns SearchResult objects (from advanced_rag_optimizer).
        Returns an empty list if not initialised, collection is empty, or on
        any error — callers always receive a safe (possibly empty) list.
        """
        import asyncio

        from advanced_rag_optimizer import SearchResult

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

        results = []
        for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
            # ChromaDB cosine distance → similarity score
            score = max(0.0, 1.0 - dist)
            results.append(
                SearchResult(
                    content=doc or "",
                    metadata={**meta, "source": "autobot_docs"},
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
