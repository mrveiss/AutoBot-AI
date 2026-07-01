# RAG Workflow with PDF Documents in AutoBot


## Quick Answer

**How do you implement a RAG workflow that fetches context from a PDF repository before generating a response?**

Upload a PDF to the knowledge base, wait for vectorization, then query with
RAG-enhanced search. The LLM receives the relevant PDF chunks as context and
returns a response with citations. Here is the complete end-to-end flow:

```python
#!/usr/bin/env python3
"""RAG with PDF: upload, vectorize, query with context-augmented LLM response."""

import asyncio

import aiohttp

from autobot_shared.ssot_config import config

BACKEND = f"https://{config.vm.main}:{config.port.backend}"


async def rag_pdf_workflow(token: str, pdf_path: str, query: str):
    """Upload a PDF, wait for indexing, and query with RAG.

    Args:
        token: Admin JWT token.
        pdf_path: Local path to the PDF file.
        query: Question to ask against the PDF content.
    """
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession() as session:
        # Step 1: Upload the PDF to the knowledge base
        form = aiohttp.FormData()
        form.add_field("file", open(pdf_path, "rb"), filename=pdf_path.split("/")[-1])
        form.add_field("category", "documentation")

        resp = await session.post(
            f"{BACKEND}/api/knowledge_base/upload",
            data=form,
            headers=headers,
            ssl=False,
        )
        upload_result = await resp.json()
        fact_id = upload_result.get("fact_id")
        print(f"Uploaded PDF: fact_id={fact_id}")

        # Step 2: Wait for vectorization to complete
        for attempt in range(30):
            status_resp = await session.get(
                f"{BACKEND}/api/knowledge_base/vectorization/status/{fact_id}",
                headers=headers,
                ssl=False,
            )
            status = await status_resp.json()
            if status.get("status") == "completed":
                print(f"Vectorization complete: {status.get('chunks', 0)} chunks")
                break
            await asyncio.sleep(2)

        # Step 3: Query with RAG-enhanced search (hybrid mode)
        search_resp = await session.post(
            f"{BACKEND}/api/knowledge_base/search",
            json={
                "query": query,
                "search_type": "hybrid",
                "limit": 5,
                "include_context": True,
            },
            headers=headers,
            ssl=False,
        )
        results = await search_resp.json()
        print(f"Found {len(results.get('results', []))} relevant chunks")

        # Step 4: Send query to chat with RAG context (automatic KB integration)
        chat_resp = await session.post(
            f"{BACKEND}/api/chat/message",
            json={
                "message": query,
                "session_id": "rag-test",
                "use_knowledge": True,
            },
            headers=headers,
            ssl=False,
        )
        chat_result = await chat_resp.json()
        print(f"LLM Response: {chat_result.get('response', '')[:200]}")
        print(f"Citations: {chat_result.get('citations', [])}")

        return chat_result


if __name__ == "__main__":
    import sys
    auth_token = sys.argv[1] if len(sys.argv) > 1 else "YOUR_JWT_TOKEN"
    asyncio.run(rag_pdf_workflow(
        auth_token,
        pdf_path="/opt/autobot/data/docs/architecture.pdf",
        query="What is the deployment architecture?",
    ))
```

**curl quick check:**

```bash
# Upload PDF
curl -sk -X POST "$BACKEND/api/knowledge_base/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/document.pdf" -F "category=documentation"

# Search with RAG
curl -sk -X POST "$BACKEND/api/knowledge_base/search" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "deployment architecture", "search_type": "hybrid", "limit": 5}'
```

For hybrid scoring, graph RAG, and the full vectorization pipeline, see
[Section 5](#5-npu-search-with-hybrid-scoring) and [Section 7](#7-graph-rag-advanced).

---


> **Benchmark target:** Implement a Retrieval-Augmented Generation (RAG) workflow that
> fetches context from a PDF repository before generating a response.

This guide covers the complete RAG pipeline in AutoBot -- from uploading PDF documents
into the knowledge base, through vectorization and indexing, to querying with context-augmented
LLM responses. Every code example is complete, runnable, and references the actual
AutoBot API endpoints and backend modules.

---

## Table of Contents

1. [RAG Architecture Overview](#1-rag-architecture-overview)
2. [Ingesting PDF Documents](#2-ingesting-pdf-documents)
3. [Knowledge API Endpoint Reference](#3-knowledge-api-endpoint-reference)
4. [RAG-Enhanced Chat Flow](#4-rag-enhanced-chat-flow)
5. [NPU Search with Hybrid Scoring](#5-npu-search-with-hybrid-scoring)
6. [Document Vectorization Pipeline](#6-document-vectorization-pipeline)
7. [Graph RAG (Advanced)](#7-graph-rag-advanced)
8. [Natural Language Search](#8-natural-language-search)
9. [Complete End-to-End Example](#9-complete-end-to-end-example)
10. [Configuration Reference](#10-configuration-reference)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. RAG Architecture Overview

AutoBot implements a multi-stage RAG architecture composed of specialized services,
a modular knowledge base built on 14 mixins, and multiple retrieval strategies ranging
from basic vector search through hybrid scoring to graph-aware traversal.

### High-Level Data Flow

```
PDF Upload             Retrieval Pipeline
   |                        |
   v                        v
[api/knowledge.py]     [User Query]
   |                        |
   v                        v
Text Extraction        Embedding Generation
(pypdf)                (NPU Worker / Ollama)
   |                        |
   v                        v
Chunking               Vector Search (ChromaDB)
(recursive split)      + Keyword Search (Redis)
   |                        |
   v                        v
Embedding              Reciprocal Rank Fusion
(NPU/Ollama)           (hybrid scoring)
   |                        |
   v                        v
ChromaDB Storage       Cross-Encoder Reranking
+ Redis Metadata       (ms-marco-MiniLM-L-6-v2)
                            |
                            v
                       Context Assembly
                            |
                            v
                       LLM Augmentation
                       (Ollama / AI Stack)
                            |
                            v
                       Response + Citations
```

### Core Components

| Component | Module Path | Responsibility |
|-----------|-------------|----------------|
| **Knowledge Base** | `knowledge/__init__.py` | Composed from 14 mixins: Core, Stats, Index, Search, Facts, Documents, Tags, Categories, Collections, Suggestions, Metadata, Versioning, BulkOps, Relations |
| **Knowledge API** | `api/knowledge.py` | REST endpoints for CRUD, upload, categories; prefix `/api/knowledge_base` |
| **Knowledge Search** | `api/knowledge_search.py` | Consolidated search endpoint (`POST /search`) with semantic, keyword, hybrid, and RAG modes |
| **RAG Service** | `services/rag_service.py` | `RAGService` class -- lazy-initialized singleton wrapping `AdvancedRAGOptimizer` with timeout, caching, and fallback |
| **RAG Agent** | `agents/rag_agent.py` | `RAGAgent` (StandardizedAgent) for document synthesis, query reformulation, and context ranking |
| **Advanced RAG Optimizer** | `advanced_rag_optimizer.py` | Hybrid search, multi-stage reranking, query expansion, result diversification, GPU-accelerated embeddings |
| **Graph RAG Service** | `services/graph_rag_service.py` | `GraphRAGService` composing `RAGService` + `AutoBotMemoryGraph` for relationship-aware retrieval |
| **Graph RAG API** | `api/graph_rag.py` | REST endpoints at `/api/graph-rag` for graph-aware search, health, metrics |
| **NPU Search** | `api/search.py` | NPU-accelerated semantic search at `/api/npu-search` |
| **Natural Language Search** | `api/natural_language_search.py` | Intent-classified code search at `/api/natural-language-search/nl-search` |
| **RAG Config** | `services/rag_config.py` | `RAGConfig` dataclass loaded from `config/complete.yaml` under `knowledge.rag` |
| **Knowledge Factory** | `knowledge_factory.py` | Singleton factory breaking circular imports between `api/knowledge.py` and `app_factory.py` |
| **Chat Integration** | `api/chat.py` | `_enhance_with_knowledge_base()` injects KB search results into LLM context |

### Storage Layer

| Store | Location | Purpose |
|-------|----------|---------|
| **ChromaDB** | AI Stack VM (<aiml-ip>) via `data/chromadb` path | Vector embeddings with HNSW index (cosine, construction_ef=300, search_ef=100, M=32) |
| **Redis DB 1** | Redis VM (<database-ip>) | Document metadata, fact storage (`knowledge_base:facts` hash), category caches, vectorization status |
| **NPU Worker** | NPU VM (<npu-ip>) | Hardware-accelerated embedding generation with cached availability checks (30s TTL) |

### Embedding Pipeline

AutoBot uses a tiered embedding strategy with automatic fallback:

1. **NPU Worker** (preferred) -- Intel NPU hardware acceleration via `services/npu_client.py`
2. **Ollama** (fallback) -- Local model via `OllamaEmbedding` (LlamaIndex integration)
3. **Sentence-Transformers** (secondary fallback) -- CPU-based embedding

The function `_generate_embedding_with_npu_fallback()` in `knowledge/facts.py` implements
this cascade with bounded concurrency (`_FALLBACK_MAX_CONCURRENT = 5`) to prevent
overwhelming Ollama during NPU outages.

---

## 2. Ingesting PDF Documents

AutoBot accepts PDF uploads through the `/api/knowledge_base/upload` endpoint. The backend
extracts text using `pypdf`, stores the content as a fact in Redis DB 1, and triggers
background vectorization into ChromaDB.

### Supported File Types

AutoBot accepts these file extensions (enforced by `_validate_file_upload()`):

| Extension | Extraction Method |
|-----------|------------------|
| `.pdf` | `pypdf.PdfReader` -- page-by-page text extraction |
| `.docx` | `python-docx` -- paragraph text extraction |
| `.txt`, `.md`, `.csv` | Direct UTF-8 decode |
| `.html` | Safe HTML parser (`_HtmlTextExtractor`) stripping script/style tags |
| `.json` | JSON parse and pretty-print |

Maximum file size: **10 MB** (enforced server-side).

### Upload a Single PDF

```python
#!/usr/bin/env python3
"""Upload a single PDF to the AutoBot knowledge base."""

import asyncio
import ssl

import aiohttp

from autobot_shared.ssot_config import config

BACKEND_URL = f"https://{config.vm.main}:{config.port.backend}"


async def upload_pdf(pdf_path: str, category: str = "documentation") -> dict:
    """
    Upload a PDF document to the knowledge base for RAG.

    Args:
        pdf_path: Absolute path to the PDF file.
        category: Knowledge base category for organization.

    Returns:
        API response dict with document_id, title, word_count.

    Raises:
        aiohttp.ClientResponseError: On non-2xx HTTP status.
    """
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    connector = aiohttp.TCPConnector(ssl=ssl_ctx)

    async with aiohttp.ClientSession(connector=connector) as session:
        with open(pdf_path, "rb") as f:
            data = aiohttp.FormData()
            data.add_field(
                "file",
                f,
                filename=pdf_path.rsplit("/", 1)[-1],
                content_type="application/pdf",
            )
            data.add_field("category", category)
            data.add_field("title", "")  # Auto-detected from filename

            response = await session.post(
                f"{BACKEND_URL}/api/knowledge_base/upload",
                data=data,
                headers={"Authorization": "Bearer <your-token>"},
            )
            response.raise_for_status()
            result = await response.json()

    return result


if __name__ == "__main__":
    result = asyncio.run(upload_pdf("/opt/autobot/documents/redis-guide.pdf"))
    print(f"Uploaded: document_id={result['document_id']}, "
          f"words={result['word_count']}")
```

### Upload a Directory of PDFs

```python
#!/usr/bin/env python3
"""Batch-upload all PDFs from a directory into the AutoBot knowledge base."""

import asyncio
import glob
import logging
import os
import ssl

import aiohttp

from autobot_shared.ssot_config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKEND_URL = f"https://{config.vm.main}:{config.port.backend}"


async def upload_pdf_repository(
    pdf_directory: str,
    category: str = "pdf_repository",
    auth_token: str = "",
) -> list:
    """
    Upload every PDF in a directory to the knowledge base.

    Args:
        pdf_directory: Directory containing PDF files.
        category: Category to assign to all uploaded documents.
        auth_token: Bearer token for API authentication.

    Returns:
        List of API response dicts, one per uploaded file.
    """
    pdf_files = sorted(glob.glob(os.path.join(pdf_directory, "*.pdf")))
    if not pdf_files:
        logger.warning("No PDF files found in %s", pdf_directory)
        return []

    logger.info("Found %d PDF files in %s", len(pdf_files), pdf_directory)

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)

    results = []
    async with aiohttp.ClientSession(connector=connector) as session:
        for pdf_path in pdf_files:
            filename = os.path.basename(pdf_path)
            try:
                with open(pdf_path, "rb") as f:
                    data = aiohttp.FormData()
                    data.add_field(
                        "file", f,
                        filename=filename,
                        content_type="application/pdf",
                    )
                    data.add_field("category", category)

                    resp = await session.post(
                        f"{BACKEND_URL}/api/knowledge_base/upload",
                        data=data,
                        headers={"Authorization": f"Bearer {auth_token}"},
                    )
                    resp.raise_for_status()
                    result = await resp.json()
                    results.append(result)
                    logger.info(
                        "Uploaded: %s -> %s (%d words)",
                        filename,
                        result["document_id"],
                        result["word_count"],
                    )
            except Exception as exc:
                logger.error("Failed to upload %s: %s", filename, exc)
                results.append({"filename": filename, "error": str(exc)})

    logger.info(
        "Upload complete: %d/%d succeeded",
        sum(1 for r in results if "document_id" in r),
        len(pdf_files),
    )
    return results


if __name__ == "__main__":
    asyncio.run(upload_pdf_repository("/opt/autobot/documents"))
```

### What Happens After Upload

When a PDF is uploaded through `POST /api/knowledge_base/upload`:

1. **Validation** -- `_validate_file_upload()` checks file size (max 10 MB), extension
   (`.pdf` allowed), and filename for path traversal.
2. **Text extraction** -- `_extract_pdf_content()` uses `pypdf.PdfReader` to extract text
   from every page, joined with newlines.
3. **Fact storage** -- `_store_fact_in_kb()` calls `kb.store_fact()` which:
   - Generates a UUID fact ID
   - Stores content + metadata as JSON in Redis hash `knowledge_base:facts`
   - Triggers embedding generation via NPU worker (with Ollama fallback)
   - Indexes the embedding vector in ChromaDB
4. **Response** -- Returns `document_id`, `title`, `word_count`, and a content preview.

---

## 3. Knowledge API Endpoint Reference

All knowledge endpoints are registered under the prefix `/api/knowledge_base`
(see `api/registry.py`, `RouterConfig` with `module_path="api.knowledge"`).

Authentication: All write endpoints require admin permission (`check_admin_permission`);
read/search endpoints require authenticated user (`get_current_user`).

### Upload Document

```http
POST /api/knowledge_base/upload
Content-Type: multipart/form-data
Authorization: Bearer <token>

Fields:
  file:     <PDF binary>         (required, max 10 MB)
  title:    "Redis HA Guide"     (optional, defaults to filename)
  category: "documentation"      (optional, defaults to "uploads")
  tags:     '["redis","ha"]'     (optional, JSON array, max 20 tags)
```

**Response (200):**

```json
{
    "success": true,
    "document_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "title": "redis-guide.pdf",
    "content": "Redis Sentinel provides high availability for Redis...",
    "word_count": 4521,
    "message": "File uploaded (4521 words)"
}
```

**Error responses:**

| Status | Condition |
|--------|-----------|
| 400 | File too large (>10 MB), unsupported extension, path traversal in filename, no extractable text |
| 400 | `PDF support requires pypdf library` -- `pypdf` not installed |
| 500 | Knowledge base not initialized |

### Add Text Content

```http
POST /api/knowledge_base/facts
Content-Type: application/json
Authorization: Bearer <token>

{
    "content": "Redis Sentinel monitors master and replica instances...",
    "title": "Redis Sentinel Overview",
    "source": "internal-wiki",
    "category": "system_knowledge",
    "tags": ["redis", "sentinel", "ha"]
}
```

**Response (200):**

```json
{
    "success": true,
    "document_id": "fact_uuid_here",
    "title": "Redis Sentinel Overview",
    "content": "Redis Sentinel monitors master and replica instances...",
    "message": "Document added successfully"
}
```

### Add URL Content

```http
POST /api/knowledge_base/url
Content-Type: application/json
Authorization: Bearer <token>

{
    "url": "https://redis.io/docs/management/sentinel/",
    "title": "Redis Sentinel Docs",
    "method": "fetch",
    "category": "documentation",
    "tags": ["redis", "sentinel"]
}
```

**Response (200):**

```json
{
    "success": true,
    "document_id": "fact_uuid_here",
    "title": "Redis Sentinel Docs",
    "content": "Redis Sentinel provides high availability...",
    "message": "URL content added (2340 chars)"
}
```

### Search Knowledge Base (Consolidated Endpoint)

This is the **primary** search endpoint (Issue #555). It replaces the deprecated
`/enhanced_search`, `/rag_search`, `/similarity_search`, and `/enhanced_search_v2`
endpoints.

```http
POST /api/knowledge_base/search
Content-Type: application/json
Authorization: Bearer <token>

{
    "query": "How to configure Redis for high availability?",
    "top_k": 5,
    "category": "documentation",
    "mode": "hybrid",
    "enable_rag": false,
    "enable_reranking": true,
    "reformulate_query": false,
    "min_score": 0.3,
    "return_context": false,
    "tags": [],
    "tags_match_any": false
}
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | (required) | Search query, 1-1000 characters |
| `top_k` | int | 10 | Maximum results (1-100) |
| `category` | string | null | Filter by category |
| `mode` | string | `"hybrid"` | `"semantic"`, `"keyword"`, `"hybrid"`, or `"auto"` |
| `enable_rag` | bool | false | Enable RAG enhancement with synthesized response |
| `enable_reranking` | bool | false | Apply cross-encoder reranking |
| `reformulate_query` | bool | false | Expand query for better recall |
| `min_score` | float | 0.0 | Minimum relevance score threshold |
| `return_context` | bool | false | Return optimized context string for chat |
| `tags` | list | [] | Filter results by tags |
| `tags_match_any` | bool | false | Match any tag (true) or all tags (false) |

**Response (200) -- Standard search:**

```json
{
    "results": [
        {
            "content": "Redis Sentinel provides high availability for Redis...",
            "score": 0.89,
            "metadata": {
                "source": "redis-guide.pdf",
                "title": "Redis HA Guide",
                "category": "documentation",
                "type": "file",
                "filename": "redis-guide.pdf",
                "created_at": "2026-03-15T10:00:00Z"
            }
        }
    ],
    "total_results": 5,
    "query": "How to configure Redis for high availability?",
    "mode": "hybrid",
    "kb_implementation": "KnowledgeBase",
    "rag_applied": false,
    "reranking_applied": true,
    "reranking_method": "cross-encoder"
}
```

**Response (200) -- With `enable_rag: true`:**

```json
{
    "status": "success",
    "synthesized_response": "To configure Redis for high availability, you should...",
    "confidence_score": 0.92,
    "document_analysis": {
        "total_documents": 5,
        "relevance_distribution": "high"
    },
    "results": [ ... ],
    "total_results": 5,
    "original_query": "How to configure Redis for high availability?",
    "reformulated_queries": [
        "Redis Sentinel high availability setup",
        "Redis cluster failover configuration"
    ],
    "rag_applied": true,
    "sources_used": ["redis-guide.pdf", "sentinel-config.pdf"]
}
```

### Get Knowledge Stats

```http
GET /api/knowledge_base/stats
Authorization: Bearer <admin-token>
```

**Response (200):**

```json
{
    "total_facts": 5432,
    "total_vectors": 5430,
    "categories": ["documentation", "system_knowledge", "user_knowledge"],
    "db_size": 15728640,
    "status": "online",
    "initialized": true,
    "index_available": true,
    "rag_available": true,
    "last_updated": "2026-03-15T10:30:00Z"
}
```

### Get Main Categories

```http
GET /api/knowledge_base/categories/main
Authorization: Bearer <token>
```

**Response (200):**

```json
{
    "categories": [
        {
            "id": "autobot_documentation",
            "name": "AutoBot Documentation",
            "description": "Platform and codebase documentation",
            "icon": "book",
            "color": "#4A90D9",
            "examples": ["API guides", "Architecture docs"],
            "count": 1245
        },
        {
            "id": "system_knowledge",
            "name": "System Knowledge",
            "description": "System capabilities and man pages",
            "icon": "terminal",
            "color": "#27AE60",
            "examples": ["Man pages", "System commands"],
            "count": 3200
        },
        {
            "id": "user_knowledge",
            "name": "User Knowledge",
            "description": "User-uploaded content and notes",
            "icon": "user",
            "color": "#E67E22",
            "examples": ["Uploaded PDFs", "Manual entries"],
            "count": 987
        }
    ],
    "total": 3
}
```

### List Knowledge Entries (Paginated)

```http
GET /api/knowledge_base/entries?limit=20&cursor=0&category=documentation
Authorization: Bearer <admin-token>
```

**Response (200):**

```json
{
    "entries": [
        {
            "id": "fact_uuid",
            "content": "Redis Sentinel provides...",
            "title": "Redis HA Guide",
            "source": "redis-guide.pdf",
            "category": "documentation",
            "type": "file",
            "created_at": "2026-03-15T10:00:00Z",
            "metadata": { ... }
        }
    ],
    "next_cursor": "42",
    "count": 20,
    "has_more": true
}
```

### Delete a Fact

```http
DELETE /api/knowledge_base/facts/{fact_id}
Authorization: Bearer <admin-token>
```

### Knowledge Health Check

```http
GET /api/knowledge_base/health
Authorization: Bearer <admin-token>
```

**Response (200):**

```json
{
    "status": "healthy",
    "initialized": true,
    "redis_connected": true,
    "vector_store_available": true,
    "total_facts": 5432,
    "db_size": 15728640,
    "kb_implementation": "KnowledgeBase",
    "rag_available": true,
    "rag_status": "healthy"
}
```

---

## 4. RAG-Enhanced Chat Flow

AutoBot's chat endpoint (`POST /api/chat/message`) has built-in knowledge base integration.
When `use_knowledge_base` is `true` (the default), the backend automatically searches the
knowledge base for relevant context before sending the query to the LLM.

### How Chat RAG Works Internally

The function `_enhance_with_knowledge_base()` in `api/chat.py` implements the context
injection:

```
User Message (use_knowledge_base=true)
         |
         v
kb.search(query=message.content, top_k=5)
         |
         v
Build context string from top 3 results:
  "Relevant knowledge context:\n- [content[:300]]..."
         |
         v
Pass as `enhanced_context` to AI Stack client:
  ai_client.chat_message(message=..., context=enhanced_context, ...)
         |
         v
LLM generates response grounded in retrieved context
```

### Complete RAG Chat Client

```python
#!/usr/bin/env python3
"""RAG-enhanced chat: fetch PDF context, then generate a grounded response."""

import asyncio
import json
import logging
import ssl

import aiohttp

from autobot_shared.ssot_config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKEND_URL = f"https://{config.vm.main}:{config.port.backend}"


def _build_ssl_context() -> ssl.SSLContext:
    """Build a permissive SSL context for internal communication."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def rag_chat_with_pdf_context(
    query: str,
    auth_token: str,
    session_id: str = "",
    score_threshold: float = 0.3,
    top_k: int = 5,
) -> dict:
    """
    Complete RAG workflow: search knowledge base for PDF context, then chat.

    This function performs two API calls:
    1. POST /api/knowledge_base/search -- retrieve relevant PDF chunks
    2. POST /api/chat/message -- send query with knowledge base context enabled

    The chat endpoint internally calls _enhance_with_knowledge_base() which
    performs its own KB search, but this explicit two-step approach gives you
    visibility into the retrieved context and lets you customize the search.

    Args:
        query: User question to answer.
        auth_token: Bearer token for API authentication.
        session_id: Chat session ID for conversation continuity.
        score_threshold: Minimum relevance score for search results.
        top_k: Number of context chunks to retrieve.

    Returns:
        Dict with answer, sources, and search metadata.
    """
    ssl_ctx = _build_ssl_context()
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)
    headers = {"Authorization": f"Bearer {auth_token}"}

    async with aiohttp.ClientSession(connector=connector) as session:
        # Step 1: Search knowledge base for relevant PDF chunks
        search_resp = await session.post(
            f"{BACKEND_URL}/api/knowledge_base/search",
            json={
                "query": query,
                "top_k": top_k,
                "mode": "hybrid",
                "enable_reranking": True,
                "min_score": score_threshold,
            },
            headers=headers,
        )
        search_resp.raise_for_status()
        search_results = await search_resp.json()

        # Log retrieved context
        results = search_results.get("results", [])
        logger.info(
            "Retrieved %d chunks (threshold=%.2f)", len(results), score_threshold
        )
        for i, result in enumerate(results):
            source = result.get("metadata", {}).get("source", "unknown")
            score = result.get("score", 0.0)
            logger.info("  [%d] score=%.3f source=%s", i, score, source)

        # Step 2: Send to chat with knowledge base context enabled
        chat_resp = await session.post(
            f"{BACKEND_URL}/api/chat/message",
            json={
                "content": query,
                "session_id": session_id,
                "use_knowledge_base": True,
                "use_ai_stack": True,
                "include_sources": True,
                "stream": False,
            },
            headers=headers,
        )
        chat_resp.raise_for_status()
        chat_data = await chat_resp.json()

        response_content = chat_data.get("data", {}).get("content", "")
        sources = [
            r.get("metadata", {}).get("source", "unknown") for r in results
        ]

        return {
            "answer": response_content,
            "sources": list(set(sources)),
            "search_results_count": len(results),
            "session_id": chat_data.get("data", {}).get("session_id", ""),
        }


if __name__ == "__main__":
    result = asyncio.run(
        rag_chat_with_pdf_context(
            query="What are the best practices for Redis high availability?",
            auth_token="<your-token>",
        )
    )
    print(f"\nAnswer: {result['answer'][:500]}")
    print(f"Sources: {result['sources']}")
```

### Using the Chat Endpoint Directly (Simpler Approach)

If you do not need explicit control over the search step, send a message with
`use_knowledge_base: true` and the backend handles everything:

```python
async def simple_rag_chat(query: str, auth_token: str) -> str:
    """
    Minimal RAG chat -- the backend handles KB search internally.

    Args:
        query: User question.
        auth_token: Bearer token.

    Returns:
        LLM response string augmented with knowledge base context.
    """
    ssl_ctx = _build_ssl_context()
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)

    async with aiohttp.ClientSession(connector=connector) as session:
        resp = await session.post(
            f"{BACKEND_URL}/api/chat/message",
            json={
                "content": query,
                "use_knowledge_base": True,
                "use_ai_stack": True,
                "stream": False,
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        resp.raise_for_status()
        data = await resp.json()
        return data.get("data", {}).get("content", "")
```

---

## 5. NPU Search with Hybrid Scoring

AutoBot provides multiple search strategies that can be combined for optimal retrieval
quality. The consolidated `/api/knowledge_base/search` endpoint supports all modes.

### Search Modes

| Mode | Implementation | Best For |
|------|---------------|----------|
| `semantic` | ChromaDB vector cosine similarity | Conceptual/meaning-based queries |
| `keyword` | Redis full-text keyword matching | Exact term lookups, identifiers |
| `hybrid` | Reciprocal Rank Fusion of semantic + keyword | General-purpose (default, recommended) |
| `auto` | Intelligent mode selection based on query analysis | When query type varies |

### Hybrid Search Weights

The `AdvancedRAGOptimizer` applies these default weights (configurable via `RAGConfig`):

- **Semantic weight:** 0.7 (vector similarity)
- **Keyword weight:** 0.3 (term matching)

These are normalized to sum to 1.0, validated at config load time.

### Cross-Encoder Reranking

When `enable_reranking: true`, results pass through a second-stage cross-encoder model
(`cross-encoder/ms-marco-MiniLM-L-6-v2`) that scores each (query, document) pair jointly
for more accurate relevance ranking.

### NPU-Accelerated Search

The NPU search endpoint (`/api/npu-search/semantic`) provides hardware-accelerated
search with automatic device selection:

```python
async def npu_enhanced_search(
    query: str,
    auth_token: str,
    top_k: int = 10,
) -> dict:
    """
    Perform NPU-accelerated semantic search.

    The endpoint automatically selects the best available hardware:
    NPU > GPU > CPU, with intelligent workload-based routing.

    Args:
        query: Search query string.
        auth_token: Bearer token for API authentication.
        top_k: Number of results to return (1-100).

    Returns:
        Search results with hardware performance metrics.
    """
    ssl_ctx = _build_ssl_context()
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)

    async with aiohttp.ClientSession(connector=connector) as session:
        resp = await session.post(
            f"{BACKEND_URL}/api/npu-search/semantic",
            json={
                "query": query,
                "similarity_top_k": top_k,
                "enable_npu_acceleration": True,
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        resp.raise_for_status()
        data = await resp.json()

        return {
            "results": data["results"],
            "device_used": data["device_used"],
            "search_time_ms": data["search_time_ms"],
            "total_results": data["total_results"],
        }
```

**Response includes hardware metrics:**

```json
{
    "query": "Redis high availability",
    "results": [ ... ],
    "metrics": {
        "total_documents_searched": 5432,
        "embedding_generation_time_ms": 12.5,
        "similarity_computation_time_ms": 8.3,
        "total_search_time_ms": 24.1,
        "device_used": "npu",
        "hardware_utilization": 0.45
    },
    "total_results": 10,
    "search_time_ms": 24.1,
    "device_used": "npu",
    "cache_hit": false
}
```

---

## 6. Document Vectorization Pipeline

Understanding the internal vectorization pipeline helps diagnose indexing issues and
optimize retrieval quality.

### Pipeline Stages

```
Stage 1: Text Extraction
  Input:  PDF binary (max 10 MB)
  Method: pypdf.PdfReader -- iterate pages, extract_text()
  Output: Plain text string with page boundaries (\n-separated)

Stage 2: Fact Storage
  Input:  Plain text + metadata dict
  Method: kb.store_fact() in knowledge/facts.py
  Output: Redis hash entry in knowledge_base:facts
          Key: UUID fact_id
          Value: JSON {content, metadata: {source, category, tags, ...}}

Stage 3: Embedding Generation
  Input:  Text content string
  Method: _generate_embedding_with_npu_fallback()
          Priority: NPU Worker > Ollama > sentence-transformers
  Output: Float vector (dimensionality depends on model, typically 384 or 768)

Stage 4: ChromaDB Indexing
  Input:  Embedding vector + metadata
  Method: ChromaVectorStore.add() via LlamaIndex
  Config: HNSW index with cosine similarity
          construction_ef=300, search_ef=100, M=32
          Optimized for 545K+ vectors (Issue #72)
  Output: Indexed vector in ChromaDB collection "autobot_memory"

Stage 5: Background Vectorization (Optional)
  For bulk operations, get_background_vectorizer() processes facts
  asynchronously via api/knowledge_vectorization.py endpoints
```

### Checking Vectorization Status

```python
async def check_vectorization_status(
    fact_ids: list,
    auth_token: str,
) -> dict:
    """
    Check which facts have been vectorized in ChromaDB.

    Args:
        fact_ids: List of fact UUIDs to check.
        auth_token: Bearer token.

    Returns:
        Dict with per-fact status and summary statistics.
    """
    ssl_ctx = _build_ssl_context()
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)

    async with aiohttp.ClientSession(connector=connector) as session:
        resp = await session.post(
            f"{BACKEND_URL}/api/knowledge_base/vectorization/batch_status",
            json={"fact_ids": fact_ids},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        resp.raise_for_status()
        return await resp.json()
```

**Response:**

```json
{
    "statuses": {
        "fact_uuid_1": {"vectorized": true},
        "fact_uuid_2": {"vectorized": false}
    },
    "summary": {
        "total_checked": 2,
        "vectorized": 1,
        "not_vectorized": 1,
        "vectorization_percentage": 50.0
    },
    "check_time_ms": 3.45
}
```

### Using the Knowledge Base Directly (Backend Code)

For backend services that need direct access without HTTP:

```python
from knowledge import get_knowledge_base


async def index_pdf_internally(pdf_path: str, category: str = "documentation"):
    """
    Index a PDF using the knowledge base directly (backend-only).

    This bypasses the HTTP API and calls the KnowledgeBase singleton directly.

    Args:
        pdf_path: Path to the PDF file on the server.
        category: Category for the document.

    Returns:
        Dict with status and fact_id.
    """
    kb = await get_knowledge_base()

    result = await kb.add_document_from_file(
        file_path=pdf_path,
        category=category,
        metadata={
            "source": pdf_path.rsplit("/", 1)[-1],
            "type": "file",
        },
    )

    return result
```

---

## 7. Graph RAG (Advanced)

Graph RAG extends standard RAG by incorporating relationship data from AutoBot's memory
graph (`AutoBotMemoryGraph`). This enables retrieval that follows entity relationships --
for example, finding security policies that apply to Redis by traversing from the "Redis"
entity through "configured_by" and "governed_by" relationships.

### Architecture

`GraphRAGService` uses pure composition (no inheritance):

```
GraphRAGService
  |-- rag_service: RAGService        (reused, not duplicated)
  |-- memory_graph: AutoBotMemoryGraph  (reused, not duplicated)
```

**Graph-Aware Retrieval Strategy:**

1. **Initial RAG search** -- Standard semantic + keyword hybrid search via `RAGService`
2. **Entity extraction** -- Identify entities mentioned in top results
3. **Graph expansion** -- Use `AutoBotMemoryGraph` to find related entities (up to `max_depth` hops)
4. **Context gathering** -- Retrieve observations from related entities
5. **Result combination** -- Merge and deduplicate with `_seen_content` set
6. **Hybrid ranking** -- Score by (1 - `graph_weight`) * RAG relevance + `graph_weight` * graph proximity
7. **Reranking** -- Apply cross-encoder reranking (reused from `RAGService`)

### Graph RAG API Endpoints

**Search (POST /api/graph-rag/search):**

```python
async def graph_rag_search(
    query: str,
    auth_token: str,
    start_entity: str = None,
    max_depth: int = 2,
    max_results: int = 5,
) -> dict:
    """
    Perform graph-aware RAG search combining semantic search with graph traversal.

    Args:
        query: Search query string (1-1000 chars).
        auth_token: Bearer token for authenticated access.
        start_entity: Optional starting entity for graph traversal.
        max_depth: Maximum traversal depth, 1-3 hops (default: 2).
        max_results: Maximum results to return, 1-20 (default: 5).

    Returns:
        Dict with results, metrics, and request_id.
    """
    ssl_ctx = _build_ssl_context()
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)

    async with aiohttp.ClientSession(connector=connector) as session:
        resp = await session.post(
            f"{BACKEND_URL}/api/graph-rag/search",
            json={
                "query": query,
                "start_entity": start_entity,
                "max_depth": max_depth,
                "max_results": max_results,
                "enable_reranking": True,
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        resp.raise_for_status()
        return await resp.json()
```

**Response:**

```json
{
    "success": true,
    "results": [
        {
            "content": "Redis Sentinel provides automatic failover...",
            "metadata": {
                "source": "redis-guide.pdf",
                "category": "documentation"
            },
            "semantic_score": 0.89,
            "keyword_score": 0.45,
            "hybrid_score": 0.76,
            "relevance_rank": 1,
            "source_path": "knowledge_base:facts:fact_uuid"
        }
    ],
    "metrics": {
        "query_processing_time": 0.012,
        "retrieval_time": 0.089,
        "reranking_time": 0.034,
        "graph_traversal_time": 0.023,
        "total_time": 0.158,
        "documents_considered": 20,
        "final_results_count": 5,
        "entities_explored": 8,
        "graph_expansion_enabled": true,
        "graph_results_added": 3
    },
    "request_id": "req_abc123"
}
```

**Health Check (GET /api/graph-rag/health):**

```json
{
    "status": "healthy",
    "components": {
        "graph_rag_service": "healthy",
        "rag_service": "healthy",
        "memory_graph": "healthy"
    },
    "timestamp": "2026-03-15T10:30:00Z"
}
```

**Performance Metrics (GET /api/graph-rag/metrics):**

```json
{
    "service": "GraphRAGService",
    "graph_weight": 0.3,
    "entity_extraction_enabled": true,
    "rag_service": {
        "enable_advanced_rag": true,
        "timeout_seconds": 10.0
    },
    "graph_initialized": true
}
```

---

## 8. Natural Language Search

AutoBot's natural language search system (`api/natural_language_search.py`) provides
intent-classified code search. While primarily designed for codebase queries, it
integrates with the knowledge base for document retrieval.

### Query Intent Classification

The system classifies queries into intents using regex pattern matching:

| Intent | Example Query |
|--------|--------------|
| `find_definition` | "Where is KnowledgeBase defined?" |
| `find_usage` | "Where is ChromaDB used?" |
| `find_implementation` | "How is hybrid search implemented?" |
| `find_error_handling` | "How are errors handled in the RAG pipeline?" |
| `find_configuration` | "Where is Redis configured?" |
| `find_tests` | "What tests exist for the knowledge base?" |
| `find_dependencies` | "What does RAGService depend on?" |
| `explain_code` | "Explain how the embedding cache works" |
| `general_search` | "Show me all documents about Redis" |

### Query Domain Detection

Queries are also classified by domain using keyword matching:

| Domain | Keywords |
|--------|----------|
| `database` | database, db, sql, redis, mongo, postgres, orm |
| `api` | api, endpoint, route, rest, request, response, http |
| `security` | auth, login, password, token, jwt, permission |
| `configuration` | config, settings, environment, setup |
| `caching` | cache, redis, memcached, ttl |

### Natural Language Search Example

```python
async def natural_language_search(
    query: str,
    auth_token: str,
) -> dict:
    """
    Search using natural language with intent classification.

    The endpoint parses the query to determine intent and domain,
    then routes to the appropriate search strategy.

    Args:
        query: Natural language query string.
        auth_token: Bearer token.

    Returns:
        Dict with classified intent, search results, and suggestions.
    """
    ssl_ctx = _build_ssl_context()
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)

    async with aiohttp.ClientSession(connector=connector) as session:
        resp = await session.post(
            f"{BACKEND_URL}/api/natural-language-search/nl-search/query",
            json={
                "query": query,
                "intent_classification": True,
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        resp.raise_for_status()
        return await resp.json()
```

---

## 9. Complete End-to-End Example

This script demonstrates the full RAG workflow: upload a repository of PDFs, verify
indexing, query with RAG augmentation, and display cited sources.

```python
#!/usr/bin/env python3
"""
Complete RAG Workflow with PDF Repository

End-to-end demonstration:
1. Upload all PDFs from a directory
2. Verify indexing completed
3. Query with RAG-augmented search
4. Display response with source citations
"""

import asyncio
import glob
import logging
import os
import ssl
import sys

import aiohttp

from autobot_shared.ssot_config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

BACKEND_URL = f"https://{config.vm.main}:{config.port.backend}"


def _build_ssl_context() -> ssl.SSLContext:
    """Build SSL context for internal HTTPS communication."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def step_1_upload_pdfs(
    session: aiohttp.ClientSession,
    pdf_directory: str,
    headers: dict,
) -> list:
    """
    Upload all PDFs from a directory to the knowledge base.

    Args:
        session: Active aiohttp session.
        pdf_directory: Directory containing PDF files.
        headers: Request headers including Authorization.

    Returns:
        List of document IDs for successfully uploaded files.
    """
    pdf_files = sorted(glob.glob(os.path.join(pdf_directory, "*.pdf")))
    if not pdf_files:
        logger.error("No PDF files found in %s", pdf_directory)
        return []

    logger.info("=== Step 1: Uploading %d PDFs ===", len(pdf_files))
    doc_ids = []

    for pdf_path in pdf_files:
        filename = os.path.basename(pdf_path)
        try:
            with open(pdf_path, "rb") as f:
                data = aiohttp.FormData()
                data.add_field(
                    "file", f,
                    filename=filename,
                    content_type="application/pdf",
                )
                data.add_field("category", "pdf_repository")

                resp = await session.post(
                    f"{BACKEND_URL}/api/knowledge_base/upload",
                    data=data,
                    headers=headers,
                )
                resp.raise_for_status()
                result = await resp.json()

                doc_id = result["document_id"]
                doc_ids.append(doc_id)
                logger.info(
                    "  Uploaded: %s -> %s (%d words)",
                    filename, doc_id, result["word_count"],
                )
        except Exception as exc:
            logger.error("  Failed: %s -- %s", filename, exc)

    logger.info("Uploaded %d/%d files", len(doc_ids), len(pdf_files))
    return doc_ids


async def step_2_verify_indexing(
    session: aiohttp.ClientSession,
    headers: dict,
    expected_count: int,
    max_wait_seconds: int = 60,
) -> bool:
    """
    Wait for indexing to complete by polling knowledge base stats.

    Args:
        session: Active aiohttp session.
        headers: Request headers including Authorization.
        expected_count: Minimum number of facts expected.
        max_wait_seconds: Maximum time to wait for indexing.

    Returns:
        True if indexing verified, False if timed out.
    """
    logger.info("=== Step 2: Verifying indexing ===")

    for elapsed in range(0, max_wait_seconds, 5):
        resp = await session.get(
            f"{BACKEND_URL}/api/knowledge_base/stats",
            headers=headers,
        )
        if resp.status == 200:
            stats = await resp.json()
            total = stats.get("total_facts", 0)
            vectors = stats.get("total_vectors", 0)
            logger.info(
                "  [%ds] Facts: %d, Vectors: %d", elapsed, total, vectors,
            )
            if total >= expected_count and vectors >= expected_count:
                logger.info("  Indexing verified: all documents vectorized")
                return True

        await asyncio.sleep(5)

    logger.warning("  Indexing verification timed out after %ds", max_wait_seconds)
    return False


async def step_3_rag_query(
    session: aiohttp.ClientSession,
    query: str,
    headers: dict,
) -> dict:
    """
    Perform a RAG-enhanced search query.

    Args:
        session: Active aiohttp session.
        query: User question to answer.
        headers: Request headers including Authorization.

    Returns:
        Dict with search results and synthesized response.
    """
    logger.info("=== Step 3: RAG Query ===")
    logger.info("  Query: %s", query)

    # Search with RAG enhancement enabled
    resp = await session.post(
        f"{BACKEND_URL}/api/knowledge_base/search",
        json={
            "query": query,
            "top_k": 5,
            "mode": "hybrid",
            "enable_rag": True,
            "enable_reranking": True,
            "reformulate_query": True,
            "min_score": 0.3,
        },
        headers=headers,
    )
    resp.raise_for_status()
    return await resp.json()


async def step_4_chat_with_context(
    session: aiohttp.ClientSession,
    query: str,
    headers: dict,
) -> dict:
    """
    Send a chat message with knowledge base context.

    Args:
        session: Active aiohttp session.
        query: User question to answer.
        headers: Request headers including Authorization.

    Returns:
        Chat response dict.
    """
    logger.info("=== Step 4: Chat with RAG Context ===")

    resp = await session.post(
        f"{BACKEND_URL}/api/chat/message",
        json={
            "content": query,
            "use_knowledge_base": True,
            "use_ai_stack": True,
            "include_sources": True,
            "stream": False,
        },
        headers=headers,
    )
    resp.raise_for_status()
    return await resp.json()


async def full_rag_workflow(
    pdf_directory: str,
    query: str,
    auth_token: str,
) -> None:
    """
    Execute the complete end-to-end RAG workflow.

    Args:
        pdf_directory: Directory containing PDF files to index.
        query: Question to answer using the indexed documents.
        auth_token: Bearer token for API authentication.
    """
    ssl_ctx = _build_ssl_context()
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)
    headers = {"Authorization": f"Bearer {auth_token}"}

    async with aiohttp.ClientSession(connector=connector) as session:
        # Step 1: Upload PDFs
        doc_ids = await step_1_upload_pdfs(session, pdf_directory, headers)
        if not doc_ids:
            logger.error("No documents uploaded. Aborting.")
            return

        # Step 2: Verify indexing
        await step_2_verify_indexing(
            session, headers, expected_count=len(doc_ids),
        )

        # Step 3: RAG-enhanced search
        search_result = await step_3_rag_query(session, query, headers)

        if search_result.get("synthesized_response"):
            logger.info("\n--- Synthesized Answer ---")
            logger.info(search_result["synthesized_response"][:1000])
            sources = search_result.get("sources_used", [])
            if sources:
                logger.info("\nSources: %s", ", ".join(sources))

        # Step 4: Chat with context
        chat_result = await step_4_chat_with_context(session, query, headers)
        answer = chat_result.get("data", {}).get("content", "")
        logger.info("\n--- Chat Response ---")
        logger.info(answer[:1000])

    logger.info("\n=== Workflow Complete ===")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python rag_workflow.py <pdf_directory> <query> [auth_token]")
        print('Example: python rag_workflow.py /opt/autobot/documents '
              '"What are Redis HA best practices?"')
        sys.exit(1)

    pdf_dir = sys.argv[1]
    user_query = sys.argv[2]
    token = sys.argv[3] if len(sys.argv) > 3 else ""

    asyncio.run(full_rag_workflow(pdf_dir, user_query, token))
```

---

## 10. Configuration Reference

RAG behavior is controlled by `RAGConfig` (defined in `services/rag_config.py`),
which loads from `config/complete.yaml` under the `knowledge.rag` section.

### RAG Configuration Parameters

```yaml
# config/complete.yaml -- knowledge.rag section
knowledge:
  rag:
    # Hybrid search weights (must sum to 1.0)
    hybrid_weight_semantic: 0.7    # Weight for vector similarity
    hybrid_weight_keyword: 0.3     # Weight for keyword matching

    # Search parameters
    max_results_per_stage: 20      # Results to consider in each pipeline stage
    diversity_threshold: 0.85      # Cosine similarity threshold for diversification
    default_max_results: 10        # Default top_k when not specified

    # Context optimization
    default_context_length: 2000   # Default context window (chars)
    max_context_length: 8000       # Maximum context window (chars)

    # Reranking
    enable_reranking: true
    reranking_model: "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Performance
    cache_ttl_seconds: 300         # Result cache TTL
    timeout_seconds: 10.0          # Search timeout

    # Feature flags
    enable_advanced_rag: true      # Enable AdvancedRAGOptimizer
    fallback_to_basic_search: true # Fall back to basic search on error

    # Category filtering for chat RAG
    default_chat_categories: null  # null = search all categories
    enable_smart_category_selection: true
```

### ChromaDB HNSW Index Parameters

Configured in `knowledge/base.py` via `ConfigManager`:

| Parameter | Config Path | Default | Description |
|-----------|------------|---------|-------------|
| `space` | `memory.chromadb.hnsw.space` | `cosine` | Distance metric |
| `construction_ef` | `memory.chromadb.hnsw.construction_ef` | 300 | Build-time accuracy (higher = slower build, better recall) |
| `search_ef` | `memory.chromadb.hnsw.search_ef` | 100 | Query-time accuracy (higher = slower query, better recall) |
| `M` | `memory.chromadb.hnsw.M` | 32 | Connections per node (higher = more memory, better recall) |

These values are optimized for the 545K+ vector collection (Issue #72).

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `AUTOBOT_NPU_ENABLED` | Enable NPU acceleration for embeddings | `true` |
| `AUTOBOT_NPU_DEVICE` | Device selection: `AUTO`, `CPU`, `GPU`, `NPU` | `AUTO` |
| `AUTOBOT_OLLAMA_HOST` | Ollama endpoint for fallback embeddings | `127.0.0.1` |

### Score Threshold Alignment

All search endpoints use a consistent default `score_threshold` of **0.3** (Issue #1532
aligned this across 6 locations). Adjust this to control result quality:

- **0.1-0.2**: Broad recall, includes tangentially relevant results
- **0.3** (default): Balanced precision and recall
- **0.5-0.7**: High precision, only highly relevant results
- **0.8+**: Very strict, may miss relevant content

---

## 11. Troubleshooting

### Low Relevance Scores

**Symptoms:** Search returns results with scores below 0.3, or no results at all.

**Diagnosis:**

```bash
# Check knowledge base health
curl -sk https://<backend-ip>:8443/api/knowledge_base/health \
  -H "Authorization: Bearer <token>" | python3 -m json.tool

# Check total facts and vectors
curl -sk https://<backend-ip>:8443/api/knowledge_base/stats \
  -H "Authorization: Bearer <token>" | python3 -m json.tool

# Verify NPU availability for embeddings
curl -sk https://<backend-ip>:8443/api/npu-search/hardware/status \
  -H "Authorization: Bearer <token>" | python3 -m json.tool
```

**Fixes:**

- If `total_vectors` is much lower than `total_facts`, background vectorization is incomplete.
  Wait or trigger manual vectorization.
- If `rag_status` is `"error"`, the RAG Agent failed to initialize. Check AI Stack availability
  on <aiml-ip>.
- Lower the `score_threshold` / `min_score` parameter to 0.1 to see if content exists but
  scores below threshold.
- Switch to `mode: "hybrid"` -- pure semantic search may miss keyword-heavy content.

### Missing PDF Content

**Symptoms:** Upload succeeds but search returns no results from the uploaded PDF.

**Diagnosis:**

```bash
# List recent entries to verify the upload is stored
curl -sk "https://<backend-ip>:8443/api/knowledge_base/entries?limit=5" \
  -H "Authorization: Bearer <token>" | python3 -m json.tool
```

**Fixes:**

- Verify `pypdf` is installed: `pip list | grep pypdf`. If missing, install it into the
  backend venv (`/opt/autobot/autobot-backend/venv`).
- Check if the PDF contains actual text (not scanned images). `pypdf` cannot OCR images.
  For scanned PDFs, pre-process with an OCR tool before uploading.
- Check the upload response `word_count` -- if 0, no text was extracted.
- Verify the file is under 10 MB. Larger files are rejected with HTTP 400.

### Slow Queries

**Symptoms:** Search takes more than 2-3 seconds.

**Diagnosis:**

```bash
# Run a benchmark
curl -sk https://<backend-ip>:8443/api/npu-search/benchmark \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"test_queries": ["test query"], "iterations": 3}' | python3 -m json.tool

# Check performance analytics
curl -sk https://<backend-ip>:8443/api/npu-search/performance/analytics \
  -H "Authorization: Bearer <token>" | python3 -m json.tool
```

**Fixes:**

- If `device_used` is `"cpu"`, NPU and GPU are unavailable. Check NPU Worker on
  <npu-ip> and GPU drivers.
- If `cache_size` is 0, the search cache is cold. Performance improves after repeated queries.
- If `embedding_generation_time_ms` is high, the embedding model may need warming up.
  The backend runs `warmup_npu_connection()` at startup (Issue #165).
- Reduce `top_k` to limit result processing.
- Disable `enable_reranking` if cross-encoder reranking is the bottleneck.

### Knowledge Base Not Initialized

**Symptoms:** All knowledge endpoints return "Knowledge base not initialized."

**Diagnosis:**

```bash
# Check backend logs
journalctl -u autobot-backend -n 100 --no-pager | grep -i "knowledge\|chromadb\|redis"

# Or check the log file directly
tail -100 /var/log/autobot/backend.log | grep -i "knowledge\|init"
```

**Fixes:**

- Verify Redis is accessible on <database-ip>:6379. The knowledge base uses DB 1.
- Verify ChromaDB data directory exists and is writable: `ls -la data/chromadb/`.
- Check if Ollama is running (needed for LlamaIndex embedding configuration):
  `curl http://127.0.0.1:11434/api/tags`.
- The backend takes approximately 6 minutes to fully initialize. 502 errors immediately
  after restart are transient.

### RAG Agent Unavailable

**Symptoms:** `rag_available: false` in health check, or `enable_rag: true` returns 503.

**Diagnosis:**

```bash
# Check if RAG Agent imports succeed
# The RAG Agent requires SSOT config for provider, endpoint, and model
python3 -c "from agents.rag_agent import get_rag_agent; print('OK')"
```

**Fixes:**

- Ensure SSOT config has `rag` agent configuration with provider, endpoint, and model.
- Verify the configured LLM endpoint is reachable (Ollama or AI Stack).
- Check `RAG_AVAILABLE` flag in backend logs -- import errors are logged at startup.

### Graph RAG Service Unavailable (503)

**Symptoms:** `GET /api/graph-rag/health` returns 503 or "Graph-RAG service not available."

**Fixes:**

- `GraphRAGService` is initialized during application lifespan and stored in `app.state`.
  If it fails, the service returns 503 on all endpoints.
- Check that both `RAGService` and `AutoBotMemoryGraph` initialized successfully.
- Verify the memory graph has data: the graph component reports `"unavailable"` if
  `graph.initialized` is `False`.

---

## Appendix: Module Cross-Reference

| Source File | Purpose | Key Classes/Functions |
|-------------|---------|----------------------|
| `api/knowledge.py` | REST API (CRUD, upload, categories) | `upload_file_to_knowledge()`, `add_facts_to_knowledge()`, `_extract_pdf_content()` |
| `api/knowledge_search.py` | Consolidated search endpoint | `consolidated_search()`, `_execute_kb_search()`, `_apply_reranking()` |
| `api/knowledge_vectorization.py` | Vectorization status and management | `_check_vectorization_batch_internal()` |
| `api/knowledge_models.py` | Pydantic request/response models | `ConsolidatedSearchRequest`, `EnhancedSearchRequest` |
| `api/graph_rag.py` | Graph RAG REST endpoints | `graph_rag_search()`, `GraphRAGSearchRequest` |
| `api/enhanced_search.py` | NPU-accelerated semantic search | `enhanced_semantic_search()`, `SearchRequest` |
| `api/natural_language_search.py` | Intent-classified NL search | `QueryIntent`, `ParsedQuery`, `INTENT_PATTERNS` |
| `api/chat.py` | Chat with KB context injection | `_enhance_with_knowledge_base()`, `EnhancedChatMessage` |
| `knowledge/__init__.py` | KnowledgeBase composed class | `KnowledgeBase`, `get_knowledge_base()` |
| `knowledge/base.py` | Core: Redis + ChromaDB + LlamaIndex init | `KnowledgeBaseCore`, `_init_redis_config()` |
| `knowledge/facts.py` | Fact CRUD + NPU embedding | `FactsMixin`, `_generate_embedding_with_npu_fallback()` |
| `knowledge/search.py` | Search facade (delegates to search_components/) | `SearchMixin`, `search()`, `enhanced_search()` |
| `knowledge/documents.py` | Document ingestion | `DocumentsMixin`, `add_document_from_file()` |
| `knowledge/index.py` | ChromaDB index rebuild | `IndexMixin`, HNSW parameter management |
| `knowledge_factory.py` | Singleton factory (breaks circular import) | `get_or_create_knowledge_base()` |
| `services/rag_service.py` | RAG service layer | `RAGService`, `advanced_search()`, `_fallback_basic_search()` |
| `services/rag_config.py` | RAG configuration | `RAGConfig`, `get_rag_config()`, `update_rag_config()` |
| `services/graph_rag_service.py` | Graph-aware RAG | `GraphRAGService`, `graph_aware_search()`, `GraphRAGMetrics` |
| `agents/rag_agent.py` | RAG agent for synthesis | `RAGAgent`, `process_document_query()`, `reformulate_query()` |
| `advanced_rag_optimizer.py` | Core RAG optimizer | `AdvancedRAGOptimizer`, `SearchResult`, `RAGMetrics`, `QueryContext` |
