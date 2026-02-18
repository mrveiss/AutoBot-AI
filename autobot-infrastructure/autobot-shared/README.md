# autobot-shared Infrastructure

> Role: `autobot-shared` | Node: **All backend nodes** | Ansible role: `common`

---

## Overview

Shared Python utilities library. Not a standalone service — deployed alongside every role that imports from `autobot_shared`. Provides Redis client, SSOT config, OpenTelemetry tracing, and structured logging.

---

## Key Modules

| Module | Import | Purpose |
|--------|--------|---------|
| `redis_client` | `from autobot_shared.redis_client import get_redis_client` | Canonical Redis client (ALWAYS use this) |
| `ssot_config` | `from autobot_shared.ssot_config import config` | Single source of truth for host/port config |
| `tracing` | `from autobot_shared.tracing import init_tracing, get_tracer` | OpenTelemetry distributed tracing |
| `logging_config` | `from autobot_shared.logging_config import setup_logging` | Structured JSON logging |

---

## Ports

None — library only, no services.

---

## Services

None.

---

## Health Check

Not applicable.

---

## Deployment

```bash
# Deployed with every backend role automatically
# Deploy shared explicitly
ansible-playbook playbooks/deploy-full.yml --tags common

# Manual sync
rsync -avz autobot-shared/ autobot@172.16.168.20:/opt/autobot/autobot-shared/
```

---

## Import Path

```python
# Correct import path (deployed to /opt/autobot/autobot-shared/)
from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_config import config

# Never hardcode IPs or ports — always use ssot_config
redis_host = config.redis.host   # Not: "172.16.168.23"
backend_url = config.backend.url # Not: "https://172.16.168.20:8443"
```

---

## WSL2 Symlink Note

At the repo root, `autobot_shared` is a symlink → `autobot-shared/` for WSL2 Python import compatibility. If git `core.symlinks=false`, this symlink is stored as a plain text file containing the target path.

After checkout:
```bash
rm autobot_shared && ln -s autobot-shared autobot_shared
```

---

## Known Gotchas

- **Redis client is canonical**: NEVER use `redis.Redis(host="172.16.168.23", ...)` directly. Always use `get_redis_client()`. Pre-commit hook enforces this.
- **aioredis compatibility**: Python 3.13 merged aioredis into redis. Use `from redis import asyncio as aioredis` or the compatibility shim at `<venv>/lib/python3.13/site-packages/aioredis.py`.
- **PYTHONPATH**: Deploying nodes must have `/opt/autobot` in `PYTHONPATH` so `import autobot_shared` resolves. Set in systemd unit `Environment=PYTHONPATH=/opt/autobot`.
- **No recursion**: `autobot-shared` manifest sets `deploy.shared: false` — it IS the shared component, not a consumer of it.

---

## Ansible Role

Role: `common` in `autobot-slm-backend/ansible/roles/common/`

Key tasks:
- Rsync `autobot-shared/` to `/opt/autobot/autobot-shared/`
- Ensure `PYTHONPATH=/opt/autobot` in each role's systemd unit
- No pip install needed (pure Python library)
