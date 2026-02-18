# autobot-ollama Infrastructure

> Role: `autobot-ollama` | Node: Backend (.20 / 172.16.168.20) | Ansible role: `llm`

---

## Overview

Ollama local LLM runtime. Runs on the same node as `autobot-backend`, providing on-device model inference via loopback. The main backend accesses it at `http://127.0.0.1:11434`.

Colocates safely with `autobot-backend` — different ports, different users (`ollama` vs `autobot-backend`).

---

## Ports

| Port | Protocol | Public | Purpose |
|------|----------|--------|---------|
| 11434 | HTTP | No (loopback only) | Ollama API |

---

## Services

| Unit | Type | Start Order |
|------|------|-------------|
| `ollama` | systemd | 1 (system service, user: ollama) |

---

## Health Check

```bash
ssh autobot@172.16.168.20 'curl -s http://localhost:11434/api/tags | jq .models[].name'
# Expected: list of loaded model names
```

---

## Secrets

None — loopback only, no auth required.

---

## Deployment

```bash
# Deploy Ollama
ansible-playbook playbooks/deploy-full.yml --tags llm --limit backend_node

# Pull a model (after deploy)
ssh autobot@172.16.168.20 'ollama pull llama3.2'

# Restart Ollama service
ansible-playbook playbooks/slm-service-control.yml \
  -e "service=ollama action=restart"
```

---

## Model Management

```bash
# List loaded models
ssh autobot@172.16.168.20 'ollama list'

# Pull new model
ssh autobot@172.16.168.20 'ollama pull mistral'

# Remove model
ssh autobot@172.16.168.20 'ollama rm mistral'
```

Models are stored in `/usr/share/ollama/.ollama/models/` (Ollama's default). Large models (7B+) require 8GB+ RAM.

---

## Known Gotchas

- **Install method**: Ollama is installed via the official install script (`curl -fsSL https://ollama.ai/install.sh | sh`), not apt. The `llm` Ansible role handles this with idempotency checks.
- **Runs as `ollama` user**: The Ollama service account is created by the install script. Not `autobot-backend`.
- **No TLS**: Loopback only — no TLS needed. Backend reaches it via `http://127.0.0.1:11434`.
- **Model pull during deploy**: Models are NOT auto-pulled by Ansible. Pull manually or add a pull task after deployment.
- **VRAM vs RAM**: Ollama detects GPU and uses it if available. On CPU-only backend node (.20), runs on RAM.

---

## Ansible Role

Role: `llm` in `autobot-slm-backend/ansible/roles/llm/`

Key tasks:
- Check if Ollama binary exists (idempotent)
- Run install script if missing
- Enable + start `ollama.service`
- Optionally pull configured models
