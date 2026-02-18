# AutoBot Network Topology

> **Status:** Active — defined in Phase 1-2 of [#926](https://github.com/mrveiss/AutoBot-AI/issues/926)
> **Subnet:** `172.16.168.0/24` (all fleet nodes)

---

## Node Map

| Node | IP | OS | Roles |
|------|----|----|-------|
| SLM Server | `172.16.168.19` | Ubuntu 22.04 | slm-backend, slm-frontend, slm-database, monitoring, slm-agent |
| Backend (WSL) | `172.16.168.20` | Kali Rolling | backend, ollama, slm-agent |
| Frontend VM | `172.16.168.21` | Ubuntu 22.04 | frontend, slm-agent |
| NPU VM | `172.16.168.22` | Ubuntu 22.04 | npu-worker, slm-agent |
| Database VM | `172.16.168.23` | Ubuntu 22.04 | database, slm-agent |
| AI Stack VM | `172.16.168.24` | Ubuntu 22.04 | ai-stack, slm-agent |
| Browser VM | `172.16.168.25` | Ubuntu 22.04 | browser-worker, slm-agent |
| Reserved (.26) | `172.16.168.26` | Ubuntu 22.04 | slm-agent |
| Reserved (.27) | `172.16.168.27` | Ubuntu 22.04 | slm-agent |
| Dev Machine | `172.16.168.20` ¹ | Kali Rolling (WSL2) | git, Ansible control |

¹ Dev machine is the WSL2 host at `.20`. Backend also runs here.

---

## Port Map (Per Node)

### `.19` — SLM Server

| Port | Protocol | Service | Public | Notes |
|------|----------|---------|--------|-------|
| 443 | HTTPS | nginx → slm-frontend | ✅ | SLM admin UI + API proxy |
| 80 | HTTP | nginx redirect | ✅ | Redirects to 443 |
| 8000 | HTTP | autobot-slm-backend | ❌ | Localhost only; nginx proxies to it |
| 5432 | TCP | PostgreSQL | ❌ | Localhost only; slm-backend connects |
| 9090 | HTTP | Prometheus | ❌ | Localhost only; nginx proxies `/prometheus/` |
| 3000 | HTTP | Grafana | ❌ | Localhost only; nginx proxies `/grafana/` |
| 22 | SSH | sshd | ✅ (fleet) | Fleet management |

### `.20` — Backend VM (WSL2)

| Port | Protocol | Service | Public | Notes |
|------|----------|---------|--------|-------|
| 8443 | HTTPS | autobot-backend (uvicorn) | ❌ | Accessed by nginx on `.21` |
| 11434 | HTTP | Ollama API | ❌ | Localhost only; backend connects |
| 6080 | HTTP | noVNC | ❌ | VNC over HTTP for GUI automation |
| 22 | SSH | sshd | ✅ (fleet) | Fleet management |

### `.21` — Frontend VM

| Port | Protocol | Service | Public | Notes |
|------|----------|---------|--------|-------|
| 443 | HTTPS | nginx → backend proxy | ✅ | User chat UI; proxies `/api/` → `.20:8443` |
| 80 | HTTP | nginx redirect | ✅ | Redirects to 443 |
| 22 | SSH | sshd | ✅ (fleet) | Fleet management |

### `.22` — NPU VM

| Port | Protocol | Service | Public | Notes |
|------|----------|---------|--------|-------|
| 8081 | HTTP | autobot-npu-worker | ❌ | Accessed by backend at `.20` |
| 22 | SSH | sshd | ✅ (fleet) | Fleet management |

### `.23` — Database VM

| Port | Protocol | Service | Public | Notes |
|------|----------|---------|--------|-------|
| 6379 | TCP | Redis Stack | ❌ | Accessed by all backends (.19, .20, .24, .25) |
| 22 | SSH | sshd | ✅ (fleet) | Fleet management |

### `.24` — AI Stack VM

| Port | Protocol | Service | Public | Notes |
|------|----------|---------|--------|-------|
| 8080 | HTTP | autobot-ai-stack | ❌ | Accessed by backend at `.20` |
| 22 | SSH | sshd | ✅ (fleet) | Fleet management |

### `.25` — Browser VM

| Port | Protocol | Service | Public | Notes |
|------|----------|---------|--------|-------|
| 3000 | HTTP | autobot-browser-worker (Playwright) | ❌ | Accessed by backend at `.20` |
| 22 | SSH | sshd | ✅ (fleet) | Fleet management |

---

## Traffic Flows

### User Request Path

```
Browser → .21:443 (nginx, HTTPS)
  └→ .20:8443 (autobot-backend, HTTPS)
       ├→ .23:6379 (Redis, TCP)          # session, cache, KB
       ├→ .24:8080 (ai-stack, HTTP)       # ChromaDB, embeddings
       ├→ .22:8081 (npu-worker, HTTP)     # NPU inference
       ├→ .25:3000 (browser-worker, HTTP) # Playwright automation
       └→ .20:11434 (Ollama, localhost)   # local LLM
```

### SLM Admin Path

```
Browser → .19:443 (nginx, HTTPS)
  └→ .19:8000 (autobot-slm-backend, localhost)
       ├→ .19:5432 (PostgreSQL, localhost)   # fleet state DB
       ├→ .23:6379 (Redis, TCP)              # node heartbeats, metrics
       ├→ .19:9090 (Prometheus, localhost)   # metrics scrape
       └→ Each node :22 (SSH)               # Ansible fleet ops
```

### SLM Agent Path (all nodes → .19)

```
Each node (slm-agent)
  └→ .19:443 (HTTPS, WebSocket)   # heartbeat, task results
```

### Monitoring Scrape Path

```
.19:9090 (Prometheus) → .20:8443/metrics
                      → .22:8081/metrics
                      → .24:8080/metrics
                      → .25:3000/metrics
                      → .23:6379 (redis_exporter)
```

---

## TLS Certificate Map

All inter-service HTTPS uses internal CA-signed certs issued by `setup-internal-ca.yml`.

| Node | Cert Path | Subject CN | Signed By |
|------|-----------|------------|-----------|
| `.19` | `/etc/autobot/certs/autobot-slm-backend.crt` | `172.16.168.19` | AutoBot Internal CA |
| `.20` | `/etc/autobot/certs/autobot-backend.crt` | `172.16.168.20` | AutoBot Internal CA |
| `.21` | `/etc/autobot/certs/autobot-frontend.crt` | `172.16.168.21` | AutoBot Internal CA |
| `.22` | `/etc/autobot/certs/autobot-npu-worker.crt` | `172.16.168.22` | AutoBot Internal CA |
| `.23` | `/etc/autobot/certs/autobot-database.crt` | `172.16.168.23` | AutoBot Internal CA |
| `.24` | `/etc/autobot/certs/autobot-ai-stack.crt` | `172.16.168.24` | AutoBot Internal CA |
| `.25` | `/etc/autobot/certs/autobot-browser-worker.crt` | `172.16.168.25` | AutoBot Internal CA |

CA root cert: `/etc/autobot/ca/ca-cert.pem` on `.19`.
All nodes receive the CA cert at `/etc/autobot/certs/ca-cert.pem`.

---

## Firewall Rules (UFW)

Rules are generated automatically from manifest `depends_on` + `ports`.

### `.19` — Allows inbound from:

| From | Port | Purpose |
|------|------|---------|
| all | 443 | HTTPS (SLM UI + API) |
| all | 22 | SSH |
| all nodes | 8000 | SLM agent callbacks (via nginx reverse proxy on 443) |

### `.20` — Allows inbound from:

| From | Port | Purpose |
|------|------|---------|
| `.21` | 8443 | Frontend nginx proxy |
| `.19` | 8443 | SLM health checks |
| all | 22 | SSH |

### `.21` — Allows inbound from:

| From | Port | Purpose |
|------|------|---------|
| all | 443 | HTTPS (user frontend) |
| all | 22 | SSH |

### `.22, .24, .25` — Allows inbound from:

| From | Port | Purpose |
|------|------|---------|
| `.20` | worker port | Backend calls |
| `.19` | worker port | SLM health checks |
| all | 22 | SSH |

### `.23` — Allows inbound from:

| From | Port | Purpose |
|------|------|---------|
| `.19` | 6379 | SLM backend Redis |
| `.20` | 6379 | Backend Redis |
| `.24` | 6379 | AI stack Redis |
| `.25` | 6379 | Browser worker Redis |
| all | 22 | SSH |

---

## DNS

No internal DNS server. All services use IP addresses directly via SSOT config.

Dev machine: `/etc/hosts` entries are optional — all Ansible inventory uses IPs.

---

## Related

- `docs/architecture/ROLE_ARCHITECTURE.md` — role definitions and boundaries
- `docs/architecture/COEXISTENCE_MATRIX.md` — which roles can coexist
- `autobot-infrastructure/autobot-<role>/manifest.yml` — per-role port declarations
- `autobot-slm-backend/ansible/playbooks/setup-internal-ca.yml` — CA + cert issuance
