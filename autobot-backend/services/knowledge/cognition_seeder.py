# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cognition Store Seeder Service — Issue #4679

Pre-populates ChromaDB with curated foundational knowledge from a YAML manifest
to prevent cold-start problems in synthesis and RAG retrieval.

Seeds are stored in a dedicated ``cognition_store`` collection with metadata
flags ``seeded: true`` and ``seed_priority: high/medium/low`` so that
AdvancedRAGOptimizer can apply a retrieval score boost.
"""

import asyncio
import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

import yaml

from autobot_shared.logging_manager import get_logger
from constants.path_constants import PATH

if TYPE_CHECKING:
    from knowledge.backends import BaseClient

logger = get_logger(__name__)

# Priority label → numeric boost applied by AdvancedRAGOptimizer
SEED_PRIORITY_BOOST: Dict[str, float] = {
    "high": 0.15,
    "medium": 0.08,
    "low": 0.03,
}

# Collection used for all seeded documents
COGNITION_COLLECTION = "cognition_store"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SeedSource:
    """One source entry inside a cognition_seed.yaml collection block."""

    path: str
    priority: str = "medium"  # high | medium | low
    refresh: str = "never"  # never | daily | on_change


@dataclass
class SeedCollection:
    """One collection block in the manifest."""

    name: str
    sources: List[SeedSource] = field(default_factory=list)


@dataclass
class SeedManifest:
    """Parsed cognition_seed.yaml."""

    collections: List[SeedCollection] = field(default_factory=list)


@dataclass
class SeedStatus:
    """Status of a seeded collection returned by get_seed_status()."""

    collection: str
    seeded_at: str | None
    document_count: int
    sources: List[str]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_manifest(manifest_path: str) -> SeedManifest:
    """Parse a cognition_seed.yaml file into a SeedManifest."""
    p = Path(manifest_path)
    if not p.is_file():
        raise FileNotFoundError(f"Seed manifest not found: {manifest_path}")

    with open(str(p), encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    collections: List[SeedCollection] = []
    for coll_data in raw.get("collections", []):
        sources = [
            SeedSource(
                path=src["path"],
                priority=src.get("priority", "medium"),
                refresh=src.get("refresh", "never"),
            )
            for src in coll_data.get("sources", [])
        ]
        collections.append(SeedCollection(name=coll_data.get("name", COGNITION_COLLECTION), sources=sources))

    return SeedManifest(collections=collections)


def _chunk_text(content: str, max_chars: int = 1500) -> List[str]:
    """Split *content* into chunks of at most *max_chars* at paragraph boundaries."""
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    chunks: List[str] = []
    current = ""
    for para in paragraphs:
        if current and len(current) + len(para) + 2 > max_chars:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}".strip() if current else para
    if current:
        chunks.append(current)
    return chunks or [content]


def _chunk_id(collection: str, rel_path: str, chunk_index: int) -> str:
    """Stable deterministic ID for a seed chunk."""
    key = f"seed:{collection}:{rel_path}:{chunk_index}"
    return hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()[:16]


# ---------------------------------------------------------------------------
# CognitionSeeder
# ---------------------------------------------------------------------------


class CognitionSeeder:
    """
    Seeds ChromaDB with curated foundational knowledge from a YAML manifest.

    Issue #4679: prevents cold-start degradation in RAG and synthesis.
    """

    def __init__(self) -> None:
        # Backend-agnostic handles (#5062, #5194). Resolved in
        # ``_ensure_initialized()`` to a ``BaseClient``; the concrete
        # production backend is ChromaDB today.
        self._client: "BaseClient" | None = None
        self._embed_model = None
        self._initialized = False
        self._root_dir: Path = PATH.PROJECT_ROOT

    async def _ensure_initialized(self) -> bool:
        """Lazy-initialize vector-store client and embedding model."""
        if self._initialized:
            return True
        try:
            from llama_index.embeddings.ollama import OllamaEmbedding

            from autobot_shared.ssot_config import get_ollama_url
            from knowledge.backends import get_default_client

            chromadb_path = self._root_dir / "data" / "chromadb"
            self._client = await asyncio.to_thread(get_default_client, db_path=str(chromadb_path))
            ollama_url = get_ollama_url()
            self._embed_model = OllamaEmbedding(model_name="nomic-embed-text", base_url=ollama_url)
            self._initialized = True
            logger.info("CognitionSeeder initialized (chromadb_path=%s)", chromadb_path)
            return True
        except Exception as exc:
            logger.error("CognitionSeeder initialization failed: %s", exc)
            return False

    def _get_or_create_collection(self, name: str):
        """Return (or create) a ChromaDB collection with cosine distance."""
        return self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def _upsert_chunk(
        self,
        collection,
        chunk_id: str,
        content: str,
        metadata: Dict[str, Any],
    ) -> None:
        """Embed *content* and upsert into *collection* (runs in executor thread)."""
        embedding = self._embed_model.get_text_embedding(content)
        collection.upsert(
            ids=[chunk_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[metadata],
        )

    async def _seed_file(
        self,
        file_path: str,
        collection_name: str,
        priority: str,
        now_iso: str,
    ) -> int:
        """Index one file into *collection_name*. Returns number of chunks stored."""
        abs_path = os.path.join(str(self._root_dir), file_path) if not os.path.isabs(file_path) else file_path

        if not os.path.isfile(abs_path):
            logger.warning("Seed file not found, skipping: %s", abs_path)
            return 0

        try:
            # #7467: was sync `Path(abs_path).read_text` blocking the event loop.
            content = await asyncio.to_thread(Path(abs_path).read_text, encoding="utf-8")
        except OSError as exc:
            logger.warning("Cannot read seed file %s: %s", abs_path, exc)
            return 0

        if not content.strip():
            return 0

        rel_path = os.path.relpath(abs_path, str(self._root_dir))
        chunks = _chunk_text(content)
        coll = self._get_or_create_collection(collection_name)
        stored = 0

        for idx, chunk_text in enumerate(chunks):
            cid = _chunk_id(collection_name, rel_path, idx)
            metadata: Dict[str, Any] = {
                "seeded": "true",
                "seed_priority": priority,
                "seed_collection": collection_name,
                "source": "cognition_store",
                "relative_path": rel_path,
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "seeded_at": now_iso,
            }
            try:
                await asyncio.to_thread(self._upsert_chunk, coll, cid, chunk_text, metadata)
                stored += 1
            except Exception as exc:
                logger.error("Failed to upsert seed chunk %s[%d]: %s", rel_path, idx, exc)

        return stored

    async def _seed_directory(
        self,
        dir_path: str,
        collection_name: str,
        priority: str,
        now_iso: str,
    ) -> int:
        """Recursively index all .md and .txt files under *dir_path*."""
        abs_dir = os.path.join(str(self._root_dir), dir_path) if not os.path.isabs(dir_path) else dir_path
        if not os.path.isdir(abs_dir):
            logger.warning("Seed directory not found, skipping: %s", abs_dir)
            return 0

        tasks = []
        for root, _dirs, files in os.walk(abs_dir):
            for fname in files:
                if fname.endswith((".md", ".txt", ".rst")):
                    tasks.append(
                        self._seed_file(
                            os.path.join(root, fname),
                            collection_name,
                            priority,
                            now_iso,
                        )
                    )

        if not tasks:
            return 0

        results = await asyncio.gather(*tasks, return_exceptions=True)
        total = 0
        for r in results:
            if isinstance(r, Exception):
                logger.error("Seed task error: %s", r)
            else:
                total += r
        return total

    async def seed_from_directory(
        self, path: str, collection: str = COGNITION_COLLECTION, priority: str = "medium"
    ) -> int:
        """Seed a single directory into *collection*.

        Returns the number of chunks upserted.
        """
        if not await self._ensure_initialized():
            return 0
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        count = await self._seed_directory(path, collection, priority, now_iso)
        logger.info(
            "seed_from_directory: path=%s collection=%s priority=%s chunks=%d",
            path,
            collection,
            priority,
            count,
        )
        return count

    async def seed_from_manifest(self, manifest_path: str) -> int:
        """Seed all sources declared in *manifest_path*.

        Returns total number of chunks upserted across all collections.
        """
        if not await self._ensure_initialized():
            return 0

        try:
            manifest = _load_manifest(manifest_path)
        except Exception as exc:
            logger.error("Failed to load seed manifest %s: %s", manifest_path, exc)
            return 0

        now_iso = datetime.now(tz=timezone.utc).isoformat()
        total = 0
        for coll in manifest.collections:
            for src in coll.sources:
                src_path = src.path
                priority = src.priority
                if os.path.isdir(
                    os.path.join(str(self._root_dir), src_path) if not os.path.isabs(src_path) else src_path
                ):
                    count = await self._seed_directory(src_path, coll.name, priority, now_iso)
                else:
                    count = await self._seed_file(src_path, coll.name, priority, now_iso)
                logger.info(
                    "Seeded source '%s' → collection '%s' (priority=%s): %d chunks",
                    src_path,
                    coll.name,
                    priority,
                    count,
                )
                total += count

        logger.info("seed_from_manifest complete: total_chunks=%d", total)
        return total

    async def get_seed_status(self) -> List[SeedStatus]:
        """Return status for all seeded collections.

        Each entry reports the collection name, when seeding last ran, the number
        of seeded documents, and the source paths that contributed them.
        """
        if not await self._ensure_initialized():
            return []

        statuses: List[SeedStatus] = []
        try:
            all_collections = self._client.list_collections()
        except Exception as exc:
            logger.error("Failed to list ChromaDB collections: %s", exc)
            return []

        for coll_meta in all_collections:
            coll_name = coll_meta.name if hasattr(coll_meta, "name") else str(coll_meta)
            try:
                coll = self._client.get_collection(coll_name)
                results = coll.get(where={"seeded": "true"}, include=["metadatas"])
                metas = results.get("metadatas") or []
                if not metas:
                    continue

                seeded_ats = [m.get("seeded_at") for m in metas if m.get("seeded_at")]
                latest = max(seeded_ats) if seeded_ats else None
                sources = list({m.get("relative_path", "") for m in metas if m.get("relative_path")})

                statuses.append(
                    SeedStatus(
                        collection=coll_name,
                        seeded_at=latest,
                        document_count=len(metas),
                        sources=sorted(sources),
                    )
                )
            except Exception as exc:
                logger.warning("Error reading seed status for collection %s: %s", coll_name, exc)

        return statuses


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_seeder: CognitionSeeder | None = None
_seeder_lock = asyncio.Lock()


async def get_cognition_seeder() -> CognitionSeeder:
    """Return the module-level CognitionSeeder singleton (thread-safe)."""
    global _seeder
    async with _seeder_lock:
        if _seeder is None:
            _seeder = CognitionSeeder()
    return _seeder
