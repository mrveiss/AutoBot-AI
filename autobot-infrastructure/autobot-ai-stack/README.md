# autobot-ai-stack Infrastructure

> Role: `autobot-ai-stack` | Node: AI Stack VM (.24 / 172.16.168.24) | Ansible role: `ai-stack`

---

## Overview

AI processing stack — ChromaDB vector store, embedding generation, and AI processing pipeline. Provides semantic search and vector storage for the main backend's RAG pipeline.

---

## Ports

| Port | Protocol | Public | Purpose |
|------|----------|--------|---------|
| 8080 | HTTP | No (fleet-internal) | AI Stack API (ChromaDB + embeddings) |

---

## Services

| Unit | Type | Start Order |
|------|------|-------------|
| `autobot-ai-stack` | systemd | 1 |

---

## Health Check

```bash
curl http://172.16.168.24:8080/health | jq
# Expected: {"status": "healthy", "chromadb": {"collections": N}, ...}
```

---

## Secrets

| Secret | File | Description |
|--------|------|-------------|
| `tls_cert` | `/etc/autobot/autobot-ai-stack/tls.crt` | Fleet-internal TLS |
| `tls_key` | `/etc/autobot/autobot-ai-stack/tls.key` | Private key |
| `service_auth_token` | `/etc/autobot/autobot-ai-stack.env` | Inter-service auth |

---

## Deployment

```bash
# Deploy AI stack
ansible-playbook playbooks/deploy-full.yml --tags ai-stack --limit ai_stack_vm

# Restart
ansible-playbook playbooks/slm-service-control.yml \
  -e "service=autobot-ai-stack action=restart"

# Manual sync
./infrastructure/shared/scripts/utilities/sync-to-vm.sh ai-stack autobot-ai-stack/
```

---

## ChromaDB Collections

Default collections initialized at startup:
- `documents` — document knowledge base
- `code` — code vectorization
- `security_findings` — security assessment results
- `knowledge_graph` — ECL pipeline entities

---

## Known Gotchas

- **ChromaDB persistence**: Data stored in `/opt/autobot/data/chromadb/`. Excluded from rsync deploys — never wiped by updates.
- **Memory requirements**: ChromaDB with large collections requires 4GB+ RAM. Monitor with `free -h` on .24.
- **Embedding model**: Downloaded on first run from HuggingFace. Cached in `/opt/autobot/data/model_cache/`.
- **Collection not found errors**: If backend reports empty results, check that the AI stack initialized collections. See `POST /api/ai-stack/collections/initialize`.

---

## Ansible Role

Role: `ai-stack` in `autobot-slm-backend/ansible/roles/ai-stack/`

Key tasks:
- Install Python + ChromaDB + embedding dependencies
- Create data directories (persistent — not wiped on redeploy)
- Systemd unit install + start
