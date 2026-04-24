# Architecture Exceptions

This file documents intentional deviations from standard AutoBot architecture patterns.
Each exception must state: the file, the pattern bypassed, and the technical rationale.

---

## `utils/gpu_vector_search.py` — FAISS-GPU hybrid search client type

**Pattern bypassed:** Direct use of raw chromadb client methods rather than going
through a `BaseCollection` ABC instance.

**Status:** Partially migrated. The `HybridVectorSearch` constructor and
`get_hybrid_vector_search` factory now accept a `BaseClient` (from
`knowledge.backends`) rather than `Any`. The internal call sites
(`get_or_create_collection`, `get_collection`, `list_collections`) all exist on
`BaseClient`, so any conformant adapter works.

**Why the collection call sites are NOT wrapped in `BaseCollection`:**
`HybridVectorSearch` interleaves FAISS-GPU vector search with ChromaDB document
storage in a single hybrid pipeline. The collection object returned by
`get_or_create_collection` / `get_collection` is used immediately for
`collection.add(...)`, `collection.get(...)`, `collection.query(...)`, and
`collection.count()` — all of which are defined on `BaseCollection`. The code
therefore already benefits from the abstraction at the client level; the collection
objects returned satisfy the `BaseCollection` contract and callers do not reach for
any chromadb-specific attribute.

**GPU-specific operations** (`faiss.StandardGpuResources`, `faiss.index_cpu_to_gpu`,
`faiss.index_gpu_to_cpu`) exist in `GPUVectorIndex` and are entirely independent of
the ChromaDB client. They cannot be expressed through any vector-store ABC; they
require direct FAISS C++ bindings by design.
