---
tags:
  - operations
  - upgrade
  - chromadb
  - knowledge-base
aliases:
  - ChromaDB 1.x Upgrade Note
---

# ChromaDB 0.5 to 1.x Upgrade — Re-index Requirement

**Introduced by:** PR #9762  
**Affects:** Bare-metal and long-lived-volume deployments only  
**Docker Compose (`single_user`):** Holds no persistent volume data — not affected

---

## What Changed

PR #9762 bumped the ChromaDB server from 0.5.23 to 1.5.9.  
ChromaDB 1.x introduced two breaking changes relative to 0.5.x:

| Change | 0.5.x | 1.x |
|--------|-------|-----|
| Persist path | `/chroma/chroma` | `/data` |
| On-disk format | 0.5 SQLite layout | 1.x SQLite layout (incompatible) |

When the server container is replaced with the 1.x image, the old volume data at
`/chroma/chroma` is not read.  The server starts healthy and the collection API
responds normally, but all previously indexed vectors are absent.  RAG returns no
results and the backend logs a startup warning:

```
WARNING  knowledge.base — Knowledge base collection 'autobot_memory' is empty.
If this deployment previously had indexed data, the ChromaDB 1.x upgrade
(PR #9762) requires re-indexing the knowledge base.
See docs/operations/chromadb-1x-upgrade.md
```

---

## How to Detect

The startup warning above fires automatically on every backend boot when
`autobot_memory` (or the configured collection) reports 0 vectors.

To check manually:

```bash
curl -s http://localhost:8001/api/knowledge_base/stats | python3 -m json.tool
# Look for "total_vectors": 0 or "total_facts": 0
```

---

## Remedy — Re-index the Knowledge Base

Re-indexing re-populates ChromaDB from the source documents already stored in
the AutoBot database (no data is lost from Redis/Postgres).

### Option A — Vectorize all facts (recommended for most deployments)

```bash
curl -X POST http://localhost:8001/api/vectorize_facts \
  -H "Content-Type: application/json" \
  -d '{"batch_size": 100}'
```

Monitor progress:

```bash
curl http://localhost:8001/api/vectorize_facts/status
```

### Option B — Background vectorization (non-blocking)

```bash
curl -X POST http://localhost:8001/api/vectorize_facts/background \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Option C — Contextual reindex (requires `CONTEXT_ENABLED=true`)

```bash
curl -X POST http://localhost:8001/api/reindex_with_context \
  -H "Content-Type: application/json" \
  -d '{"batch_size": 50}'

# Check status
curl http://localhost:8001/api/reindex_with_context/status
```

---

## Scope

| Deployment type | Affected? | Action |
|-----------------|-----------|--------|
| `docker compose up` (default `single_user` profile) | No — no persistent `chroma_data` volume | None |
| Bare-metal / systemd with `chroma_data` volume populated under 0.5.x | Yes | Re-index (see above) |
| Fresh install onto 1.x | No — no prior data | None |

---

## Related

- PR #9762 — ChromaDB 0.5.23 → 1.5.9 bump, compose health-check fixes  
- `autobot-backend/knowledge/base.py` — `_create_chroma_collection` (startup warning source)  
- `docs/features/knowledge-base-maintenance.md` — general KB maintenance procedures
