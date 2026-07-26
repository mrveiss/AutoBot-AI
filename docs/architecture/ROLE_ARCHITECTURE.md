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
| `autobot-backend` | `autobot-backend/` | backend (.20) | <backend-ip> |
| `autobot-frontend` | `autobot-frontend/` | frontend (.21) | <frontend-ip> |
| `autobot-ollama` | `autobot-ollama/` | backend (.20) | <backend-ip> |
| `autobot-slm-backend` | `autobot-slm-backend/` | slm (.19) | <slm-manager-ip> |
| `autobot-slm-frontend` | `autobot-slm-frontend/` | slm (.19) | <slm-manager-ip> |
| `autobot-slm-database` | `autobot-slm-database/` | slm (.19) | <slm-manager-ip> |
| `autobot-monitoring` | `autobot-monitoring/` | slm (.19) | <slm-manager-ip> |
| `autobot-npu-worker` | `autobot-npu-worker/` | npu (.22) | <npu-ip> |
| `autobot-browser-worker` | `autobot-browser-worker/` | browser (.25) | <browser-ip> |
| `autobot-ai-stack` | `autobot-ai-stack/` | ai-stack (.24) | <aiml-ip> |
| `autobot-database` | `autobot-database/` | database (.23) | <database-ip> |
| `autobot-slm-agent` | `autobot-slm-backend/slm/agent/`¹ | **all nodes** | all |
| `autobot_shared` | `autobot_shared/` | all backend nodes | all |

¹ Exception to the one-role-one-top-level-dir rule: the agent's code source lives nested under `autobot-slm-backend/slm/agent/` (not a top-level `autobot-slm-agent/` dir) and is deployed by the `slm_agent` Ansible role from a byte-identical mirror at `autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent/`, CI-gated against drift (#1629). See `autobot-infrastructure/autobot-slm-agent/manifest.yml` for the role's infra descriptor.

---

## Node Assignments

Each node gets **only** its assigned role directories + `autobot_shared/` + `autobot-infrastructure/autobot-<its-roles>/`.

| Node | IP | Roles |
|------|----|-------|
| SLM (.19) | <slm-manager-ip> | slm-backend + slm-frontend + slm-database + monitoring + slm-agent |
| Backend (.20) | <backend-ip> | backend + ollama + slm-agent |
| Frontend (.21) | <frontend-ip> | frontend + slm-agent |
| NPU (.22) | <npu-ip> | npu-worker + slm-agent |
| Database (.23) | <database-ip> | database + slm-agent |
| AI Stack (.24) | <aiml-ip> | ai-stack + slm-agent |
| Browser (.25) | <browser-ip> | browser-worker + slm-agent |
| Reserved (.26) | <reserved-ip> | slm-agent |
| Reserved (.27) | <reserved-ip> | slm-agent |

Expected `/opt/autobot/` content on each node:

```
/opt/autobot/
├── autobot-<role>/          # Role code (only that node's roles)
├── autobot_shared/          # Shared Python utilities
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
│   └── slm/agent/            # Per-node SLM agent (all nodes) — see ¹ above
├── autobot-slm-frontend/     # SLM admin dashboard
├── autobot-slm-database/     # PostgreSQL schema/migrations
├── autobot-monitoring/       # Prometheus/Grafana config
├── autobot-npu-worker/       # Intel NPU inference worker
├── autobot-browser-worker/   # Playwright automation worker
├── autobot-ai-stack/         # ChromaDB + embeddings
├── autobot-database/         # Redis Stack + PostgreSQL config
├── autobot_shared/           # Shared Python utilities
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
  shared: true                # Also deploy autobot_shared/
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
