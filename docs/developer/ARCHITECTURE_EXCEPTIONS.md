# Architecture Exceptions

This document records intentional deviations from the standard AutoBot architecture.
Each entry explains what diverges, which canonical module it mirrors (where applicable),
why the exception exists, and how to keep the two in sync.

---

## Windows NPU Worker — Standalone Redis Client

**File:** `autobot-npu-worker/resources/windows-npu-worker/app/utils/redis_client.py`
**Mirrors:** `autobot_shared/redis_client.py`
**Issue:** #5438

**Reason:** The Windows NPU worker is packaged as a self-contained executable via PyInstaller.
It cannot import from `autobot_shared/` at runtime because the shared package is not bundled
with the executable. The standalone redis_client.py replicates the subset of functionality
needed by the worker.

**Sync cadence:** When `autobot_shared/redis_client.py` changes (connection parameters,
retry logic, health-check helpers), manually mirror those changes here. Reference this
document to surface the obligation.

---

## `utils/gpu_vector_search.py` — FAISS-GPU Hybrid Search Client Type

**File:** `autobot-backend/utils/gpu_vector_search.py`
**Issue:** #5800

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

---

## `knowledge/rag_benchmarks.py` — EphemeralClient in Test Fixtures

**File:** `autobot-backend/knowledge/rag_benchmarks.py`

**Pattern bypassed:** Direct `chromadb.EphemeralClient()` instead of `InMemoryClient`
from `knowledge.backends`.

**Status:** Intentional test exception.

**Rationale:** `TestRealKBBenchmarks._ensure_collection()` (line 883) intentionally uses
`chromadb.EphemeralClient()` to exercise ChromaDB's hnswlib HNSW path. `InMemoryClient`
uses a pure-Python brute-force search that cannot replicate the HNSW recall characteristics
this benchmark measures. A swap to `InMemoryClient` would make the test meaningless.

**Grep check:** `grep -rn "EphemeralClient" autobot-backend/` should return only this file.

---

## `api/skills_repos.py` — Broad `except Exception` in `sync_repo`

**File:** `autobot-backend/api/skills_repos.py` (function `sync_repo`, ~line 126)
**Issue:** #5802

**Pattern bypassed:** AutoBot convention is to catch specific exception types rather
than bare `Exception`.

**Reason:** `_sync_packages` performs a composite operation involving network I/O
(fetching from an upstream repository), git operations (clone/pull), and filesystem
writes — each of which raises a distinct exception hierarchy (`aiohttp` exceptions,
`gitpython` exceptions, `OSError` subclasses). Listing every possible type would be
fragile and would not improve error handling since all paths produce the same HTTP 502
response. The broad catch is bounded to this one call site; the exception is logged in
full and re-raised as an `HTTPException` so no information is silently swallowed.

**Grep check:** `grep -n "except Exception" autobot-backend/api/skills_repos.py`

---

## `api/skills_governance.py` — Broad `except Exception` in `detect_gap`

**File:** `autobot-backend/api/skills_governance.py` (function `detect_gap`, ~line 108)
**Issue:** #5802

**Pattern bypassed:** AutoBot convention is to catch specific exception types.

**Reason:** `SkillGenerator.generate()` makes an LLM API call that may fail through
network errors, provider-specific HTTP errors, token-limit errors, JSON decode errors,
or any exception raised inside a dynamically loaded LLM adapter. The failure mode is
non-fatal (the endpoint returns `{"success": false, ...}` rather than raising), so a
broad catch with a warning log is the correct boundary. Narrowing the catch would
either miss real failures or require enumerating every LLM adapter's private exception
classes.

**Grep check:** `grep -n "except Exception" autobot-backend/api/skills_governance.py`

---

## `api/skills_governance.py` — Broad `except Exception` in `promote_skill`

**File:** `autobot-backend/api/skills_governance.py` (function `promote_skill`, ~line 229)
**Issue:** #5802

**Pattern bypassed:** AutoBot convention is to catch specific exception types.

**Reason:** `SkillPromoter.promote()` writes files to the filesystem and may invoke
git operations to register the promoted skill. Failures can originate from
`PermissionError`, `FileExistsError`, `OSError`, `subprocess.CalledProcessError`, or
git library exceptions. All failure paths produce the same HTTP 500 response; the
exception is logged in full and re-raised as `HTTPException` so no information is
silently swallowed. Narrowing the catch would add fragility without improving
observability.

**Grep check:** `grep -n "except Exception" autobot-backend/api/skills_governance.py`

---

## `FlashAttentionV2` / `TestFlashAttentionV2` — Published Algorithm Name

**Pattern bypassed:** `py-duplicate-concept` rule flags `Enhanced*`/`Unified*`/`*V2` class names that shadow a base-name class. `FlashAttentionV2` and `TestFlashAttentionV2` match the `*V2` pattern but are intentional exceptions.

**Reason:** "FlashAttention-2" is a published algorithm (Dao et al., 2023, NeurIPS) with an established canonical name in the ML literature. The `V2` suffix identifies the specific paper/algorithm revision, not a code-organisation era marker. Renaming to `FlashAttention` would lose the version identity and make it impossible to distinguish from the original FlashAttention algorithm.

**Waiver pattern:** Any file defining `FlashAttentionV2` or `TestFlashAttentionV2` should carry an inline suppression on the class line:

```python
class FlashAttentionV2:  # canonical: ignore py-duplicate-concept — published algorithm name FlashAttention-2 (Dao et al. 2023) (#10666)
```

**Grep check:** `git grep -n "FlashAttentionV2"` should return only flash-attention implementation and test files.
