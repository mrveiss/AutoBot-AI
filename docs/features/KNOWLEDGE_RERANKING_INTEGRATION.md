# Knowledge Reranking Integration - Implementation Guide

**Status:** ✅ Production Ready
**Date Completed:** 2025-01-08
**Version:** 1.0.0

---

## Overview

AutoBot now features a comprehensive knowledge reranking system powered by neural cross-encoder models. This implementation provides state-of-the-art document retrieval with improved relevance scoring beyond traditional vector similarity.

### Key Features

- 🧠 **Neural Reranking**: Cross-encoder models trained on MS MARCO dataset
- 🔄 **Hybrid Search**: Combines semantic (70%) + keyword (30%) scoring
- ⚙️ **Configurable**: All parameters externalized to YAML config
- 🚀 **High Performance**: LRU caching, timeout protection, graceful degradation
- 🔌 **Reusable**: Service layer architecture for maximum code reuse
- ✅ **Backward Compatible**: Existing endpoints work unchanged

---

## Architecture

### Three-Layer Service Architecture

```
┌─────────────────────────────────────┐
│     API Endpoints Layer             │
│  /search, /advanced_search, /rerank │
└──────────────┬──────────────────────┘
               │ Depends on
               ↓
┌─────────────────────────────────────┐
│         RAGService                  │
│  • Caching (5min TTL)               │
│  • Timeout protection (30s)         │
│  • Graceful degradation             │
│  • FastAPI dependency injection     │
└──────────────┬──────────────────────┘
               │ Uses
               ↓
┌─────────────────────────────────────┐
│    AdvancedRAGOptimizer             │
│  • Hybrid search                    │
│  • Query expansion                  │
│  • Result diversification           │
│  • Cross-encoder reranking          │
└──────────────┬──────────────────────┘
               │ Accesses via
               ↓
┌─────────────────────────────────────┐
│    KnowledgeBaseAdapter             │
│  • Unified KB V1/V2 interface       │
│  • Result normalization             │
└─────────────────────────────────────┘
```

### Components

#### 1. KnowledgeBaseAdapter
**File:** `backend/services/knowledge_base_adapter.py`

**Purpose:** Unified interface resolving API differences between KnowledgeBase V1 and V2.

**Key Methods:**
- `search(query, top_k, mode)` - Unified search interface
- `get_all_facts()` - Retrieve all facts
- `get_stats()` - Knowledge base statistics
- `_normalize_results()` - Consistent result format

**Pattern:** Adapter Pattern

#### 2. RAGConfig
**File:** `backend/services/rag_config.py`

**Purpose:** Externalized configuration management with validation.

**Key Features:**
- Loads from `config/complete.yaml` under `knowledge.rag`
- Validates weight normalization (must sum to 1.0)
- Singleton pattern for global instance
- Runtime updates via `update_rag_config()`

**Configuration Parameters:**
```python
hybrid_weight_semantic: 0.7
hybrid_weight_keyword: 0.3
enable_reranking: true
reranking_model: "cross-encoder/ms-marco-MiniLM-L-6-v2"
cache_ttl_seconds: 300
timeout_seconds: 30.0
```

#### 3. RAGService
**File:** `backend/services/rag_service.py`

**Purpose:** Reusable wrapper providing clean API for RAG operations.

**Key Methods:**
- `advanced_search(query, max_results, enable_reranking, timeout)`
- `get_optimized_context(query, max_context_length)`
- `rerank_results(query, results)`

**Features:**
- Lazy initialization (creates optimizer on first use)
- LRU caching (max 100 entries, 5min TTL)
- Timeout protection (30s default)
- Graceful degradation to basic search
- FastAPI dependency injection ready

#### 4. Cross-Encoder Reranking
**File:** `src/advanced_rag_optimizer.py` (lines 405-498)

**Purpose:** Neural reranking using transformer-based cross-encoders.

**Model:** `cross-encoder/ms-marco-MiniLM-L-6-v2`
- Trained on Microsoft MARCO passage ranking dataset
- Optimized for query-document relevance scoring
- 6-layer MiniLM transformer (fast inference)

**Workflow:**
1. Lazy load model on first use
2. Prepare query-document pairs
3. Run cross-encoder prediction (in thread pool)
4. Combine scores: CE (80%) + hybrid (20%)
5. Sort by rerank score
6. Update relevance ranks

**Fallback:** Term-based reranking if model unavailable

---

## API Endpoints

### Enhanced Existing Endpoint

#### POST /api/knowledge_base/search
Enhanced with optional reranking parameter.

**Request:**
```json
{
  "query": "how to configure redis",
  "limit": 10,
  "enable_reranking": true
}
```

**Response:**
```json
{
  "results": [...],
  "total_results": 10,
  "query": "how to configure redis",
  "reranking_applied": true,
  "reranking_method": "cross-encoder"
}
```

### New Dedicated Endpoints

All endpoints prefixed with `/api/knowledge_base/rag/`

#### 1. POST /advanced_search
Full-featured advanced RAG search with all optimizations.

**Request:**
```json
{
  "query": "redis configuration best practices",
  "max_results": 10,
  "enable_reranking": true,
  "return_context": false,
  "timeout": 30.0
}
```

**Response:**
```json
{
  "results": [
    {
      "content": "...",
      "metadata": {...},
      "source_path": "docs/redis.md",
      "semantic_score": 0.85,
      "keyword_score": 0.60,
      "hybrid_score": 0.76,
      "rerank_score": 0.92,
      "relevance_rank": 1
    }
  ],
  "total_results": 10,
  "query": "redis configuration best practices",
  "metrics": {
    "query_processing_time": 0.05,
    "retrieval_time": 0.20,
    "reranking_time": 0.15,
    "total_time": 0.42,
    "documents_considered": 20,
    "final_results_count": 10,
    "hybrid_search_enabled": true
  },
  "reranking_enabled": true
}
```

#### 2. POST /rerank_results
Post-process existing search results with reranking.

**Request:**
```json
{
  "query": "redis setup",
  "results": [
    {"content": "...", "metadata": {}, "score": 0.7},
    {"content": "...", "metadata": {}, "score": 0.6}
  ]
}
```

**Response:**
```json
{
  "reranked_results": [
    {
      "content": "...",
      "rerank_score": 0.85,
      "original_rank": 2
    },
    {
      "content": "...",
      "rerank_score": 0.72,
      "original_rank": 1
    }
  ],
  "original_count": 2,
  "query": "redis setup",
  "reranking_applied": true
}
```

#### 3. GET /config
View current RAG configuration.

**Response:**
```json
{
  "config": {
    "hybrid_weight_semantic": 0.7,
    "hybrid_weight_keyword": 0.3,
    "enable_reranking": true,
    "reranking_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "cache_ttl_seconds": 300,
    "timeout_seconds": 30.0,
    "enable_advanced_rag": true,
    "fallback_to_basic_search": true
  },
  "source": "config/complete.yaml"
}
```

#### 4. PUT /config
Update RAG configuration at runtime.

**Request:**
```json
{
  "hybrid_weight_semantic": 0.8,
  "hybrid_weight_keyword": 0.2,
  "enable_reranking": true
}
```

**Response:**
```json
{
  "message": "RAG configuration updated successfully",
  "updated_fields": ["hybrid_weight_semantic", "hybrid_weight_keyword"],
  "config": {...}
}
```

#### 5. GET /stats
RAG service statistics.

**Response:**
```json
{
  "stats": {
    "initialized": true,
    "kb_implementation": "KnowledgeBase",
    "cache_entries": 15,
    "config": {...}
  },
  "service_available": true
}
```

---

## Configuration

### YAML Configuration
**Location:** `config/complete.yaml` (lines 210-237)

```yaml
knowledge:
  rag:
    # Hybrid search weights (must sum to 1.0)
    hybrid_weight_semantic: 0.7
    hybrid_weight_keyword: 0.3

    # Search parameters
    max_results_per_stage: 20
    diversity_threshold: 0.85
    default_max_results: 5

    # Context optimization
    default_context_length: 2000
    max_context_length: 5000

    # Reranking configuration
    enable_reranking: true
    reranking_model: "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Performance and caching
    cache_ttl_seconds: 300
    timeout_seconds: 30.0

    # Feature flags
    enable_advanced_rag: true
    fallback_to_basic_search: true
```

### Configuration Validation

The `RAGConfig` class automatically validates:
- Weights sum to 1.0 (normalized if needed)
- Weights are in range [0, 1]
- Thresholds are in range [0, 1]
- Positive integers for counts and timeouts

---

## Performance Characteristics

### Caching Strategy
- **Type:** LRU Cache
- **TTL:** 300 seconds (5 minutes)
- **Max Entries:** 100
- **Eviction:** Removes oldest 20% when full

### Timeout Protection
- **Default Timeout:** 30 seconds
- **Configurable:** Via `timeout_seconds` parameter
- **Fallback:** Graceful degradation to basic search

### Model Loading
- **Strategy:** Lazy loading (first use only)
- **Location:** In-memory (singleton)
- **Execution:** Thread pool (non-blocking async)

### Performance Metrics
Typical advanced search performance:
- Query processing: ~50ms
- Initial retrieval: ~200ms
- Reranking (10 docs): ~150ms
- **Total:** ~400ms

---

## Testing

### Test Suite
**Location:** `tests/unit/test_rag_integration.py`

**Test Coverage:**
- ✅ 6 tests for KnowledgeBaseAdapter
- ✅ 6 tests for RAGConfig
- ✅ 4 tests for RAGService
- ✅ 2 tests for Cross-Encoder
- ✅ 5 API endpoint tests (structure)

**Total:** 23 test cases

### Running Tests

```bash
# Run all RAG integration tests
pytest tests/unit/test_rag_integration.py -v

# Run specific test class
pytest tests/unit/test_rag_integration.py::TestRAGService -v

# Run with coverage
pytest tests/unit/test_rag_integration.py --cov=backend.services --cov=src.advanced_rag_optimizer
```

---

## Usage Examples

### Python API Usage

```python
from backend.services.rag_service import RAGService
from backend.knowledge_factory import get_or_create_knowledge_base

# Get knowledge base
kb = await get_or_create_knowledge_base(app)

# Create RAG service
rag_service = RAGService(kb)
await rag_service.initialize()

# Perform advanced search
results, metrics = await rag_service.advanced_search(
    query="how to configure redis",
    max_results=10,
    enable_reranking=True
)

# Process results
for result in results:
    print(f"Score: {result.rerank_score:.3f}")
    print(f"Content: {result.content[:100]}...")
    print(f"Source: {result.source_path}")
```

### FastAPI Dependency Injection

```python
from fastapi import Depends
from backend.services.rag_service import RAGService

async def get_rag_service_dep(request: Request) -> RAGService:
    kb = await get_or_create_knowledge_base(request.app)
    service = RAGService(kb)
    await service.initialize()
    return service

@router.post("/custom_search")
async def custom_search(
    query: str,
    rag_service: RAGService = Depends(get_rag_service_dep)
):
    results, metrics = await rag_service.advanced_search(query)
    return {"results": results, "metrics": metrics}
```

---

## Troubleshooting

### Common Issues

#### 1. Cross-Encoder Model Not Loading

**Symptom:** Fallback to term-based reranking

**Solution:**
```bash
# Verify sentence-transformers installed
pip list | grep sentence-transformers

# Reinstall if needed
pip install sentence-transformers>=2.2.0
```

#### 2. Timeout Errors

**Symptom:** `asyncio.TimeoutError` after 30 seconds

**Solution:** Increase timeout in config
```yaml
knowledge:
  rag:
    timeout_seconds: 60.0  # Increase to 60s
```

#### 3. Memory Issues with Cache

**Symptom:** High memory usage

**Solution:** Reduce cache TTL or size
```yaml
knowledge:
  rag:
    cache_ttl_seconds: 120  # 2 minutes instead of 5
```

#### 4. Reranking Not Applied

**Symptom:** `reranking_applied: false` in response

**Check:**
1. `enable_reranking` parameter set to `true`
2. Configuration: `knowledge.rag.enable_reranking: true`
3. Check logs for initialization errors

---

## Migration Guide

### From Basic Search to Reranked Search

**Before:**
```python
results = await kb.search(query="redis", top_k=10)
```

**After (Option 1 - Use existing endpoint):**
```python
# Via API
response = requests.post(
    "http://localhost:8001/api/knowledge_base/search",
    json={"query": "redis", "limit": 10, "enable_reranking": True}
)
```

**After (Option 2 - Use dedicated endpoint):**
```python
# Via advanced RAG endpoint
response = requests.post(
    "http://localhost:8001/api/knowledge_base/rag/advanced_search",
    json={"query": "redis", "max_results": 10, "enable_reranking": True}
)
```

**After (Option 3 - Use service directly):**
```python
from backend.services.rag_service import RAGService

service = RAGService(kb)
await service.initialize()
results, metrics = await service.advanced_search("redis", max_results=10)
```

---

## Best Practices

### When to Use Reranking

✅ **Use reranking when:**
- Search queries are complex or ambiguous
- Precision is more important than speed
- You need the top 5-10 most relevant results
- User queries contain natural language

❌ **Skip reranking when:**
- Simple exact-match queries
- Speed is critical (<100ms required)
- Large result sets (>50 documents)
- Keyword-only searches

### Performance Optimization

1. **Enable caching** for repeated queries
2. **Limit max_results** to 10-20 documents
3. **Use diversity_threshold** to remove duplicates
4. **Set appropriate timeouts** based on use case
5. **Monitor metrics** via `/rag/stats` endpoint

### Configuration Tuning

**For precision-focused retrieval:**
```yaml
hybrid_weight_semantic: 0.8
hybrid_weight_keyword: 0.2
enable_reranking: true
```

**For recall-focused retrieval:**
```yaml
hybrid_weight_semantic: 0.6
hybrid_weight_keyword: 0.4
enable_reranking: false
```

---

## Future Enhancements

### Planned Features

- 🔄 Multi-stage reranking with different models
- 📊 A/B testing framework for reranking strategies
- 🎯 Query-specific model selection
- 📈 Performance monitoring dashboard
- 🔍 Explainability for rerank scores
- 🌐 Multi-language cross-encoder support

### Experimental Features

- BM25 integration for keyword scoring
- Learned sparse retrieval (SPLADE)
- ColBERT-style late interaction
- Query expansion with LLMs

---

## References

### Model Information
- **Cross-Encoder Model:** [ms-marco-MiniLM-L-6-v2](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L-6-v2)
- **Training Dataset:** [MS MARCO Passage Ranking](https://microsoft.github.io/msmarco/)
- **Library:** [sentence-transformers](https://www.sbert.net/)

### Related Documentation
- [AutoBot API Documentation](../api/COMPREHENSIVE_API_DOCUMENTATION.md)
- [Knowledge Base Architecture](../architecture/KNOWLEDGE_BASE_ARCHITECTURE.md)
- [Configuration Guide](../../config/README.md)

---

**Implementation Date:** 2025-01-08
**Implemented By:** Claude Code
**Status:** ✅ Production Ready
