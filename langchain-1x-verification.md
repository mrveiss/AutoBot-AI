# LangChain 1.x Import Compatibility Verification

**Issue:** #1600
**Branch:** issue-1600
**Date:** 2026-03-16
**Scope:** All Python files in `autobot-backend/`, `autobot-shared/`, `autobot-npu-worker/`, `autobot-infrastructure/`

---

## Summary

- **Total LangChain import sites found:** 16 (across 7 files)
- **Imports needing fixes:** 0
- **Deprecated old-style `langchain.*` imports (pre-1.x):** 0
- **All production backend imports are 1.x-compatible:** YES

---

## Version Pins

| Package | Pin (autobot-backend/requirements.txt) | Notes |
|---------|----------------------------------------|-------|
| `langchain` | `>=1.2.0,<2.0.0` | Issue #1572: migrated from 0.3.x |
| `langchain-core` | `>=1.2.11,<2.0.0` | Issue #1572: SSRF CVE fix requires >=1.2.11 |
| `langchain-community` | `>=0.4.0,<0.5.0` | Compatible with langchain 1.x |
| `langchain-ollama` | `>=1.0.0,<2.0.0` | ChatOllama for QA chain |
| `langgraph` | `>=1.1.1,<2.0.0` | StateGraph for chat orchestration |
| `langgraph-checkpoint-redis` | `>=0.4.0,<1.0.0` | Redis checkpointer |

Additional pins in `autobot-infrastructure/shared/config/requirements.txt`:

| Package | Pin | Notes |
|---------|-----|-------|
| `langchain` | `>=1.2.0` | |
| `langchain-community` | `>=0.4.0` | |
| `langchain-experimental` | `>=0.4.0` | |

Additional pins in `autobot-infrastructure/shared/docker/ai-stack/requirements-ai.txt`:

| Package | Pin | Notes |
|---------|-----|-------|
| `langchain` | `>=1.2.0` | |
| `langchain-core` | `>=1.2.11` | |
| `langchain-community` | `>=0.4.0` | |

---

## Import Inventory

### Production Backend (`autobot-backend/`)

| File | Line | Import | Status |
|------|------|--------|--------|
| `chat_workflow/graph.py` | 29 | `from langchain_core.runnables import RunnableConfig` | OK |
| `api/knowledge_mcp.py` | 68 | `from langchain_ollama import ChatOllama` (inside try/ImportError guard) | OK |

### NPU Worker (`autobot-npu-worker/`)

| File | Line | Import | Status |
|------|------|--------|--------|
| `openvino/openvino_validation_test.py` | 334 | `from langchain_community.embeddings.openvino import OpenVINOEmbeddings` (guarded by try/ImportError + pytest.skip) | OK |
| `openvino/openvino_validation_test.py` | 343 | `from langchain_community.document_compressors.openvino_rerank import OpenVINOReranker` (guarded by try/ImportError + pytest.skip) | OK |

### Infrastructure Analysis Scripts (`autobot-infrastructure/shared/scripts/analysis/`)

These are offline analysis/test scripts, not production code. All LangChain imports in this directory are wrapped in `try/except ImportError` guards.

| File | Line | Import | Status |
|------|------|--------|--------|
| `redis_vector_analysis.py` | 141 | `from langchain_ollama import OllamaEmbeddings` (preferred, try block) | OK |
| `redis_vector_analysis.py` | 145 | `from langchain_community.embeddings import OllamaEmbeddings` (fallback, except block) | OK — fallback only |
| `redis_vector_analysis.py` | 266 | `from langchain_redis import RedisVectorStore` (try block) | OK |
| `redis_final_analysis.py` | 386 | `from langchain_community.embeddings import OllamaEmbeddings` (try block) | OK — fallback path |
| `redis_final_analysis.py` | 387 | `from langchain_redis import RedisVectorStore` (try block) | OK |
| `redis_final_analysis.py` | 620 | `from langchain_redis import RedisVectorStore` (try block) | OK |
| `redis_final_analysis.py` | 623 | `from langchain_ollama import OllamaEmbeddings` (preferred, try block) | OK |
| `redis_final_analysis.py` | 627 | `from langchain_community.embeddings import OllamaEmbeddings` (fallback, except block) | OK — fallback only |
| `test_redis_comparison.py` | 129 | `from langchain_redis import RedisVectorStore as LangChainRedisStore` (try block) | OK |
| `test_redis_comparison.py` | 131 | `from langchain_community.vectorstores.redis import Redis as LangChainRedisStore` (fallback) | OK — fallback only |
| `test_redis_comparison.py` | 163 | `from langchain_redis import RedisVectorStore as LangChainRedisStore` (try block) | OK |
| `test_redis_comparison.py` | 198 | `from langchain_community.embeddings import OllamaEmbeddings` | OK — note below |

---

## Analysis

### No deprecated pre-1.x paths found

The migration from 0.3.x to 1.x (#1572) previously removed all usage of:
- `langchain.schema` (now `langchain_core.messages`)
- `langchain.callbacks` (now `langchain_core.callbacks`)
- `langchain.chat_models` (now `langchain_openai` / `langchain_anthropic` / `langchain_ollama`)
- `langchain.llms` (now split into provider packages)
- `langchain.embeddings` (now `langchain_community.embeddings` or `langchain_ollama`)
- `langchain.vectorstores` (now `langchain_community.vectorstores` or `langchain_redis`)

A search across all Python files confirms: **zero files import from bare `langchain.*` submodules**. Every import uses the correct 1.x namespace packages (`langchain_core`, `langchain_community`, `langchain_ollama`, `langchain_redis`).

### `langchain_community.embeddings.OllamaEmbeddings` — soft deprecation note

In LangChain 1.x, `OllamaEmbeddings` and `ChatOllama` from `langchain-community` are soft-deprecated in favour of the standalone `langchain-ollama` package. The preferred 1.x import is:

```python
from langchain_ollama import OllamaEmbeddings   # preferred
from langchain_ollama import ChatOllama          # preferred
```

The codebase already uses the preferred form in two places:
- `redis_vector_analysis.py:141` — tries `langchain_ollama` first, falls back to community
- `redis_final_analysis.py:623` — tries `langchain_ollama` first, falls back to community
- `api/knowledge_mcp.py:68` — uses `langchain_ollama.ChatOllama` directly

The remaining community fallbacks (`redis_final_analysis.py:386`, `test_redis_comparison.py:198`) are in offline analysis scripts with no production impact. They function correctly under `langchain-community>=0.4.0` and will continue to do so within the `<0.5.0` pin.

### `langchain_community.vectorstores.redis.Redis` fallback

`test_redis_comparison.py:131` uses the legacy `langchain_community.vectorstores.redis.Redis` as a fallback when `langchain_redis` is not available. This path is deprecated in 1.x and was replaced by the `langchain-redis` package. Because it is:
1. Only reached when `langchain_redis` import fails
2. In an offline analysis script, not production code
3. Guarded by `try/except ImportError`

No action is required — the preferred `langchain_redis.RedisVectorStore` path runs first.

### `langchain_core.runnables.RunnableConfig` — verified compatible

`RunnableConfig` has been part of `langchain-core` since 0.1.x and remains stable in 1.x. Import confirmed working.

---

## Files With No LangChain Imports (verified)

- `autobot-shared/` — no LangChain imports anywhere
- `autobot-slm-backend/` — no LangChain imports
- `autobot-browser-worker/` — no LangChain imports
- `autobot-tts-worker/` — no LangChain imports

---

## Conclusion

**All LangChain imports in this codebase are compatible with LangChain 1.x.** The migration performed in #1572 fully removed the deprecated `langchain.*` namespace imports. The two production files that use LangChain (`chat_workflow/graph.py` and `api/knowledge_mcp.py`) both use the correct 1.x package namespaces.

No import changes are required to close this issue.
