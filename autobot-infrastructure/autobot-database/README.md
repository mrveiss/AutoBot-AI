# autobot-database Infrastructure

> Role: `autobot-database` | Node: Database VM (.23 / 172.16.168.23) | Ansible role: `redis`

---

## Overview

Redis Stack + PostgreSQL data layer. Redis Stack serves fleet-wide session storage, caching, vector search (RediSearch), and pub/sub. PostgreSQL serves the user management database for `autobot-backend`.

System updates policy is **manual** — database nodes require planned maintenance windows to avoid data loss.

---

## Ports

| Port | Protocol | Public | Purpose |
|------|----------|--------|---------|
| 6379 | TCP | No (fleet-internal) | Redis Stack (all backend services) |
| 8001 | HTTP | No (fleet-internal) | RedisInsight web UI |
| 5432 | TCP | No (loopback only) | PostgreSQL (user management DB) |

---

## Services

| Unit | Type | Start Order |
|------|------|-------------|
| `autobot-database-redis` | systemd | 1 (redis-stack-server) |
| `autobot-database-postgres` | systemd | 2 (postgresql) |

---

## Health Check

```bash
redis-cli -h 172.16.168.23 -a "$REDIS_PASSWORD" ping
# Expected: PONG

ssh autobot@172.16.168.23 'pg_isready -U autobot_users'
# Expected: /var/run/postgresql:5432 - accepting connections
```

---

## Secrets

| Secret | File | Description |
|--------|------|-------------|
| `redis_password` | `/etc/autobot/database-secrets.env` | Redis AUTH password |
| `db_password` | `/etc/autobot/database-secrets.env` | PostgreSQL password for autobot_users |

---

## Redis Databases

| DB Index | Name | Purpose |
|----------|------|---------|
| 0 | main | Sessions, general cache |
| 1 | knowledge | Knowledge base indices |
| 2 | prompts | Prompt cache |
| 3 | analytics | Usage analytics, audit logs |

Always use the canonical client:
```python
from autobot_shared.redis_client import get_redis_client
client = get_redis_client(async_client=False, database="main")
```

---

## PostgreSQL Databases

| Database | Owner | Purpose |
|----------|-------|---------|
| `autobot_users` | `autobot_users` | User management (auth, teams, API keys) |

---

## Deployment

```bash
# Deploy database node
ansible-playbook playbooks/deploy-full.yml --tags redis,postgresql --limit database_vm

# IMPORTANT: Use 'manual' update policy — coordinate maintenance window before running
```

---

## Known Gotchas

- **System updates: manual** — Never auto-update the database node. Schedule a maintenance window, back up data, then update.
- **Redis Stack vs redis**: Install from `packages.redis.io` (Redis Stack includes RediSearch, RedisJSON, RedisTimeSeries). Standard `redis-server` from apt is NOT the same.
- **Redis binds all interfaces**: Required for fleet-wide access. Secured via AUTH password only — ensure UFW allows 6379 from fleet subnet only.
- **PostgreSQL loopback only**: Port 5432 is `loopback_only=true`. The main backend accesses it via the environment variable `DATABASE_URL=postgresql://...@172.16.168.23:5432/autobot_users` (exception: routed over VPN/VLAN, not public internet).
- **Backups**: Redis `BGSAVE` snapshots to `/opt/autobot/data/redis/`. PostgreSQL daily pg_dump to `/opt/autobot/data/postgres/backups/`.

---

## Ansible Role

Role: `redis` in `autobot-slm-backend/ansible/roles/redis/`

Key tasks:
- Add Redis Stack APT repo
- Install redis-stack-server + postgresql
- Configure redis.conf (bind, requirepass, maxmemory)
- Create PostgreSQL database + user
- Systemd unit aliases + start
