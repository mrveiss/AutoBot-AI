# NPU-Accelerated Semantic Code Search Design

**Issue:** #207
**Date:** 2026-02-04
**Author:** mrveiss
**Status:** Design Approved

---

## Summary

Implement proper embedding-based semantic code search with NPU acceleration, replacing the current word-matching fallback in `npu_code_search_agent.py`.

## Background

From Issue #201 analysis:
- Location: `autobot-user-backend/agents/npu_code_search_agent.py`
- Current behavior: Falls back to word-matching fuzzy search when semantic search unavailable
- Root cause: Code indexing stores metadata in Redis but doesn't generate embeddings
- Impact: Reduced search quality and accuracy for code discovery

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Embedding model | CodeBERT (microsoft/codebert-base) | Code-specific transformer understands syntax, semantics, and NL queries |
| Vector storage | ChromaDB collection | Consistent with existing multi-modal architecture |
| Granularity | Function/class level | Good precision/context balance, matches existing extraction |
| NPU acceleration | OpenVINO IR conversion | Leverage existing NPU infrastructure |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Code Indexing Pipeline                        │
├─────────────────────────────────────────────────────────────────┤
│  1. File Discovery (existing)                                    │
│  2. Element Extraction (existing - functions, classes)          │
│  3. CodeBERT Embedding Generation (NEW - NPU accelerated)       │
│  4. ChromaDB Storage (NEW - 'autobot_code_embeddings')          │
│  5. Redis Metadata (existing - enhanced with embedding refs)    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    Semantic Code Search                          │
├─────────────────────────────────────────────────────────────────┤
│  Query → CodeBERT Embedding (NPU)                               │
│       → ChromaDB Vector Search                                   │
│       → Optional: Hybrid boost with keyword search              │
│       → Ranked Results (file_path, line_number, context)        │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Plan

### Phase 1: CodeBERT Integration

**New File:** `src/code_embedding_generator.py`

```python
# Responsibilities:
# - Load CodeBERT model (HuggingFace → OpenVINO IR)
# - NPU/GPU/CPU device selection via existing WorkerNode
# - Batch embedding generation for efficiency
# - Integration with existing EmbeddingCache (Issue #65)

class CodeEmbeddingGenerator:
    """Generate code embeddings using CodeBERT with NPU acceleration."""

    def __init__(self):
        self.model_name = "microsoft/codebert-base"
        self.embedding_dim = 768
        self.openvino_model = None
        self.tokenizer = None
        self.npu_available = False

    async def initialize(self):
        """Load model and convert to OpenVINO IR if NPU available."""

    async def generate_embedding(self, code: str, language: str) -> np.ndarray:
        """Generate embedding for code snippet."""

    async def batch_generate(self, code_snippets: List[str]) -> List[np.ndarray]:
        """Batch embedding generation for efficiency."""
```

### Phase 2: ChromaDB Code Collection

**Modify:** `src/npu_semantic_search.py`

Add code collection to existing multi-modal architecture:

```python
# In NPUSemanticSearch.__init__()
self.collection_names = {
    "text": "autobot_text_embeddings",
    "image": "autobot_image_embeddings",
    "audio": "autobot_audio_embeddings",
    "multimodal": "autobot_multimodal_fused",
    "code": "autobot_code_embeddings",  # NEW
}

# New method
async def store_code_embedding(
    self,
    code_content: str,
    file_path: str,
    line_number: int,
    element_type: str,  # 'function', 'class'
    language: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Store code element embedding in ChromaDB."""
```

**Collection Schema:**
```
autobot_code_embeddings:
  - id: unique element identifier
  - embedding: 768-dim CodeBERT vector
  - document: code content (for retrieval)
  - metadata:
      - file_path: str
      - line_number: int
      - element_type: 'function' | 'class' | 'module'
      - element_name: str
      - language: str
      - content_hash: str (for change detection)
      - indexed_at: timestamp
```

### Phase 3: Enhanced Code Indexing

**Modify:** `autobot-user-backend/agents/npu_code_search_agent.py`

Enhance `_index_file()` to generate and store embeddings:

```python
async def _index_file(self, file_path: str, relative_path: str):
    """Index a single file with embeddings."""
    # Existing: read file, detect language, extract elements

    # NEW: Generate embeddings for each element
    embedding_generator = await get_code_embedding_generator()

    for element_type in ["functions", "classes"]:
        for element in elements[element_type]:
            # Get full element code with context
            element_code = self._extract_element_code(
                content, element["line_number"], element_type
            )

            # Generate embedding
            embedding = await embedding_generator.generate_embedding(
                element_code, language
            )

            # Store in ChromaDB
            embedding_id = await self.npu_search_engine.store_code_embedding(
                code_content=element_code,
                file_path=relative_path,
                line_number=element["line_number"],
                element_type=element_type,
                language=language,
                metadata={"element_name": element["name"]}
            )

            # Update Redis with embedding reference
            element["embedding_id"] = embedding_id
```

### Phase 4: Semantic Search Implementation

**Replace:** `_fallback_semantic_search()` with proper semantic search:

```python
async def _search_semantic(
    self, query: str, language: Optional[str], max_results: int
) -> List[CodeSearchResult]:
    """Perform true semantic search using code embeddings."""
    try:
        # Ensure search engine initialized
        await self._ensure_search_engine_initialized()

        # Generate query embedding using CodeBERT
        embedding_generator = await get_code_embedding_generator()
        query_embedding = await embedding_generator.generate_embedding(
            query, language or "python"
        )

        # Search ChromaDB code collection
        results = await self._search_code_collection(
            query_embedding, language, max_results
        )

        # Optional: Hybrid boost with keyword matches
        if self.enable_hybrid_search:
            keyword_results = await self._search_keywords(query, language, max_results)
            results = self._merge_hybrid_results(results, keyword_results)

        return results

    except Exception as e:
        self.logger.error("Semantic code search failed: %s", e)
        # Final fallback to word-matching (deprecated path)
        return await self._word_matching_fallback(query, language, max_results)


async def _search_code_collection(
    self,
    query_embedding: np.ndarray,
    language: Optional[str],
    max_results: int,
) -> List[CodeSearchResult]:
    """Search ChromaDB code embeddings collection."""
    collection = self.npu_search_engine.collections.get("code")
    if not collection:
        raise ValueError("Code collection not initialized")

    # Build filter for language if specified
    where_filter = {"language": language} if language else None

    # Query ChromaDB
    results = collection.query(
        query_embeddings=[query_embedding.tolist()],
        n_results=max_results,
        where=where_filter,
        include=["metadatas", "documents", "distances"],
    )

    # Convert to CodeSearchResult
    return self._convert_chroma_to_code_results(results)
```

### Phase 5: Hybrid Search (Optional Enhancement)

```python
async def _merge_hybrid_results(
    self,
    semantic_results: List[CodeSearchResult],
    keyword_results: List[CodeSearchResult],
    semantic_weight: float = 0.7,
) -> List[CodeSearchResult]:
    """Merge semantic and keyword results with weighted scoring."""
    # Create lookup by (file_path, line_number)
    merged = {}

    for result in semantic_results:
        key = (result.file_path, result.line_number)
        merged[key] = result
        result.confidence *= semantic_weight

    for result in keyword_results:
        key = (result.file_path, result.line_number)
        if key in merged:
            # Boost existing semantic match
            merged[key].confidence += result.confidence * (1 - semantic_weight)
        else:
            result.confidence *= (1 - semantic_weight)
            merged[key] = result

    # Sort by combined confidence
    results = sorted(merged.values(), key=lambda x: x.confidence, reverse=True)
    return results
```

### Phase 6: Incremental Updates

```python
async def _should_reindex_element(
    self,
    element: Dict[str, Any],
    stored_hash: Optional[str],
) -> bool:
    """Check if element needs re-indexing based on content hash."""
    current_hash = hashlib.sha256(
        element["context"].encode()
    ).hexdigest()
    return stored_hash != current_hash
```

## Files Summary

| File | Action | Lines Est. |
|------|--------|------------|
| `src/code_embedding_generator.py` | CREATE | ~200 |
| `autobot-user-backend/agents/npu_code_search_agent.py` | MODIFY | ~150 |
| `src/npu_semantic_search.py` | MODIFY | ~80 |
| `tests/test_code_semantic_search.py` | CREATE | ~150 |

## Acceptance Criteria

- [ ] CodeBERT model loads and generates embeddings
- [ ] Code embeddings stored in ChromaDB collection
- [ ] NPU utilized for embedding generation when available
- [ ] Semantic code search returns relevant results
- [ ] Performance improvement over word-matching fallback
- [ ] Hybrid search option combining semantic + keyword
- [ ] Incremental indexing detects code changes
- [ ] Unit tests pass for new functionality

## Dependencies

- `transformers` (already installed)
- `openvino` (already installed)
- `chromadb` (already installed)
- Existing: `EmbeddingCache`, `WorkerNode`, `NPUSemanticSearch`

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| CodeBERT model size (440MB) | Lazy loading, model caching |
| NPU not available | Graceful fallback to GPU/CPU |
| Large codebase indexing time | Batch processing, incremental updates |
| ChromaDB collection grows large | Content hash deduplication, TTL cleanup |

## Testing Strategy

1. **Unit tests:** Embedding generation, ChromaDB storage
2. **Integration tests:** Full index → search pipeline
3. **Performance tests:** Compare semantic vs word-matching accuracy
4. **NPU tests:** Verify NPU acceleration when available

---

## Implementation Order

1. Create `code_embedding_generator.py` with CodeBERT loading
2. Add code collection to `npu_semantic_search.py`
3. Enhance `_index_file()` to generate embeddings
4. Implement `_search_code_collection()` for semantic search
5. Add hybrid search option
6. Create tests
7. Performance benchmarking
