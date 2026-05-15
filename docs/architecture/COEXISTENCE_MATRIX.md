# AutoBot Coexistence Matrix

> **Status:** Active — defined in Phase 2 of [#926](https://github.com/mrveiss/AutoBot-AI/issues/926)
> **Single source of truth:** `autobot-infrastructure/autobot-<role>/manifest.yml` (`coexistence` block)

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Compatible — can coexist on the same node |
| ❌ | Conflict — SLM prevents assignment (hard block) |
| ⚠️ | Warning — can coexist but requires attention (soft) |
| —  | Not applicable (role is deploy-to-all or same role) |

---

## Full Matrix

Rows and columns are the same role set. Read as: "Can **row role** and **column role** coexist on the same node?"

| | backend | frontend | slm-backend | slm-frontend | slm-database | monitoring | npu-worker | browser-worker | ai-stack | database | ollama | slm-agent | shared |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **backend** | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **frontend** | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **slm-backend** | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **slm-frontend** | ✅ | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **slm-database** | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **monitoring** | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | ⚠️ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **npu-worker** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **browser-worker** | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| **ai-stack** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ |
| **database** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | ✅ |
| **ollama** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ |
| **slm-agent** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| **shared** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |

---

## Notes on `autobot-frontend` ↔ `autobot-slm-frontend`

Both roles use nginx on port 443 — but nginx supports multiple `server_name` virtual hosts on the same port, each proxying to a different backend endpoint.

**When colocated on the same node**, a single nginx instance serves both:

```nginx
# autobot-frontend block
server {
    listen 443 ssl;
    server_name autobot.example.com;
    # ... proxy to autobot-backend at .20:8443
}

# autobot-slm-frontend block
server {
    listen 443 ssl;
    server_name slm.example.com;
    # ... proxy to autobot-slm-backend at localhost:8000
}
```

Each role's Ansible role renders its own `server` block into `/etc/nginx/sites-available/`. Both can be active simultaneously with no conflict.

**Default fleet layout** still keeps them on separate nodes (.21 and .19) for isolation, but there is no technical restriction.

---

## Warning Details

### ⚠️ `autobot-monitoring` ↔ `autobot-browser-worker`

**Reason:** Grafana binds port 3000. The browser-worker's Playwright-based service also defaults to port 3000.

**Resolution options:**
1. Assign to different nodes (default — monitoring to SLM .19, browser-worker to .25)
2. If colocating, configure Grafana to use port 3001 or browser-worker to use an alternate port
3. Update both manifests to reflect the chosen ports before SLM allows assignment

**Soft warning:** SLM displays a warning dialog but allows the operator to override if they confirm port changes.

---

## Default Node Assignments

The current fleet has dedicated nodes, making all conflicts irrelevant:

| Node | IP | Roles assigned |
|------|----|----------------|
| SLM | .19 | slm-backend, slm-frontend, slm-database, monitoring |
| Backend | .20 | backend, ollama |
| Frontend | .21 | frontend |
| NPU | .22 | npu-worker |
| Database | .23 | database |
| AI Stack | .24 | ai-stack |
| Browser | .25 | browser-worker |
| Reserved | .26 | (none) |
| Reserved | .27 | (none) |
| All nodes | — | slm-agent, shared |

---

## Port Map (Conflict Reference)

Ports that could conflict if roles share a node:

| Port | Protocol | Role | Binding |
|------|----------|------|---------|
| 80 | HTTP | frontend | all interfaces (redirect to 443) |
| 443 | HTTPS | frontend | all interfaces |
| 443 | HTTPS | slm-backend (nginx) | all interfaces |
| 3000 | HTTP | browser-worker | all interfaces |
| 3000 | HTTP | monitoring (grafana) | loopback |
| 5432 | TCP | slm-database | loopback |
| 5432 | TCP | database | loopback |
| 5555 | HTTP | backend (flower) | loopback |
| 6379 | TCP | database (redis) | all interfaces |
| 8000 | HTTP | slm-backend | loopback |
| 8001 | HTTP | database (redisinsight) | all interfaces |
| 8080 | HTTP | ai-stack | all interfaces |
| 8081 | HTTP | npu-worker | all interfaces |
| 8443 | HTTPS | backend | all interfaces |
| 9090 | HTTP | monitoring (prometheus) | loopback |
| 9100 | HTTP | slm-agent (node_exporter) | all interfaces |
| 11434 | HTTP | ollama | loopback |

---

## Adding New Roles

When adding a new role:

1. Choose a unique service port not in the table above
2. Add `coexistence.compatible_with`, `conflicts_with`, `warns_with` to its `manifest.yml`
3. Add the new role to the `compatible_with` list of any roles it coexists with
4. Update this matrix

Port conflicts are discovered at manifest load time — SLM cross-checks `manifest.ports` across all roles assigned to a node.

---

## Related Documents

- [ROLE_ARCHITECTURE.md](ROLE_ARCHITECTURE.md) — role definitions and manifest schema
- [NETWORK_TOPOLOGY.md](NETWORK_TOPOLOGY.md) — full port map and firewall rules
- `autobot-infrastructure/autobot-<role>/manifest.yml` — authoritative per-role coexistence block
