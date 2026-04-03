---
tags:
  - api
  - networking
  - deployment
aliases:
  - IP Addressing
  - Network Configuration
---

# IP Addressing Scheme

AutoBot runs in two modes. The addressing rules differ per mode. **Never hardcode
a specific IP address** — always derive it from configuration or Ansible variables.

---

## Distributed Mode (Production — Multi-VM)

Each role runs on a dedicated VM. IPs are **assigned at install time** by `install.sh`,
which detects the network interface and writes them to `/etc/autobot/slm-secrets.env`.

All Ansible templates reference role variables, not literal IPs:

| Role | Ansible var | Services | Key ports |
| --- | --- | --- | --- |
| SLM Manager | `infrastructure.hosts.slm` | SLM API, nginx, Prometheus, Grafana | 443, 8000, 9090, 3000 |
| Backend | `infrastructure.hosts.backend` | FastAPI, noVNC | 8443, 8001, 6080 |
| Frontend | `infrastructure.hosts.frontend` | nginx, Vue build | 443 |
| Database | `infrastructure.hosts.database` | Redis, ChromaDB, PostgreSQL | 6379, 8100, 5432 |
| AI/ML | `infrastructure.hosts.aiml` | AI Stack, NPU Worker, Ollama | 8080, 8081, 11434 |
| Browser | `infrastructure.hosts.browser` | Playwright, VNC | 3000, 6080, 5901 |

> Full role descriptions, firewall rules, and service configs: [VM_ROLES.md](../architecture/VM_ROLES.md)

In Ansible templates use:

```jinja2
{{ infrastructure.hosts.backend }}:8443
{{ infrastructure.hosts.database }}:6379
```

In Python (runtime) use `autobot_shared.ssot_config`:

```python
from autobot_shared.ssot_config import config
backend_url = config.network.backend_url   # resolved at startup from env
```

In shell scripts use `ssot-config.sh`:
```bash
source /opt/autobot/infrastructure/shared/scripts/lib/ssot-config.sh
curl "https://${AUTOBOT_BACKEND_HOST}:8443/api/system/health"
```

---

## Co-located Mode (Single Host / Development)

All services run on one machine. Each service binds to a `127.0.0.x` loopback alias
so they can address each other by a stable IP without routing ambiguity.

> **Critical rule: never use `localhost` or `127.0.0.1`.** Use the specific alias below.

| Alias | Role | Key services | Example |
| --- | --- | --- | --- |
| `127.0.0.1` | **RESERVED** | System internal only | — |
| `127.0.0.2` | Windows host | Windows-side services | — |
| `127.0.0.3` | Backend | FastAPI, Ollama | `https://127.0.0.3:8443` |
| `127.0.0.4` | Browser / Playwright | VNC, browser automation | `http://127.0.0.4:6080` |
| `127.0.0.5` | NPU Worker | AI inference | `http://127.0.0.5:8081` |
| `127.0.0.6` | AI Stack | LLM serving | `http://127.0.0.6:8080` |
| `127.0.0.7` | Redis | Database | `redis://127.0.0.7:6379` |
| `127.0.0.8` | Log Viewer | Seq logging | `http://127.0.0.8:5341` |

### Why loopback aliases and not `localhost`?

- Eliminates routing ambiguity when Docker / WSL share the loopback stack
- Each service has a unique, grep-able address for debugging
- The same `ssot_config` values work in co-located and distributed mode — only
  the resolved IP changes, the code does not

### Setting up loopback aliases (co-located only)

```bash
# Add aliases (run once, or add to /etc/rc.local)
sudo ip addr add 127.0.0.3/8 dev lo
sudo ip addr add 127.0.0.4/8 dev lo
sudo ip addr add 127.0.0.5/8 dev lo
sudo ip addr add 127.0.0.6/8 dev lo
sudo ip addr add 127.0.0.7/8 dev lo
```

### Example configuration (co-located)

```javascript
// Vue ssot-config.ts — co-located values
BASE_URL: 'https://127.0.0.3:8443'
WS_BASE_URL: 'wss://127.0.0.3:8443/ws'
PLAYWRIGHT_VNC_URL: 'http://127.0.0.4:6080/vnc.html'
```

---

## Rules for All Modes

1. **No hardcoded IPs anywhere in code or docs.** Reference Ansible vars, ssot_config, or environment variables.
2. **No `localhost` / `127.0.0.1`.** Use role aliases in co-located mode, or `ssot_config` values in distributed mode.
3. **Document by role, not by IP.** When writing docs or error messages, say "backend VM" not "172.16.168.20".
4. **IPs in docs are examples only.** Any specific IP shown in documentation reflects one test deployment and is not canonical.

---

## Related

- [VM_ROLES.md](../architecture/VM_ROLES.md) — full role definitions, services, and ports
- [AUTOBOT_REFERENCE.md](../developer/AUTOBOT_REFERENCE.md) — quick reference
- [Ansible inventory](../../autobot-slm-backend/ansible/inventory/) — live host configuration
- [ssot_config](../../autobot-backend/autobot_shared/) — Python config access
