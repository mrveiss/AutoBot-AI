# Implement a Retrieval-Augmented Generation (RAG) workflow that fetches context from a PDF repository before generating a response

AutoBot's knowledge base ingests PDF files, chunks and embeds them into ChromaDB, and automatically retrieves relevant passages as context before every LLM call.  No workflow configuration is required — upload PDFs and the RAG pipeline activates transparently for every chat session.

## Step 1 — Upload PDFs to the knowledge base

```python
import httpx
from pathlib import Path

BASE_URL = "https://autobot.example.com:8443/api"
TOKEN    = "your-admin-jwt-token"

client = httpx.Client(
    base_url=BASE_URL,
    headers={"Authorization": f"Bearer {TOKEN}"},
    verify=False,
)

def upload_pdf(path: str, title: str = "", tags: list[str] | None = None) -> dict:
    """Upload a PDF file to AutoBot's knowledge base."""
    file_path = Path(path)
    with file_path.open("rb") as f:
        response = client.post(
            "/knowledge_base/upload",
            files={"file": (file_path.name, f, "application/pdf")},
            data={
                "title":    title or file_path.stem,
                "category": "uploads",
                "tags":     ",".join(tags or []),
            },
        )
    response.raise_for_status()
    result = response.json()
    print(f"Uploaded: {result['document_id']} — {result['title']}")
    return result


# Upload a directory of PDFs
pdf_dir = Path("/home/user/documentation/")
for pdf_file in pdf_dir.glob("*.pdf"):
    upload_pdf(str(pdf_file), tags=["documentation"])
```

Supported upload formats: `.pdf`, `.txt`, `.md`, `.docx`, `.json`, `.csv`, `.html` (max 10 MB each).

## Step 2 — Chat automatically retrieves PDF context

Once PDFs are uploaded, every chat message triggers RAG retrieval automatically.  No additional configuration is needed:

```python
# Send a chat message — RAG context is retrieved and injected automatically
response = client.post("/chat/message", json={
    "session_id": "my-session",
    "message":    "What does the API documentation say about authentication?",
}).json()

print(response["response"])

# Inspect which PDF passages were used as context
for citation in response.get("citations", []):
    print(f"  [{citation['score']:.2f}] {citation['source']} — {citation['content'][:80]}...")
```

## How the RAG pipeline works

```
User message
  │
  ├─ ChatKnowledgeService.conversation_aware_retrieve()
  │       │
  │       ├─ Intent detection  — decides if retrieval is appropriate
  │       ├─ Query enhancement — rewrites query with conversation context
  │       ├─ Category routing  — selects relevant ChromaDB collections
  │       │
  │       └─ RAGService.advanced_search()
  │               │
  │               ├─ Semantic search (vector similarity via embeddings)
  │               ├─ Keyword search  (BM25 over text content)
  │               ├─ Hybrid ranking  (blends semantic + keyword scores)
  │               └─ Optional reranking (cross-encoder for accuracy)
  │
  ├─ Build full prompt:
  │       KNOWLEDGE CONTEXT:
  │       1. [score: 0.95] <PDF passage 1>
  │       2. [score: 0.87] <PDF passage 2>
  │       ...
  │       <conversation history>
  │       <user message>
  │
  └─ LLM call → response with citations
```

## Step 3 — Query the knowledge base directly

To search the PDF repository without going through the chat interface:

```python
# Basic RAG search
results = client.post("/knowledge_search/rag_search", json={
    "query":           "authentication token expiry",
    "top_k":           5,
    "score_threshold": 0.3,
    "categories":      ["uploads"],   # restrict to uploaded PDFs
}).json()

for fact in results.get("results", []):
    print(f"[{fact['score']:.2f}] {fact['source']}")
    print(f"  {fact['content'][:200]}")
    print()
```

## Step 4 — Build a custom RAG workflow

For a standalone RAG pipeline that fetches PDF context before calling any LLM:

```python
import httpx
import os

BASE_URL     = "https://autobot.example.com:8443/api"
TOKEN        = "your-jwt-token"
OLLAMA_URL   = os.getenv("AUTOBOT_OLLAMA_ENDPOINT", "http://localhost:11434")
MODEL        = "llama3:8b"

client = httpx.Client(
    base_url=BASE_URL,
    headers={"Authorization": f"Bearer {TOKEN}"},
    verify=False,
)


def rag_query(question: str, top_k: int = 5) -> str:
    """Retrieve PDF context and generate a response using the LLM."""
    # 1. Retrieve relevant passages from the PDF knowledge base
    search = client.post("/knowledge_search/rag_search", json={
        "query":           question,
        "top_k":           top_k,
        "score_threshold": 0.3,
    }).json()

    # 2. Build context string from retrieved passages
    context_parts = []
    for i, fact in enumerate(search.get("results", []), 1):
        context_parts.append(f"{i}. {fact['content']}")
    context = "\n".join(context_parts)

    # 3. Assemble prompt with context
    prompt = f"""You are a helpful assistant. Use the following context to answer the question.
If the context does not contain the answer, say so.

CONTEXT:
{context}

QUESTION: {question}

ANSWER:"""

    # 4. Generate response via Ollama
    ollama = httpx.Client(base_url=OLLAMA_URL)
    resp = ollama.post("/api/generate", json={
        "model":  MODEL,
        "prompt": prompt,
        "stream": False,
    }).json()

    return resp["response"]


# Example
answer = rag_query("How do I configure Ollama for GPU acceleration?")
print(answer)
```

## Knowledge base management endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /knowledge_base/upload` | POST | Upload a PDF or other document |
| `POST /knowledge_base/add_text` | POST | Add a plain-text fact |
| `POST /knowledge_base/url` | POST | Ingest content from a URL |
| `GET /knowledge_base/entries` | GET | List all knowledge entries (paginated) |
| `GET /knowledge_base/stats` | GET | KB statistics (document count, vector count) |
| `GET /knowledge_base/health` | GET | ChromaDB + embedding model health check |
| `POST /knowledge_search/rag_search` | POST | Advanced RAG search with hybrid ranking |
| `POST /knowledge_search/enhanced_search` | POST | RAG-powered search |

## ChromaDB storage

PDFs are chunked and stored in the `knowledge_vectors` ChromaDB collection.  Each chunk carries metadata:

```json
{
  "document_id":  "fact-uuid",
  "chunk_index":   0,
  "document_type": "file",
  "source":        "api-reference.pdf",
  "title":         "API Reference",
  "category":      "uploads"
}
```

Embeddings are generated by the model configured in `AUTOBOT_EMBEDDING_MODEL` (default: `nomic-embed-text:latest`).

## Architecture reference

- **PDF extraction** — `autobot-backend/api/knowledge.py` (`_extract_pdf_content`, uses `pypdf`)
- **Upload endpoint** — `autobot-backend/api/knowledge.py` (`POST /knowledge_base/upload`)
- **RAG service** — `autobot-backend/services/rag_service.py` (`RAGService.advanced_search`)
- **Chat integration** — `autobot-backend/services/knowledge/service.py` (`conversation_aware_retrieve`)
- **ChromaDB loader** — `autobot-backend/knowledge/pipeline/loaders/chromadb_loader.py`
- **Search endpoints** — `autobot-backend/api/knowledge_search.py`
