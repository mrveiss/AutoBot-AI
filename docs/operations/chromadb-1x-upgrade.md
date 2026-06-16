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
**Affects:** Any deployment whose ChromaDB data volume was populated under 0.5.x —
including Docker Compose, whose named `chroma_data` volume persists across
`docker compose up` and image upgrades

---

## What Changed

PR #9762 bumped the ChromaDB server from 0.5.23 to 1.5.9.  
ChromaDB 1.x introduced two breaking changes relative to 0.5.x:

| Change | 0.5.x | 1.x |
|--------|-------|-----|
| Persist path | `/chroma/chroma` | `/data` |
| On-disk format | 0.5 SQLite layout | 1.x SQLite layout (incompatible) |

In `docker-compose.yml` the named volume mount moved accordingly:
`chroma_data:/chroma/chroma` (0.5.x) → `chroma_data:/data` (1.x). The volume
itself is unchanged and survives the upgrade — but the 1.x server does not read
the 0.5-format data it contains.

When the server container is replaced with the 1.x image, the old volume data
is not read.  The server starts healthy and the collection API
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
curl -X POST http://localhost:8001/api/knowledge_base/vectorize_facts \
  -H "Content-Type: application/json" \
  -d '{"batch_size": 100}'
```

Monitor progress:

```bash
curl http://localhost:8001/api/knowledge_base/vectorize_facts/status
```

### Option B — Background vectorization (non-blocking)

```bash
curl -X POST http://localhost:8001/api/knowledge_base/vectorize_facts/background \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Option C — Contextual reindex (requires `CONTEXT_ENABLED=true`)

```bash
curl -X POST http://localhost:8001/api/knowledge_base/reindex_with_context \
  -H "Content-Type: application/json" \
  -d '{"batch_size": 50}'

# Check status
curl http://localhost:8001/api/knowledge_base/reindex_with_context/status
```

---

## Scope

| Deployment type | Affected? | Action |
|-----------------|-----------|--------|
| `docker compose up` with a `chroma_data` volume populated under 0.5.x | Yes — named volumes survive image upgrades | Re-index (see above) |
| Bare-metal / systemd with ChromaDB data populated under 0.5.x | Yes | Re-index (see above) |
| Fresh host, or `chroma_data` removed (`docker volume rm` / prune) before first 1.x start | No — no prior data | None |

---

## Related

- PR #9762 — ChromaDB 0.5.23 → 1.5.9 bump, compose health-check fixes  
- `autobot-backend/knowledge/base.py` — `_create_chroma_collection` (startup warning source)  
- `docs/features/knowledge-base-maintenance.md` — general KB maintenance procedures
