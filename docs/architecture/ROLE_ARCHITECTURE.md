# AutoBot Role Architecture

> **Status:** Active — implemented in Phase 1-2 of [#926](https://github.com/mrveiss/AutoBot-AI/issues/926)
> **Single source of truth:** `autobot-infrastructure/autobot-<role>/manifest.yml`

---

## Overview

Every AutoBot component is a **role**. A role is:

- A top-level repository directory `autobot-<role>/` containing code only
- A corresponding `autobot-infrastructure/autobot-<role>/` directory containing the Ansible role, systemd templates, nginx configs, secrets vault, and `manifest.yml`
- A unique Linux service account on its target node
- A set of declared ports, health endpoints, and coexistence rules

The `manifest.yml` in each infrastructure directory is the **single source of truth** — SLM reads it for deployment, health checking, conflict detection, secret management, and service lifecycle.

---

## Role Catalogue

| Role | Directory | Target Node | IP |
|------|-----------|-------------|-----|
| `autobot-backend` | `autobot-backend/` | backend (.20) | 172.16.168.20 |
| `autobot-frontend` | `autobot-frontend/` | frontend (.21) | 172.16.168.21 |
| `autobot-ollama` | `autobot-ollama/` | backend (.20) | 172.16.168.20 |
| `autobot-slm-backend` | `autobot-slm-backend/` | slm (.19) | 172.16.168.19 |
| `autobot-slm-frontend` | `autobot-slm-frontend/` | slm (.19) | 172.16.168.19 |
| `autobot-slm-database` | `autobot-slm-database/` | slm (.19) | 172.16.168.19 |
| `autobot-monitoring` | `autobot-monitoring/` | slm (.19) | 172.16.168.19 |
| `autobot-npu-worker` | `autobot-npu-worker/` | npu (.22) | 172.16.168.22 |
| `autobot-browser-worker` | `autobot-browser-worker/` | browser (.25) | 172.16.168.25 |
| `autobot-ai-stack` | `autobot-ai-stack/` | ai-stack (.24) | 172.16.168.24 |
| `autobot-database` | `autobot-database/` | database (.23) | 172.16.168.23 |
| `autobot-slm-agent` | `autobot-slm-agent/` | **all nodes** | all |
| `autobot-shared` | `autobot-shared/` | all backend nodes | all |

---

## Node Assignments

Each node gets **only** its assigned role directories + `autobot-shared/` + `autobot-infrastructure/autobot-<its-roles>/`.

| Node | IP | Roles |
|------|----|-------|
| SLM (.19) | 172.16.168.19 | slm-backend + slm-frontend + slm-database + monitoring + slm-agent |
| Backend (.20) | 172.16.168.20 | backend + ollama + slm-agent |
| Frontend (.21) | 172.16.168.21 | frontend + slm-agent |
| NPU (.22) | 172.16.168.22 | npu-worker + slm-agent |
| Database (.23) | 172.16.168.23 | database + slm-agent |
| AI Stack (.24) | 172.16.168.24 | ai-stack + slm-agent |
| Browser (.25) | 172.16.168.25 | browser-worker + slm-agent |
| Reserved (.26) | 172.16.168.26 | slm-agent |
| Reserved (.27) | 172.16.168.27 | slm-agent |

Expected `/opt/autobot/` content on each node:

```
/opt/autobot/
├── autobot-<role>/          # Role code (only that node's roles)
├── autobot-shared/          # Shared Python utilities
├── autobot-infrastructure/  # Ansible + manifests (role-scoped)
│   └── autobot-<role>/
├── cache/                   # SLM code distribution cache (.19 only)
├── data/                    # Runtime data (DB files, logs)
└── .env                     # Role environment variables
```

---

## Repository Structure

```
AutoBot/
├── autobot-backend/          # Core FastAPI backend
├── autobot-frontend/         # Vue 3 user frontend
├── autobot-ollama/           # Ollama local LLM config
├── autobot-slm-backend/      # SLM fleet management API
├── autobot-slm-frontend/     # SLM admin dashboard
├── autobot-slm-database/     # PostgreSQL schema/migrations
├── autobot-monitoring/       # Prometheus/Grafana config
├── autobot-npu-worker/       # Intel NPU inference worker
├── autobot-browser-worker/   # Playwright automation worker
├── autobot-ai-stack/         # ChromaDB + embeddings
├── autobot-database/         # Redis Stack + PostgreSQL config
├── autobot-slm-agent/        # Per-node SLM agent (all nodes)
├── autobot-shared/           # Shared Python utilities
└── autobot-infrastructure/   # Per-role Ansible + manifests
    ├── autobot-backend/
    │   ├── manifest.yml      ← single source of truth
    │   └── README.md
    ├── autobot-frontend/
    │   ├── manifest.yml
    │   └── README.md
    ├── ... (one dir per role)
    └── shared/               # Shared Ansible, certs, scripts
```

---

## manifest.yml Schema

Every role has `autobot-infrastructure/autobot-<role>/manifest.yml`:

```yaml
role: autobot-<name>          # Must start with autobot-
description: "..."
version: "1.0.0"
target_node: <node-name>      # null = all nodes

deploy:
  source: autobot-<name>/     # Repo dir to rsync
  destination: /opt/autobot/autobot-<name>/
  shared: true                # Also deploy autobot-shared/
  infrastructure: true        # Also deploy autobot-infrastructure/<role>/

system_dependencies: [...]    # apt packages

services:
  - name: autobot-<name>      # systemd unit name
    type: systemd|oneshot|timer
    start_order: 1

ports:
  - port: 8443
    protocol: https
    public: false
    loopback_only: false

health:
  endpoint: "https://localhost:8443/api/health"
  interval: "30s"

secrets:
  own: [tls_cert, tls_key]
  shared: [redis_password]

tls:
  auto_rotate: true
  rotate_days_before: 14
  reload_command: "systemctl reload nginx"

system_updates:
  policy: full|security|manual
  reboot_strategy: immediate|scheduled|manual|never

coexistence:
  conflicts_with: []          # Hard block — SLM prevents assignment
  warns_with: []              # Soft warning
  compatible_with: []

depends_on: []                # Roles that must be healthy first
```

---

## Deployment Flow

SLM triggers Ansible directly when a role is assigned or updated:

```
Phase 1 — CLEAN        Remove legacy dirs, remove wrong-node roles
Phase 2 — DEPLOY       rsync role code + shared + infra from cache → node
Phase 3 — SYSTEM DEPS  apt install from manifest.system_dependencies
Phase 4 — SECRETS      Render .env.j2 → /etc/autobot/autobot-<role>.env (640)
Phase 5 — SERVICES     Install systemd units, start in manifest.start_order
Phase 6 — VERIFY       Poll health endpoint, report UP_TO_DATE to SLM
```

Updates (code sync) run phases 2, 4, 5, 6 only — clean and system deps are skipped.

---

## Code Sync Flow

```
git push (dev machine)
  ↓ post-commit hook detects changed role dirs (git diff)
  ↓ rsync changed roles → /opt/autobot/cache/<role>/ on .19
  ↓ POST /api/code-source/notify (changed_roles + commit hash)
  ↓ SLM marks affected nodes OUTDATED
  ↓ Operator triggers update (or auto)
  ↓ Ansible update-node.yml deploys from cache → node (scoped)
  ↓ Node agent reports UP_TO_DATE with commit hash
```

Each role on each node tracks its own commit hash independently in `node_code_versions` DB table.

---

## Security Model

**Per-role service accounts** — each role runs as `autobot-<role>` Linux user. A compromised role process cannot read another role's secrets.

**Environment files** — `/etc/autobot/autobot-<role>.env`, mode 640, owned `root:autobot-<role>`.

**TLS everywhere** — internal CA on SLM. Per-node certs signed at provision. Auto-rotation 14 days before expiry via zero-downtime `systemctl reload`.

**Service auth** — inter-service HTTP calls authenticated via `SERVICE_AUTH_TOKEN` (per-role scoped).

**Firewall** — UFW rules generated from manifest `depends_on` + `ports`. Loopback-only ports get `deny` on external interfaces.

---

## Related Documents

- [COEXISTENCE_MATRIX.md](COEXISTENCE_MATRIX.md) — which roles can share a node
- [NETWORK_TOPOLOGY.md](NETWORK_TOPOLOGY.md) — port map and firewall rules
- [UPDATE_FLOWS.md](UPDATE_FLOWS.md) — code sync and system update flows
- `autobot-infrastructure/autobot-<role>/manifest.yml` — authoritative per-role spec
- `autobot-infrastructure/autobot-<role>/README.md` — deploy notes and gotchas
