# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
GPU-Accelerated Vector Search - Hybrid FAISS-GPU + ChromaDB Architecture

Provides high-performance similarity search by combining:
- FAISS-GPU: GPU-accelerated similarity computation (10-100x speedup)
- ChromaDB: Document storage, metadata management, persistence

This hybrid approach gives best of both worlds:
- Fast GPU similarity search for large vector collections
- Rich metadata filtering and document retrieval from ChromaDB
- Automatic fallback to CPU when GPU unavailable

Issue #387: GPU-Accelerated Vector Search Implementation
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# FAISS import with graceful fallback
try:
    import faiss

    if hasattr(faiss, "StandardGpuResources"):
        FAISS_GPU_AVAILABLE = True
        FAISS_AVAILABLE = True
    else:
        FAISS_GPU_AVAILABLE = False
        FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    FAISS_GPU_AVAILABLE = False
    faiss = None

# ChromaDB import
try:
    import chromadb

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    chromadb = None

logger = logging.getLogger(__name__)


class IndexType(Enum):
    """FAISS index types with different performance characteristics."""

    FLAT_L2 = "flat_l2"  # Exact search, O(n) but fast on GPU
    FLAT_IP = "flat_ip"  # Inner product (cosine with normalized vectors)
    IVF_FLAT = "ivf_flat"  # Inverted file index, faster for large datasets
    IVF_PQ = "ivf_pq"  # Product quantization, memory efficient
    HNSW = "hnsw"  # Hierarchical NSW, good recall/speed tradeoff


class SearchBackend(Enum):
    """Available search backends."""

    FAISS_GPU = "faiss_gpu"
    FAISS_CPU = "faiss_cpu"
    CHROMADB = "chromadb"


@dataclass
class VectorSearchConfig:
    """Configuration for GPU vector search."""

    # Index settings
    index_type: IndexType = IndexType.FLAT_IP
    embedding_dim: int = 384  # sentence-transformers default
    use_gpu: bool = True
    gpu_device: int = 0

    # IVF settings (if using IVF index types)
    nlist: int = 100  # Number of clusters for IVF
    nprobe: int = 10  # Number of clusters to search

    # Performance settings
    batch_size: int = 1000
    max_vectors_in_memory: int = 1_000_000

    # Persistence
    index_path: Optional[str] = None
    auto_save: bool = True
    save_interval_seconds: int = 300


@dataclass
class SearchResult:
    """Individual search result."""

    doc_id: str
    score: float
    distance: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    content: Optional[str] = None


@dataclass
class SearchMetrics:
    """Performance metrics for search operation."""

    query_time_ms: float
    total_vectors_searched: int
    results_returned: int
    backend_used: SearchBackend
    gpu_utilized: bool
    index_type: str


class GPUVectorIndex:
    """
    GPU-accelerated FAISS index wrapper.

    Provides fast similarity search on GPU with automatic fallback to CPU.
    Designed to work alongside ChromaDB for document storage.
    """

    def __init__(self, config: VectorSearchConfig):
        """Initialize GPU vector index."""
        self.config = config
        self.index: Optional[Any] = None
        self.gpu_resources: Optional[Any] = None
        self.id_map: Dict[int, str] = {}  # FAISS internal ID → document ID
        self.reverse_id_map: Dict[str, int] = {}  # document ID → FAISS internal ID
        self.next_id: int = 0
        self.is_trained: bool = False
        self._lock = asyncio.Lock()

        # Backend tracking
        self.backend = SearchBackend.CHROMADB  # Default fallback
        self.last_save_time: Optional[datetime] = None

    async def initialize(self) -> bool:
        """Initialize the FAISS index with GPU support if available."""
        if not FAISS_AVAILABLE:
            logger.warning("FAISS not available. Install with: pip install faiss-gpu")
            return False

        try:
            async with self._lock:
                # Check for WSL environment - GPU operations can hang in WSL
                is_wsl = self._detect_wsl()
                use_gpu = self.config.use_gpu and FAISS_GPU_AVAILABLE and not is_wsl

                if is_wsl and self.config.use_gpu:
                    logger.info(
                        "WSL environment detected - using CPU mode "
                        "(GPU operations may hang in WSL)"
                    )

                # Try GPU initialization first (skip in WSL)
                if use_gpu:
                    success = await self._initialize_gpu_index()
                    if success:
                        self.backend = SearchBackend.FAISS_GPU
                        logger.info(
                            f"✅ GPU Vector Index initialized on device {self.config.gpu_device}"
                        )
                        return True

                # Fall back to CPU
                success = await self._initialize_cpu_index()
                if success:
                    self.backend = SearchBackend.FAISS_CPU
                    logger.info("✅ CPU Vector Index initialized (GPU fallback)")
                    return True

                return False

        except Exception as e:
            logger.error("Failed to initialize vector index: %s", e)
            return False

    def _detect_wsl(self) -> bool:
        """Detect if running in Windows Subsystem for Linux."""
        try:
            with open("/proc/version", "r") as f:
                return "microsoft" in f.read().lower()
        except Exception:
            return False

    async def _initialize_gpu_index(self) -> bool:
        """Initialize FAISS index on GPU."""
        try:
            # Create GPU resources
            self.gpu_resources = faiss.StandardGpuResources()

            # Create base CPU index first
            cpu_index = self._create_base_index()

            # Transfer to GPU
            self.index = faiss.index_cpu_to_gpu(
                self.gpu_resources, self.config.gpu_device, cpu_index
            )

            logger.info(
                f"✅ FAISS GPU index created: {self.config.index_type.value}, "
                f"dim={self.config.embedding_dim}"
            )
            return True

        except Exception as e:
            logger.warning("GPU index initialization failed: %s", e)
            return False

    async def _initialize_cpu_index(self) -> bool:
        """Initialize FAISS index on CPU."""
        try:
            self.index = self._create_base_index()
            logger.info(
                f"✅ FAISS CPU index created: {self.config.index_type.value}, "
                f"dim={self.config.embedding_dim}"
            )
            return True
        except Exception as e:
            logger.error("CPU index initialization failed: %s", e)
            return False

    def _create_base_index(self) -> Any:
        """Create base FAISS index based on configuration."""
        dim = self.config.embedding_dim

        if self.config.index_type == IndexType.FLAT_L2:
            return faiss.IndexFlatL2(dim)

        elif self.config.index_type == IndexType.FLAT_IP:
            return faiss.IndexFlatIP(dim)

        elif self.config.index_type == IndexType.IVF_FLAT:
            quantizer = faiss.IndexFlatIP(dim)
            index = faiss.IndexIVFFlat(quantizer, dim, self.config.nlist)
            return index

        elif self.config.index_type == IndexType.IVF_PQ:
            quantizer = faiss.IndexFlatIP(dim)
            # PQ with 8 sub-quantizers
            index = faiss.IndexIVFPQ(quantizer, dim, self.config.nlist, 8, 8)
            return index

        elif self.config.index_type == IndexType.HNSW:
            index = faiss.IndexHNSWFlat(dim, 32)  # 32 neighbors
            index.hnsw.efConstruction = 200
            index.hnsw.efSearch = 64
            return index

        else:
            # Default to flat IP
            return faiss.IndexFlatIP(dim)

    async def add_vectors(
        self,
        embeddings: np.ndarray,
        doc_ids: List[str],
        normalize: bool = True,
    ) -> int:
        """
        Add vectors to the index.

        Args:
            embeddings: Numpy array of shape (n, dim)
            doc_ids: List of document IDs corresponding to embeddings
            normalize: Whether to L2-normalize vectors (recommended for cosine similarity)

        Returns:
            Number of vectors added
        """
        if self.index is None:
            raise RuntimeError("Index not initialized. Call initialize() first.")

        if len(embeddings) != len(doc_ids):
            raise ValueError("Number of embeddings must match number of doc_ids")

        async with self._lock:
            # Ensure correct dtype and shape
            embeddings = np.ascontiguousarray(embeddings.astype(np.float32))

            # Normalize for cosine similarity
            if normalize:
                norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
                norms[norms == 0] = 1  # Avoid division by zero
                embeddings = embeddings / norms

            # Train index if needed (IVF indices require training)
            if not self.is_trained and hasattr(self.index, "train"):
                if self.index.is_trained:
                    self.is_trained = True
                else:
                    # Need training data
                    if len(embeddings) >= self.config.nlist:
                        await asyncio.to_thread(self.index.train, embeddings)
                        self.is_trained = True
                    else:
                        logger.warning(
                            f"Not enough vectors to train IVF index "
                            f"(need {self.config.nlist}, have {len(embeddings)})"
                        )

            # Add to index
            await asyncio.to_thread(self.index.add, embeddings)

            # Update ID mappings
            for doc_id in doc_ids:
                internal_id = self.next_id
                self.id_map[internal_id] = doc_id
                self.reverse_id_map[doc_id] = internal_id
                self.next_id += 1

            # Auto-save if configured
            if self.config.auto_save and self.config.index_path:
                await self._maybe_save()

            return len(embeddings)

    async def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
        normalize: bool = True,
    ) -> Tuple[List[SearchResult], SearchMetrics]:
        """
        Search for similar vectors.

        Args:
            query_embedding: Query vector of shape (dim,) or (1, dim)
            top_k: Number of results to return
            normalize: Whether to normalize query vector

        Returns:
            Tuple of (search results, performance metrics)
        """
        if self.index is None:
            raise RuntimeError("Index not initialized. Call initialize() first.")

        start_time = time.perf_counter()

        # Prepare query
        query = np.ascontiguousarray(query_embedding.astype(np.float32))
        if query.ndim == 1:
            query = query.reshape(1, -1)

        if normalize:
            norm = np.linalg.norm(query)
            if norm > 0:
                query = query / norm

        # Set search parameters for IVF indices
        if hasattr(self.index, "nprobe"):
            self.index.nprobe = self.config.nprobe

        # Execute search
        distances, indices = await asyncio.to_thread(self.index.search, query, top_k)

        # Convert results
        results = []
        for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
            if idx == -1:  # FAISS returns -1 for missing results
                continue

            doc_id = self.id_map.get(idx, f"unknown_{idx}")

            # Convert distance to similarity score
            # For IP (inner product), higher is better
            # For L2, lower is better - convert to similarity
            if self.config.index_type in (IndexType.FLAT_IP, IndexType.IVF_FLAT):
                score = float(dist)  # Already similarity
            else:
                score = 1.0 / (1.0 + float(dist))  # Convert L2 distance to similarity

            results.append(
                SearchResult(
                    doc_id=doc_id,
                    score=score,
                    distance=float(dist),
                )
            )

        query_time = (time.perf_counter() - start_time) * 1000

        metrics = SearchMetrics(
            query_time_ms=query_time,
            total_vectors_searched=self.index.ntotal if self.index else 0,
            results_returned=len(results),
            backend_used=self.backend,
            gpu_utilized=self.backend == SearchBackend.FAISS_GPU,
            index_type=self.config.index_type.value,
        )

        return results, metrics

    async def batch_search(
        self,
        query_embeddings: np.ndarray,
        top_k: int = 10,
        normalize: bool = True,
    ) -> Tuple[List[List[SearchResult]], SearchMetrics]:
        """
        Batch search for multiple query vectors.

        Much more efficient than individual searches on GPU.

        Args:
            query_embeddings: Query vectors of shape (n, dim)
            top_k: Number of results per query
            normalize: Whether to normalize query vectors

        Returns:
            Tuple of (list of results per query, aggregate metrics)
        """
        if self.index is None:
            raise RuntimeError("Index not initialized. Call initialize() first.")

        start_time = time.perf_counter()

        # Prepare queries
        queries = np.ascontiguousarray(query_embeddings.astype(np.float32))

        if normalize:
            norms = np.linalg.norm(queries, axis=1, keepdims=True)
            norms[norms == 0] = 1
            queries = queries / norms

        # Set search parameters
        if hasattr(self.index, "nprobe"):
            self.index.nprobe = self.config.nprobe

        # Execute batch search
        distances, indices = await asyncio.to_thread(self.index.search, queries, top_k)

        # Convert results
        all_results = []
        for q_idx in range(len(queries)):
            results = []
            for dist, idx in zip(distances[q_idx], indices[q_idx]):
                if idx == -1:
                    continue

                doc_id = self.id_map.get(idx, f"unknown_{idx}")

                if self.config.index_type in (IndexType.FLAT_IP, IndexType.IVF_FLAT):
                    score = float(dist)
                else:
                    score = 1.0 / (1.0 + float(dist))

                results.append(
                    SearchResult(doc_id=doc_id, score=score, distance=float(dist))
                )

            all_results.append(results)

        query_time = (time.perf_counter() - start_time) * 1000

        metrics = SearchMetrics(
            query_time_ms=query_time,
            total_vectors_searched=self.index.ntotal * len(queries),
            results_returned=sum(len(r) for r in all_results),
            backend_used=self.backend,
            gpu_utilized=self.backend == SearchBackend.FAISS_GPU,
            index_type=self.config.index_type.value,
        )

        return all_results, metrics

    async def remove_vectors(self, doc_ids: List[str]) -> int:
        """
        Remove vectors from index by document ID.

        Note: FAISS doesn't support direct removal for most index types.
        This marks vectors as removed and they'll be cleaned up on rebuild.
        """
        removed = 0
        for doc_id in doc_ids:
            if doc_id in self.reverse_id_map:
                internal_id = self.reverse_id_map.pop(doc_id)
                del self.id_map[internal_id]
                removed += 1

        if removed > 0:
            logger.info(
                f"Marked {removed} vectors for removal. "
                f"Rebuild index to reclaim space."
            )

        return removed

    async def save(self, path: Optional[str] = None) -> bool:
        """Save index to disk."""
        save_path = path or self.config.index_path
        if not save_path:
            logger.warning("No save path specified")
            return False

        if self.index is None:
            logger.warning("No index to save")
            return False

        try:
            save_dir = Path(save_path)
            # Issue #358 - avoid blocking
            await asyncio.to_thread(save_dir.mkdir, parents=True, exist_ok=True)

            # For GPU index, transfer to CPU first
            if self.backend == SearchBackend.FAISS_GPU:
                cpu_index = faiss.index_gpu_to_cpu(self.index)
                await asyncio.to_thread(
                    faiss.write_index, cpu_index, str(save_dir / "index.faiss")
                )
            else:
                await asyncio.to_thread(
                    faiss.write_index, self.index, str(save_dir / "index.faiss")
                )

            # Save ID mappings
            import json

            # Issue #358 - avoid blocking
            id_map_path = save_dir / "id_map.json"
            id_map_data = json.dumps(
                {str(k): v for k, v in self.id_map.items()}, ensure_ascii=False
            )

            def _write_id_map():
                with open(id_map_path, "w", encoding="utf-8") as f:
                    f.write(id_map_data)

            await asyncio.to_thread(_write_id_map)

            self.last_save_time = datetime.now()
            logger.info("✅ Index saved to %s", save_path)
            return True

        except Exception as e:
            logger.error("Failed to save index: %s", e)
            return False

    async def load(self, path: Optional[str] = None) -> bool:
        """Load index from disk."""
        load_path = path or self.config.index_path
        if not load_path:
            logger.warning("No load path specified")
            return False

        try:
            load_dir = Path(load_path)

            # Issue #358 - avoid blocking
            index_file_exists = await asyncio.to_thread((load_dir / "index.faiss").exists)
            if not index_file_exists:
                logger.warning("No index file found at %s", load_path)
                return False

            # Load CPU index
            cpu_index = await asyncio.to_thread(
                faiss.read_index, str(load_dir / "index.faiss")
            )

            # Transfer to GPU if configured
            if self.config.use_gpu and FAISS_GPU_AVAILABLE:
                self.gpu_resources = faiss.StandardGpuResources()
                self.index = faiss.index_cpu_to_gpu(
                    self.gpu_resources, self.config.gpu_device, cpu_index
                )
                self.backend = SearchBackend.FAISS_GPU
            else:
                self.index = cpu_index
                self.backend = SearchBackend.FAISS_CPU

            # Load ID mappings
            import json

            # Issue #358 - avoid blocking
            id_map_path = load_dir / "id_map.json"

            def _read_id_map():
                with open(id_map_path, "r", encoding="utf-8") as f:
                    return json.load(f)

            raw_map = await asyncio.to_thread(_read_id_map)
            self.id_map = {int(k): v for k, v in raw_map.items()}
            self.reverse_id_map = {v: int(k) for k, v in raw_map.items()}
            self.next_id = max(self.id_map.keys()) + 1 if self.id_map else 0

            self.is_trained = True
            logger.info(
                f"✅ Index loaded from {load_path} "
                f"({self.index.ntotal} vectors, backend={self.backend.value})"
            )
            return True

        except Exception as e:
            logger.error("Failed to load index: %s", e)
            return False

    async def _maybe_save(self):
        """Save if enough time has passed since last save."""
        if self.last_save_time is None:
            await self.save()
            return

        elapsed = (datetime.now() - self.last_save_time).total_seconds()
        if elapsed >= self.config.save_interval_seconds:
            await self.save()

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        return {
            "initialized": self.index is not None,
            "backend": self.backend.value if self.index else None,
            "index_type": self.config.index_type.value,
            "total_vectors": self.index.ntotal if self.index else 0,
            "embedding_dim": self.config.embedding_dim,
            "is_trained": self.is_trained,
            "gpu_available": FAISS_GPU_AVAILABLE,
            "faiss_available": FAISS_AVAILABLE,
        }


class HybridVectorSearch:
    """
    Hybrid vector search combining FAISS-GPU and ChromaDB.

    ChromaDB handles:
    - Document storage and retrieval
    - Metadata filtering
    - Persistence

    FAISS-GPU handles:
    - Fast similarity computation
    - Batch search optimization
    - Large-scale vector operations
    """

    def __init__(
        self,
        chromadb_client: Optional[Any] = None,
        config: Optional[VectorSearchConfig] = None,
    ):
        """Initialize hybrid search."""
        self.chromadb = chromadb_client
        self.config = config or VectorSearchConfig()
        self.gpu_index = GPUVectorIndex(self.config)
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize both backends."""
        # Initialize FAISS GPU index
        faiss_ok = await self.gpu_index.initialize()

        if faiss_ok:
            logger.info("✅ Hybrid Vector Search initialized with FAISS-GPU")
        else:
            logger.info("✅ Hybrid Vector Search initialized (ChromaDB fallback)")

        self._initialized = True
        return True

    async def add_documents(
        self,
        embeddings: np.ndarray,
        doc_ids: List[str],
        documents: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
        collection_name: str = "default",
    ) -> int:
        """
        Add documents to both FAISS index and ChromaDB.

        Args:
            embeddings: Document embeddings
            doc_ids: Document IDs
            documents: Document contents (for ChromaDB)
            metadatas: Document metadata (for ChromaDB)
            collection_name: ChromaDB collection name

        Returns:
            Number of documents added
        """
        added = 0

        # Add to FAISS index for fast search
        if self.gpu_index.index is not None:
            added = await self.gpu_index.add_vectors(embeddings, doc_ids)

        # Add to ChromaDB for storage and metadata
        if self.chromadb is not None and documents:
            try:
                collection = self.chromadb.get_or_create_collection(collection_name)
                collection.add(
                    ids=doc_ids,
                    embeddings=embeddings.tolist(),
                    documents=documents,
                    metadatas=metadatas or [{} for _ in doc_ids],
                )
                if added == 0:
                    added = len(doc_ids)
            except Exception as e:
                logger.error("Failed to add to ChromaDB: %s", e)

        return added

    async def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
        collection_name: str = "default",
        metadata_filter: Optional[Dict[str, Any]] = None,
        include_documents: bool = True,
    ) -> Tuple[List[SearchResult], SearchMetrics]:
        """
        Hybrid search using FAISS for speed and ChromaDB for documents.

        Args:
            query_embedding: Query vector
            top_k: Number of results
            collection_name: ChromaDB collection name
            metadata_filter: Optional metadata filter (applied in ChromaDB)
            include_documents: Whether to fetch document content

        Returns:
            Tuple of (results with documents, metrics)
        """
        # Try FAISS first for speed
        if self.gpu_index.index is not None and self.gpu_index.index.ntotal > 0:
            results, metrics = await self.gpu_index.search(query_embedding, top_k)

            # Enrich results with documents from ChromaDB
            if include_documents and self.chromadb is not None and results:
                results = await self._enrich_from_chromadb(
                    results, collection_name, metadata_filter
                )

            return results, metrics

        # Fallback to ChromaDB
        if self.chromadb is not None:
            return await self._chromadb_search(
                query_embedding, top_k, collection_name, metadata_filter
            )

        # No backend available
        return [], SearchMetrics(
            query_time_ms=0,
            total_vectors_searched=0,
            results_returned=0,
            backend_used=SearchBackend.CHROMADB,
            gpu_utilized=False,
            index_type="none",
        )

    async def _enrich_from_chromadb(
        self,
        results: List[SearchResult],
        collection_name: str,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Fetch document content and metadata from ChromaDB."""
        try:
            collection = self.chromadb.get_collection(collection_name)
            doc_ids = [r.doc_id for r in results]

            # Fetch from ChromaDB
            chromadb_results = collection.get(
                ids=doc_ids, include=["documents", "metadatas"]
            )

            # Build lookup
            doc_lookup = {}
            if chromadb_results["ids"]:
                for i, doc_id in enumerate(chromadb_results["ids"]):
                    doc_lookup[doc_id] = {
                        "content": (
                            chromadb_results["documents"][i]
                            if chromadb_results["documents"]
                            else None
                        ),
                        "metadata": (
                            chromadb_results["metadatas"][i]
                            if chromadb_results["metadatas"]
                            else {}
                        ),
                    }

            # Enrich results
            enriched = []
            for result in results:
                if result.doc_id in doc_lookup:
                    data = doc_lookup[result.doc_id]

                    # Apply metadata filter if specified
                    if metadata_filter:
                        if not self._matches_filter(data["metadata"], metadata_filter):
                            continue

                    result.content = data["content"]
                    result.metadata = data["metadata"]

                enriched.append(result)

            return enriched

        except Exception as e:
            logger.error("Failed to enrich from ChromaDB: %s", e)
            return results

    async def _chromadb_search(
        self,
        query_embedding: np.ndarray,
        top_k: int,
        collection_name: str,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[SearchResult], SearchMetrics]:
        """Fallback search using ChromaDB."""
        start_time = time.perf_counter()

        try:
            collection = self.chromadb.get_collection(collection_name)

            # Build where clause if filter provided
            where = metadata_filter if metadata_filter else None

            chromadb_results = collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )

            results = []
            if chromadb_results["ids"] and chromadb_results["ids"][0]:
                for i, doc_id in enumerate(chromadb_results["ids"][0]):
                    distance = chromadb_results["distances"][0][i]
                    # Convert L2 distance to similarity
                    score = 1.0 / (1.0 + distance)

                    results.append(
                        SearchResult(
                            doc_id=doc_id,
                            score=score,
                            distance=distance,
                            content=(
                                chromadb_results["documents"][0][i]
                                if chromadb_results["documents"]
                                else None
                            ),
                            metadata=(
                                chromadb_results["metadatas"][0][i]
                                if chromadb_results["metadatas"]
                                else {}
                            ),
                        )
                    )

            query_time = (time.perf_counter() - start_time) * 1000

            metrics = SearchMetrics(
                query_time_ms=query_time,
                total_vectors_searched=collection.count(),
                results_returned=len(results),
                backend_used=SearchBackend.CHROMADB,
                gpu_utilized=False,
                index_type="hnsw",
            )

            return results, metrics

        except Exception as e:
            logger.error("ChromaDB search failed: %s", e)
            return [], SearchMetrics(
                query_time_ms=0,
                total_vectors_searched=0,
                results_returned=0,
                backend_used=SearchBackend.CHROMADB,
                gpu_utilized=False,
                index_type="error",
            )

    def _matches_filter(
        self, metadata: Dict[str, Any], filter_dict: Dict[str, Any]
    ) -> bool:
        """Check if metadata matches filter."""
        for key, value in filter_dict.items():
            if key not in metadata:
                return False
            if metadata[key] != value:
                return False
        return True

    async def sync_from_chromadb(self, collection_name: str = "default") -> int:
        """
        Sync FAISS index from ChromaDB collection.

        Useful for rebuilding GPU index from persistent ChromaDB data.
        """
        if self.chromadb is None:
            logger.warning("ChromaDB not available for sync")
            return 0

        try:
            collection = self.chromadb.get_collection(collection_name)

            # Get all embeddings from ChromaDB
            all_data = collection.get(include=["embeddings"])

            if not all_data["ids"] or not all_data["embeddings"]:
                logger.info("No data in ChromaDB collection to sync")
                return 0

            embeddings = np.array(all_data["embeddings"], dtype=np.float32)
            doc_ids = all_data["ids"]

            # Add to FAISS index
            added = await self.gpu_index.add_vectors(
                embeddings, doc_ids, normalize=True
            )

            logger.info("✅ Synced %s vectors from ChromaDB to FAISS index", added)
            return added

        except Exception as e:
            logger.error("Failed to sync from ChromaDB: %s", e)
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """Get combined statistics."""
        stats = {
            "initialized": self._initialized,
            "faiss_index": self.gpu_index.get_stats(),
            "chromadb_available": self.chromadb is not None,
        }

        if self.chromadb:
            try:
                collections = self.chromadb.list_collections()
                stats["chromadb_collections"] = len(collections)
            except Exception:
                stats["chromadb_collections"] = "error"

        return stats


# Singleton instance
_hybrid_search: Optional[HybridVectorSearch] = None
_hybrid_search_lock = asyncio.Lock()


async def get_hybrid_vector_search(
    chromadb_client: Optional[Any] = None,
    config: Optional[VectorSearchConfig] = None,
) -> HybridVectorSearch:
    """
    Get or create the singleton hybrid vector search instance.

    Args:
        chromadb_client: Optional ChromaDB client (uses existing if not provided)
        config: Optional configuration

    Returns:
        Initialized HybridVectorSearch instance
    """
    global _hybrid_search

    if _hybrid_search is None:
        async with _hybrid_search_lock:
            if _hybrid_search is None:
                _hybrid_search = HybridVectorSearch(
                    chromadb_client=chromadb_client, config=config
                )
                await _hybrid_search.initialize()

    return _hybrid_search


__all__ = [
    "GPUVectorIndex",
    "HybridVectorSearch",
    "VectorSearchConfig",
    "SearchResult",
    "SearchMetrics",
    "IndexType",
    "SearchBackend",
    "get_hybrid_vector_search",
    "FAISS_AVAILABLE",
    "FAISS_GPU_AVAILABLE",
]
