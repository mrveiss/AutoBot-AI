---
tags:
  - architecture
  - deployment
  - infrastructure
aliases:
  - VM Roles
  - Distributed Deployment Roles
---

# VM Roles — Distributed Deployment

AutoBot supports two deployment modes. In both modes the same Ansible roles apply;
the difference is whether roles run on separate machines or are co-located.

## Deployment Modes

| Mode | Description | When to use |
| --- | --- | --- |
| **Co-located** | All roles on one machine, services bound to `127.0.0.x` aliases | Development, single-host lab |
| **Distributed** | Each role on a dedicated VM, IPs assigned at install time | Production, multi-VM cluster |

IPs are **never hardcoded**. They are detected by `install.sh` from the network interface
and written to `/etc/autobot/slm-secrets.env` as `NETWORK_SUBNET` / `NETWORK_GATEWAY`.
All Ansible templates reference `infrastructure.hosts.<role>` which resolves at deploy time.

---

## Role Definitions

### SLM Manager (`slm`)

**Purpose:** Control plane — orchestrates all other VMs, hosts the admin UI and monitoring stack.

| Service | Port | Protocol |
| --- | --- | --- |
| SLM Backend API | 8000 | HTTPS |
| SLM Frontend (nginx) | 443 / 80 | HTTPS / HTTP→HTTPS redirect |
| PostgreSQL | 5432 | TCP (internal only) |
| Prometheus | 9090 | HTTP (internal only) |
| Grafana | 3000 | HTTP (internal only) |
| Node Exporter | 9100 | HTTP (internal only) |

Ansible group: `slm` | Ansible var: `infrastructure.hosts.slm`

---

### Backend (`backend`)

**Purpose:** Core AutoBot API — agents, workflows, knowledge, chat, terminal.

| Service | Port | Protocol |
| --- | --- | --- |
| FastAPI (nginx proxy) | 8443 | HTTPS |
| FastAPI (internal) | 8001 | HTTP |
| noVNC (VNC web UI) | 6080 | HTTPS |
| VNC raw | 5900 | TCP (internal only) |
| Syslog | 514 | TCP (internal only) |

Ansible group: `backend` | Ansible var: `infrastructure.hosts.backend`

---

### Frontend (`frontend`)

**Purpose:** Vue 3 web UI served via nginx.

| Service | Port | Protocol |
| --- | --- | --- |
| nginx (production build) | 443 / 80 | HTTPS / HTTP redirect |
| Vite dev server | 5173 | HTTP (dev only) |
| Node Exporter | 9100 | HTTP (internal only) |

Ansible group: `frontend` | Ansible var: `infrastructure.hosts.frontend`

---

### Database (`database`)

**Purpose:** Persistent data — Redis Stack, ChromaDB, model storage.

| Service | Port | Protocol |
| --- | --- | --- |
| Redis Stack | 6379 | TCP (internal only) |
| Redis Insight UI | 8001 | HTTP (internal only) |
| ChromaDB | 8100 | HTTP (internal only) |
| PostgreSQL | 5432 | TCP (internal only) |
| Node Exporter | 9100 | HTTP (internal only) |

Ansible group: `database` | Ansible var: `infrastructure.hosts.database`

---

### AI/ML (`aiml`)

**Purpose:** LLM inference and NPU acceleration — AI Stack + NPU Worker.

| Service | Port | Protocol |
| --- | --- | --- |
| AI Stack (LLM serving) | 8080 | HTTP (internal only) |
| NPU Worker | 8081 | HTTP (internal only) |
| Ollama | 11434 | HTTP (internal only) |
| Node Exporter | 9100 | HTTP (internal only) |

> **Note:** NPU Worker may run co-located with AI Stack on the same VM or on a
> dedicated Windows NPU host. The Ansible group is `npu_workers` when separate.

Ansible group: `aiml` | Ansible var: `infrastructure.hosts.aiml`
NPU subgroup: `npu_workers` | Ansible var: `infrastructure.hosts.npu`

---

### Browser (`browser`)

**Purpose:** Web automation — Playwright, VNC desktop, browser control agent.

| Service | Port | Protocol |
| --- | --- | --- |
| Browser Worker API | 3000 | HTTP (internal only) |
| Playwright debug | 3001 | HTTP (internal only) |
| noVNC web UI | 6080 | HTTPS |
| TigerVNC raw | 5901 | TCP (internal only) |
| Node Exporter | 9100 | HTTP (internal only) |

Ansible group: `browser` | Ansible var: `infrastructure.hosts.browser`

---

## Co-located Mode (Single Host)

When running on one machine, each role binds to a `127.0.0.x` loopback alias
so services can still address each other by a stable IP without network routing.

| Role | Loopback alias |
| --- | --- |
| Backend | `127.0.0.3` |
| Browser / Playwright | `127.0.0.4` |
| NPU Worker | `127.0.0.5` |
| AI Stack | `127.0.0.6` |
| Redis | `127.0.0.7` |

See [IP_ADDRESSING_SCHEME.md](../api/IP_ADDRESSING_SCHEME.md) for the full co-located
addressing rules including the no-localhost policy.

---

## Adding a New VM Role

1. Add a group to `autobot-slm-backend/ansible/inventory/hosts.yml`
2. Create `autobot-slm-backend/ansible/inventory/group_vars/<role>.yml`
3. Add `infrastructure.hosts.<role>` to `group_vars/infrastructure.yml`
4. Reference via `{{ infrastructure.hosts.<role> }}` in templates — never hardcode an IP

---

## Related

- [IP_ADDRESSING_SCHEME.md](../api/IP_ADDRESSING_SCHEME.md) — co-located loopback scheme
- [DISTRIBUTED_ARCHITECTURE.md](DISTRIBUTED_ARCHITECTURE.md) — full architecture overview
- [Ansible Inventory](../../autobot-slm-backend/ansible/inventory/) — live role definitions
- [AUTOBOT_REFERENCE.md](../developer/AUTOBOT_REFERENCE.md) — quick reference for IPs/ports
