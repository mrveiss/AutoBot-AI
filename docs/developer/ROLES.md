# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss

# AutoBot Fleet Role Registry

> **Source of truth** for SLM role definitions.
> Update this document when adding, removing, or changing roles.
> Role definitions in `autobot-slm-backend/services/role_registry.py` must match this document.

---

## Role Concepts

**SLM roles** and **Ansible roles** are not the same thing:

- **Ansible role** — a deployment unit that installs and configures a service on a host
- **SLM role** — a logical fleet role tracked in the SLM registry, representing a service or group of services a node is responsible for

A single SLM role may be deployed by one or more Ansible roles. A node may run multiple SLM roles (e.g. `.19` runs `slm-backend`, `slm-frontend`, `slm-database`, `slm-monitoring` by default).

**Required vs optional:**

- `required: true` — fleet health is **critical** if no node has this role active
- `required: false` — fleet health is **degraded** if no node has this role active, but the system can still function

**Python dependencies** (LlamaIndex, LangChain, etc.) that are installed via pip into a service's venv are **not** separate SLM roles. They are tracked as dependencies of the role that uses them.

**nginx** runs on most nodes as a reverse proxy. It is infrastructure-level and not a separate SLM role.

---

## Role Conflicts

The following pairs of roles **cannot run on the same node** due to port collisions or hardware exclusivity.

### Port Conflicts

| Role A | Role B | Conflicting port | Reason |
|--------|--------|-----------------|--------|
| `slm-backend` | `chromadb` | 8000 | Both bind :8000 (uvicorn / ChromaDB HTTP) |
| `slm-monitoring` | `browser-service` | 3000 | Both bind :3000 (Grafana / Node.js Express) |
| `autobot-llm-cpu` | `autobot-llm-gpu` | 11434 | Both are Ollama — only one instance per node |
| `slm-database` | `redis` | 5432 | Both run PostgreSQL — only one pg cluster per node |

### Hardware Exclusivity

| Role | Constraint |
|------|-----------|
| `autobot-llm-gpu` | Requires NVIDIA GPU. Cannot share GPU VRAM with `npu-worker` on the same node without careful resource partitioning — avoid co-locating. |
| `npu-worker` | Requires Intel NPU or NVIDIA GPU. Do not co-locate with `autobot-llm-gpu` unless hardware has sufficient separate VRAM/NPU units. |

### Implied Node Assignments

These conflicts drive the default fleet layout:

- `.19` — SLM stack only (`slm-backend`, `slm-frontend`, `slm-database`, `slm-monitoring`) — no user-facing services
- `.20` — Backend only (`backend`, `celery`, `autobot-llm-gpu`) — no SLM components
- `.23` — Databases only (`redis`, postgresql) — no application services
- `.24` — AI stack only (`ai-stack`, `chromadb`) — no SLM monitoring (Grafana port conflict)
- `.25` — Browser only (`browser-service`) — no SLM monitoring (Grafana port conflict)

---

## Role Definitions

---

### `slm-backend`

| Field | Value |
|-------|-------|
| **Description** | SLM Manager FastAPI backend — orchestrates fleet, runs Ansible playbooks, WebSocket node heartbeats |
| **Default node** | `.19` (separable) |
| **Required** | yes |
| **Systemd service** | `autobot-slm-backend` |
| **Internal port** | 8000 (uvicorn HTTP, localhost) |
| **External port** | 443 (nginx HTTPS reverse proxy) |
| **Install dir** | `/opt/autobot/autobot-slm-backend` |
| **Python** | 3.10 (venv at `{install_dir}/venv`) |
| **Node.js** | 20.x (required for Ansible tasks and build) |
| **System packages** | `python3 python3-pip python3-venv nginx openssl ansible build-essential curl gnupg ca-certificates` |
| **External deps** | PostgreSQL :5432, Redis :6379 |
| **Ansible playbook** | `deploy-slm-manager.yml` |
| **Source path** | `autobot-slm-backend/` |
| **Key Python packages** | FastAPI, Uvicorn, SQLAlchemy, asyncpg, psycopg2-binary, pydantic, websockets, ansible-runner, prometheus-client, httpx, paramiko, croniter, authlib |
| **Notes** | Admin password auto-generated → `/etc/autobot/slm-secrets.env`. Ansible control node for fleet. |

---

### `slm-frontend`

| Field | Value |
|-------|-------|
| **Description** | SLM Manager Vue 3 admin UI — fleet dashboard, role management, node orchestration |
| **Default node** | `.19` (separable) |
| **Required** | yes |
| **Systemd service** | `nginx` (serves built dist/) |
| **Internal port** | — |
| **External port** | 443 (same nginx instance as slm-backend on .19) |
| **Install dir** | `/opt/autobot/autobot-slm-frontend` |
| **Python** | — |
| **Node.js** | 20.x |
| **System packages** | `nodejs nginx` |
| **External deps** | SLM backend :8000 |
| **Ansible playbook** | `deploy-slm-manager.yml` |
| **Source path** | `autobot-slm-frontend/` |
| **Build command** | `npm install && npm run build` |
| **Notes** | 30 pages, 15 composables, 66 components. Production build only — never `npm run dev` on nodes. |

---

### `slm-database`

| Field | Value |
|-------|-------|
| **Description** | PostgreSQL database for SLM Manager — stores nodes, roles, sessions, audit logs |
| **Default node** | `.19` (separable) |
| **Required** | yes |
| **Systemd service** | `postgresql` |
| **Port** | 5432 (localhost only) |
| **Install dir** | `/var/lib/postgresql/16/main` |
| **Python** | — |
| **Node.js** | — |
| **System packages** | `postgresql-16 postgresql-client-16` |
| **External deps** | — |
| **Ansible playbook** | `playbooks/deploy_role.yml` |
| **Source path** | — (package install, no code sync) |
| **Databases** | `slm`, `slm_users`, `autobot_users` |
| **Credentials** | `/etc/autobot/db-credentials.env` (prefix: `SLM_DB_`) |
| **Notes** | Tuned for 4GB VM: shared_buffers=256MB, effective_cache_size=1GB. Credentials auto-generated on first deploy. |

---

### `slm-monitoring`

| Field | Value |
|-------|-------|
| **Description** | Prometheus + Grafana monitoring stack for the SLM fleet |
| **Default node** | `.19` (separable) |
| **Required** | no |
| **Systemd services** | `prometheus`, `grafana-server` |
| **Ports** | Prometheus: 9090, Grafana: 3000 (both proxied via nginx) |
| **Install dirs** | Prometheus: `/opt/prometheus`, Grafana: `/var/lib/grafana` |
| **Python** | — |
| **Node.js** | — |
| **System packages** | prometheus (binary install), grafana (binary install) |
| **External deps** | node_exporter on all nodes :9100, redis_exporter :9121, SLM `/api/metrics` |
| **Ansible playbook** | `deploy-monitoring.yml` |
| **Source path** | — (binary install, no code sync) |
| **Scrape interval** | 15 seconds |
| **Retention** | 15 days or 10GB |
| **Notes** | Grafana embedded in SLM frontend via iframe. Anonymous access allowed. Hardware-specific collectors (IPMI, NVMe, SMART, Mellanox) installed conditionally based on detected hardware (see #1147). |

---

### `backend`

| Field | Value |
|-------|-------|
| **Description** | Main AutoBot FastAPI backend — AI agent execution, knowledge management, chat, file processing |
| **Default node** | `.20` |
| **Required** | yes |
| **Systemd services** | `autobot-backend`, `autobot-celery`, `nginx` |
| **Internal port** | 8001 (uvicorn HTTP, localhost only) |
| **External port** | 8443 (nginx HTTPS reverse proxy) |
| **Install dir** | `/opt/autobot/autobot-backend` |
| **Python** | 3.12 (conda env: `/home/autobot/miniconda3/envs/autobot-backend`) |
| **Node.js** | — |
| **System packages** | `build-essential libssl-dev ffmpeg libsndfile1 libsndfile1-dev portaudio19-dev tesseract-ocr libtesseract-dev nginx` |
| **External deps** | Redis :6379, PostgreSQL :5432, Ollama :11434, ChromaDB :8000 |
| **Ansible playbook** | `deploy-backend.yml` |
| **Source path** | `autobot-backend/` |
| **Post-sync** | `pip install -r requirements.txt && alembic upgrade head` |
| **Key Python packages** | FastAPI, Uvicorn, Celery, SQLAlchemy, Alembic, OpenAI, Anthropic, ChromaDB client, sentence-transformers, torch, LangChain 0.3.x, LlamaIndex 0.10.x |
| **Notes** | Takes ~6min to init after restart. WSL2: Windows Firewall may block 8443 after restart. GPU: NVIDIA RTX 4070 Laptop (8GB VRAM, CUDA 12). |

---

### `celery`

| Field | Value |
|-------|-------|
| **Description** | Async task worker for backend — Ansible playbook execution, knowledge processing, system tasks |
| **Default node** | `.20` (separable) |
| **Required** | yes |
| **Systemd service** | `autobot-celery` |
| **Port** | — (no HTTP; uses Redis as broker) |
| **Install dir** | Shares `/opt/autobot/autobot-backend` venv with `backend` |
| **Python** | 3.12 (shared conda env with `backend`) |
| **Node.js** | — |
| **System packages** | — (shared with `backend`) |
| **External deps** | Redis :6379 (broker + result backend), PostgreSQL :5432 |
| **Ansible playbook** | `deploy-backend.yml` (deployed alongside backend) |
| **Source path** | `autobot-backend/` (same source as backend) |
| **Redis databases** | broker: db 1, result backend: db 2 |
| **Notes** | Shares venv with `backend`. Can be separated to dedicated worker node if `.20` becomes overloaded. |

---

### `frontend`

| Field | Value |
|-------|-------|
| **Description** | Main AutoBot Vue 3 user interface |
| **Default node** | `.21` |
| **Required** | yes |
| **Systemd service** | `nginx` (serves built dist/) |
| **Internal port** | — |
| **External port** | 443 (nginx HTTPS) |
| **Install dir** | `/opt/autobot/autobot-frontend` |
| **Python** | — |
| **Node.js** | 20.x |
| **System packages** | `nodejs nginx build-essential curl gnupg ca-certificates` |
| **External deps** | Backend API :8443 |
| **Ansible playbook** | `deploy-frontend.yml` |
| **Source path** | `autobot-frontend/` |
| **Build command** | `npm install && npm run build` |
| **Notes** | dist/ may be root-owned after Ansible deploy — fix: `sudo chown -R autobot:autobot /opt/autobot/autobot-frontend/`. Never `npm run dev` on production nodes. |

---

### `npu-worker`

| Field | Value |
|-------|-------|
| **Description** | Intel NPU/GPU inference worker using OpenVINO — hardware-accelerated model inference |
| **Default node** | Optional dedicated node with NPU/GPU hardware |
| **Required** | no |
| **Systemd service** | `autobot-npu-worker` |
| **Port** | 8081 (FastAPI, proxied via nginx) |
| **Install dir** | `/opt/autobot/autobot-npu-worker` |
| **Python** | 3.10 (venv) |
| **Node.js** | — |
| **System packages** | `python3 python3-pip python3-venv libopenblas-dev libblas-dev liblapack-dev` |
| **External deps** | — |
| **Ansible playbook** | `setup-npu-worker.yml` |
| **Source path** | `autobot-npu-worker/` |
| **Post-sync** | `pip install -r requirements.txt` |
| **Key Python packages** | FastAPI, Uvicorn, openvino>=2024.0, openvino-dev, numpy, pillow, transformers, optimum[openvino] |
| **Special hardware** | Intel NPU device (optional, falls back to CPU) |
| **Degraded without** | GPU inference offloading — backend falls back to local Ollama |

---

### `tts-worker`

| Field | Value |
|-------|-------|
| **Description** | Text-to-speech synthesis worker using Pocket TTS |
| **Default node** | Portable — can co-locate with frontend or any available node |
| **Required** | no |
| **Systemd service** | `autobot-tts-worker` |
| **Port** | 8082 (FastAPI, proxied via nginx) |
| **Install dir** | `/opt/autobot/autobot-tts-worker` |
| **Python** | 3.10 (venv) |
| **Node.js** | — |
| **System packages** | `python3 python3-pip python3-venv libsndfile1` |
| **External deps** | Redis :6379 (optional, for task queue) |
| **Ansible playbook** | `playbooks/deploy_role.yml` |
| **Source path** | `autobot-tts-worker/` |
| **Post-sync** | `pip install -r requirements.txt` |
| **Key Python packages** | FastAPI, Uvicorn, torch>=2.5 (CPU only, from PyTorch index), pocket-tts, soundfile, numpy, scipy |
| **Models dir** | `/var/lib/autobot/models/tts` |
| **Voices dir** | `/var/lib/autobot/voices` |
| **Degraded without** | Voice synthesis — TTS features unavailable |
| **Notes** | PyTorch CPU-only. Can run on same node as `frontend` or any low-traffic node. |

---

### `browser-service`

| Field | Value |
|-------|-------|
| **Description** | Playwright browser automation worker — web scraping, visual browser, MCP automation |
| **Default node** | `.25` |
| **Required** | no |
| **Systemd services** | `autobot-playwright`, `autobot-vnc` (optional headed mode) |
| **Port** | 3000 (Node.js Express, proxied via nginx) |
| **VNC port** | 5901 (optional) |
| **Install dir** | `/opt/autobot/autobot-browser-worker` |
| **Python** | 3.10 (venv, optional) |
| **Node.js** | Latest |
| **System packages** | `nodejs xfce4 xfce4-goodies tightvncserver dbus-x11 xvfb libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libgbm1 libasound2` |
| **External deps** | — |
| **Ansible playbook** | `setup-browser-worker.yml` |
| **Source path** | `autobot-browser-worker/` |
| **Post-sync** | `npm install` |
| **Key packages** | playwright, playwright-stealth, express |
| **Browsers** | Chromium, Firefox |
| **Degraded without** | Browser automation tasks — features degrade gracefully |
| **Notes** | Two playwright services may coexist (`autobot-playwright` headless, `browser-playwright` headed). Only one should run at a time. |

---

### `ai-stack`

| Field | Value |
|-------|-------|
| **Description** | AI processing API — LLM routing, RAG, multi-modal processing, LangChain/LlamaIndex orchestration |
| **Default node** | `.24` (separable) |
| **Required** | yes |
| **Systemd service** | `autobot-ai-stack` |
| **Port** | 8080 (FastAPI, proxied via nginx) |
| **Install dir** | `/opt/autobot/autobot-ai-stack` |
| **Python** | 3.10 (venv) |
| **Node.js** | — |
| **System packages** | `python3 python3-pip python3-venv build-essential` |
| **External deps** | Redis :6379, Ollama :11434 (resolved from inventory, not hardcoded) |
| **Ansible playbook** | `setup-ai-stack.yml` |
| **Source path** | `autobot-ai-stack/` |
| **Post-sync** | `pip install -r requirements.txt` |
| **Key Python packages** | FastAPI, Uvicorn, LangChain 0.3.x, LangChain-Community, LangChain-Ollama, LlamaIndex 0.10.x, transformers, sentence-transformers, torch, openai, anthropic, redis, httpx |
| **Notes** | LangChain and LlamaIndex are Python dependencies in this venv — not separate roles. Ollama host resolved from SSOT config, never hardcoded. |

---

### `chromadb`

| Field | Value |
|-------|-------|
| **Description** | ChromaDB vector database — stores and queries embeddings for RAG and knowledge search |
| **Default node** | `.24` (portable — can co-locate with Redis on `.23` or backend on `.20`) |
| **Required** | yes |
| **Systemd service** | `autobot-chromadb` |
| **Port** | 8000 (localhost only) |
| **Install dir** | `/opt/autobot/autobot-ai-stack` (shared venv with `ai-stack`) |
| **Python** | 3.10 (shared venv with `ai-stack`) |
| **Node.js** | — |
| **System packages** | — (shared with `ai-stack`) |
| **External deps** | — (local SQLite + parquet persistence) |
| **Ansible playbook** | `setup-ai-stack.yml` (deployed alongside ai-stack) |
| **Source path** | — (pip package, no code sync) |
| **Persistence dir** | `/var/lib/autobot/chromadb` |
| **Notes** | No GPU benefit — CPU-based HNSW indexing. Can be separated to its own node if ai-stack and chromadb need independent scaling. |

---

### `autobot-llm-cpu`

| Field | Value |
|-------|-------|
| **Description** | Ollama LLM inference — CPU-only node for lightweight models (≤3B parameters) |
| **Default node** | `.26` |
| **Required** | no |
| **Systemd service** | `ollama` |
| **Port** | 11434 (localhost only) |
| **Install dir** | `/usr/local/bin/ollama` (binary), `/var/lib/ollama` (models) |
| **Python** | — |
| **Node.js** | — |
| **System packages** | `curl ca-certificates` (for installer script) |
| **External deps** | — |
| **Ansible playbook** | `playbooks/deploy_role.yml` |
| **Source path** | — (binary install from ollama.ai) |
| **CPU models** | nomic-embed-text, llama3.2:1b, llama3.2:3b, llama3.2:latest, gemma2:2b |
| **Concurrency** | max_loaded=2, num_parallel=2, keep_alive=5m |
| **Degraded without** | Local CPU inference — system falls back to cloud providers (OpenAI, Anthropic, Mistral) |
| **Notes** | Cloud providers (OpenAI, Anthropic, Mistral) are alternative LLM backends — local LLM nodes are optional if cloud is configured. |

---

### `autobot-llm-gpu`

| Field | Value |
|-------|-------|
| **Description** | Ollama LLM inference — GPU-accelerated node for large models (7B+ parameters) |
| **Default node** | `.20` (runs alongside `backend`) |
| **Required** | no |
| **Systemd service** | `ollama` |
| **Port** | 11434 (localhost only) |
| **Install dir** | `/usr/local/bin/ollama` (binary), `/var/lib/ollama` (models) |
| **Python** | — |
| **Node.js** | — |
| **System packages** | `curl ca-certificates nvidia-driver` (GPU drivers) |
| **External deps** | — |
| **Ansible playbook** | `playbooks/deploy_role.yml` |
| **Source path** | — (binary install from ollama.ai) |
| **GPU models** | mistral:7b-instruct, deepseek-r1:14b, codellama:13b |
| **Concurrency** | max_loaded=5, num_parallel=4, keep_alive=10m |
| **Special hardware** | NVIDIA GPU required. Auto-detected via nvidia-smi. |
| **Degraded without** | Large model inference — system falls back to CPU models or cloud providers |

---

### `redis`

| Field | Value |
|-------|-------|
| **Description** | Redis Stack + PostgreSQL database node — primary cache, Celery broker, pub/sub, vector search, time series, and backend user management DB |
| **Default node** | `.23` |
| **Required** | yes |
| **Systemd services** | `redis-stack-server`, `redis_exporter`, `postgresql` |
| **Redis port** | 6379 (plain), 6380 (TLS optional) |
| **Redis exporter port** | 9121 (Prometheus metrics) |
| **PostgreSQL port** | 5432 (internal subnet only) |
| **Install dirs** | Redis: `/var/lib/redis-stack`, PostgreSQL: `/var/lib/postgresql/16/main` |
| **Python** | — |
| **Node.js** | — |
| **System packages** | `redis-stack-server redis-tools postgresql-16 postgresql-client-16` |
| **External deps** | — |
| **Ansible playbooks** | Redis: `setup-redis-stack.yml`, PostgreSQL: `playbooks/deploy_role.yml` |
| **Source path** | — (package install, no code sync) |
| **Redis max memory** | 6GB, `allkeys-lru` eviction |
| **Persistence** | RDB snapshots + AOF enabled |
| **TLS** | Configurable via `AUTOBOT_REDIS_TLS_ENABLED` |
| **Redis database IDs** | 0=main+RediSearch, 1=metrics, 2=prompts, 3=agents, 4=cache, 6=sessions, 8=chat_history, 15=testing |
| **Celery databases** | broker=db1, result_backend=db2 (from `celery_app.py`) |
| **PostgreSQL databases** | `autobot` (backend user management — only when `AUTOBOT_DEPLOYMENT_MODE != single_user`) |
| **PostgreSQL credentials** | `/etc/autobot/db-credentials.env` (prefix: `AUTOBOT_DB_`) |
| **Notes** | Always use `from autobot_shared.redis_client import get_redis_client` — never direct connection. PostgreSQL co-hosted here for backend user management; not needed in `single_user` deployment mode. |

---

### `autobot-shared`

| Field | Value |
|-------|-------|
| **Description** | Shared Python library — Redis client, SSOT config, utilities used by all Python services |
| **Default node** | All nodes running Python services |
| **Required** | yes |
| **Systemd service** | — (library, no service) |
| **Port** | — |
| **Install dir** | `/opt/autobot/autobot-shared` |
| **Python** | 3.10 / 3.12 (editable install into each service's venv) |
| **Node.js** | — |
| **System packages** | `python3 python3-venv` |
| **External deps** | — |
| **Ansible playbook** | `deploy-shared.yml` |
| **Source path** | `autobot-shared/` |
| **Post-sync** | `pip install -e .` |
| **Notes** | Must be deployed before any other Python service. Provides `get_redis_client()`, `ssot_config`, and shared utilities. |

---

### `slm-agent`

| Field | Value |
|-------|-------|
| **Description** | Per-node agent — heartbeat to SLM manager, task polling, service monitoring, Prometheus metrics export |
| **Default node** | All managed nodes |
| **Required** | yes |
| **Systemd services** | `slm-agent`, `prometheus-node-exporter`, hardware collectors (conditional) |
| **Port** | — (outbound only to SLM backend HTTPS) |
| **Node exporter port** | 9100 (scraped by Prometheus on `.19`) |
| **Install dir** | `/opt/autobot/autobot-slm-agent` |
| **Python** | 3.10 (venv) |
| **Node.js** | — |
| **System packages** | `python3 python3-venv prometheus-node-exporter` |
| **External deps** | SLM backend HTTPS (resolved from config, not hardcoded) |
| **Ansible playbook** | `deploy-slm-agent.yml` |
| **Source path** | `autobot-slm-backend/slm/agent/` |
| **Post-sync** | `pip install aiohttp psutil` |
| **Heartbeat interval** | 30 seconds |
| **Hardware collectors** | Installed conditionally based on detected hardware: `prometheus-node-exporter-nvme` (NVMe drives), `prometheus-node-exporter-smartmon` (SMART drives), `prometheus-node-exporter-ipmitool-sensor` (IPMI), `prometheus-node-exporter-mellanox-hca-temp` (Mellanox NICs) |
| **Notes** | Bundles node-exporter — both always co-deployed. Hardware collectors currently failing on .19/.26/.27 (see #1147). |

---

## Fleet Node Summary

| IP | Node ID | Primary Roles | Python | Node.js |
|----|---------|---------------|--------|---------|
| `.19` | `00-SLM-Manager` | slm-backend, slm-frontend, slm-database, slm-monitoring | 3.10 | 20.x |
| `.20` | `01-Backend` | backend, celery, autobot-llm-gpu | 3.12 (conda) | — |
| `.21` | `02-Frontend` | frontend | — | 20.x |
| `.22` | `npu-worker` | npu-worker, tts-worker (current) | 3.10 | — |
| `.23` | `04-Databases` | redis, postgresql (backend user mgmt) | — | — |
| `.24` | `03-AI-Stack` | ai-stack, chromadb | 3.10 | — |
| `.25` | `browser-automation` | browser-service | 3.10 | Latest |
| `.26` | `05-LLM-CPU` | autobot-llm-cpu | — | — |
| `.27` | `06-Node-27` | reserved | — | — |

> `slm-agent` + `prometheus-node-exporter` run on **every node**.
> `autobot-shared` deployed to every node running a Python service.
> `tts-worker` is portable — currently on `.22`, can move to `.21` or any available node.
> `chromadb` is portable — currently on `.24`, can co-locate with Redis on `.23` or backend on `.20`.

---

## Port Reference

| Port | Service | Node(s) | Exposed |
|------|---------|---------|---------|
| 443 | nginx (frontend, slm-frontend, slm-backend) | .19, .21 | external HTTPS |
| 3000 | browser-service (Node.js) | .25 | via nginx |
| 3000 | grafana | .19 | via nginx |
| 5432 | postgresql (SLM databases) | .19 | internal subnet |
| 5432 | postgresql (backend user mgmt) | .23 | internal subnet |
| 5901 | VNC (browser-service, optional) | .25 | optional |
| 6379 | redis (plain) | .23 | internal subnet |
| 6380 | redis (TLS, optional) | .23 | internal subnet |
| 8000 | chromadb | .24 | localhost only |
| 8000 | slm-backend (uvicorn) | .19 | localhost only |
| 8001 | backend (uvicorn) | .20 | localhost only |
| 8080 | ai-stack | .24 | via nginx |
| 8081 | npu-worker | .22 | via nginx |
| 8082 | tts-worker | portable | via nginx |
| 8443 | backend (nginx HTTPS) | .20 | external HTTPS |
| 9090 | prometheus | .19 | via nginx |
| 9100 | node-exporter | all nodes | internal (scraped by Prometheus) |
| 9121 | redis-exporter | .23 | internal (scraped by Prometheus) |
| 11434 | ollama | .20, .26 | localhost only |

---

## Dependency Graph

```
frontend (.21)
  └── backend (.20) :8443
        ├── redis (.23) :6379
        ├── postgresql (.23) :5432  [user mgmt; only when AUTOBOT_DEPLOYMENT_MODE != single_user]
        ├── autobot-llm-gpu :11434
        ├── ai-stack (.24) :8080
        │     ├── chromadb :8000
        │     └── autobot-llm-cpu (.26) :11434
        └── celery
              └── redis (.23) :6379 [broker db1, results db2]

slm-frontend (.19)
  └── slm-backend (.19) :8000
        ├── slm-database (.19) :5432
        └── redis (.23) :6379

slm-agent (all nodes)
  └── slm-backend (.19) :443 [heartbeat]

optional roles:
  npu-worker (.22) :8081
  tts-worker (portable) :8082
  browser-service (.25) :3000
  autobot-llm-cpu (.26) :11434
  autobot-llm-gpu (.20) :11434
```

---

## Architecture Schematics

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           AutoBot Fleet Architecture                            │
└─────────────────────────────────────────────────────────────────────────────────┘

  USERS / BROWSERS
        │ HTTPS :443
        ▼
┌───────────────────┐       ┌───────────────────────────────────────────────────┐
│  .21  FRONTEND    │       │  .19  SLM MANAGER                                 │
│  nginx (dist/)    │       │  slm-backend :8000   slm-frontend (nginx :443)    │
│  autobot-frontend │       │  postgresql :5432    slm-monitoring :9090/:3000   │
│  (Vue 3 SPA)      │       │  (fleet control plane, Ansible executor)          │
└────────┬──────────┘       └────────────────────┬──────────────────────────────┘
         │ API :8443                              │ WS :443 heartbeat
         ▼                                        ▼ (all nodes)
┌───────────────────┐       ┌───────────────────────────────────────────────────┐
│  .20  BACKEND     │       │  slm-agent + node-exporter  (every node)          │
│  uvicorn :8001    │       └───────────────────────────────────────────────────┘
│  nginx :8443      │
│  celery workers   │       ┌─────────────────────────────────────────────────┐
│  ollama :11434    │       │  .23  DATABASES                                  │
│  (Python 3.12     │──────▶│  Redis Stack :6379   redis_exporter :9121        │
│   conda env)      │       │  PostgreSQL :5432    (backend user mgmt)          │
└───────────────────┘       └─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│  .24  AI STACK                                                                  │
│  autobot-ai-stack :8080   (LangChain, LlamaIndex, RAG orchestration)           │
│  autobot-chromadb :8000   (vector DB, local SQLite+parquet persistence)         │
└──────────────────────────────────────────┬──────────────────────────────────────┘
                                           │ Ollama :11434
                                           ▼
┌──────────────────┐    ┌──────────────────┐    ┌────────────────────────────────┐
│  .26  LLM-CPU    │    │  .22  NPU/TTS    │    │  .25  BROWSER                  │
│  ollama :11434   │    │  npu-worker:8081 │    │  autobot-playwright :3000      │
│  CPU models      │    │  tts-worker:8082 │    │  Chromium/Firefox headless     │
│  ≤3B params      │    │  (optional GPU)  │    │  VNC :5901 (optional)          │
└──────────────────┘    └──────────────────┘    └────────────────────────────────┘

  ─── Required service boundary     ···  Optional / degraded-without
  ══  External HTTPS                 ──  Internal subnet 172.16.168.0/24
```

---

## Database Setup Reference (Blank Machine)

When provisioning AutoBot from scratch, the following databases must be initialised
before services start. Ansible handles creation automatically via the `postgresql`
Ansible role, but this section documents what gets created where.

### PostgreSQL on `.19` — SLM Manager

Provisioned by: `deploy-slm-manager.yml` (includes `postgresql` Ansible role)

| Database | Owner | Purpose |
|----------|-------|---------|
| `slm` | `slm_app` | SLM Manager primary data (nodes, roles, sessions, audit log) |
| `slm_users` | `slm_app` | SLM user accounts |
| `autobot_users` | `slm_app` | Shared user accounts (future cross-service) |

Schema applied by: `alembic upgrade head` inside the SLM backend venv
Credentials file: `/etc/autobot/db-credentials.env` (prefix `SLM_DB_`)

### PostgreSQL on `.23` — Backend User Management

Provisioned by: `playbooks/deploy_role.yml` (postgresql role)

| Database | Owner | Purpose |
|----------|-------|---------|
| `autobot` | `autobot` | Backend user management (users, teams, orgs, API keys, audit) |

**Only active when** `AUTOBOT_DEPLOYMENT_MODE != single_user`.
Set `AUTOBOT_DEPLOYMENT_MODE=single_company` (or higher) to enable.
Schema applied by: `alembic upgrade head` inside the backend conda env
Credentials file: `/etc/autobot/db-credentials.env` (prefix `AUTOBOT_DB_`)

### SQLite on `.20` — Backend Primary Storage

No setup required — aiosqlite creates the file on first startup.

| File | Purpose |
|------|---------|
| `/var/lib/autobot/autobot.db` | Conversations, knowledge, files, agent state |

### Redis on `.23` — Key Namespace Reference

No schema setup — namespaces are managed by application code.

| DB ID | Name | Used by | Contents |
|-------|------|---------|----------|
| 0 | main + RediSearch | backend, ai-stack | App data, RediSearch/vector indexes (RediSearch requires db 0) |
| 1 | metrics | backend | Performance metrics, monitoring time series |
| 2 | prompts | backend | Prompt templates |
| 3 | agents | backend | Agent coordination, pub/sub |
| 4 | cache | backend | General cache |
| 6 | sessions | backend | User sessions, auth tokens |
| 8 | chat_history | backend | Chat conversation history |
| 15 | testing | test suites | Isolated test data |

Celery (in `celery_app.py`): broker=db1, result_backend=db2

### ChromaDB on `.24` — Vector Persistence

No setup required — ChromaDB creates its own storage on first startup.

| Path | Purpose |
|------|---------|
| `/var/lib/autobot/chromadb` | Embedding collections (SQLite + parquet files) |
