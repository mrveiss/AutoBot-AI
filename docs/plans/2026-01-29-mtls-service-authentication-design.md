# mTLS Service Authentication Migration Design

**Issue:** #725
**Date:** 2026-01-29
**Status:** Approved for Implementation
**Author:** mrveiss

---

## Executive Summary

Migrate AutoBot from password-based service authentication to mutual TLS (mTLS) using the existing PKI infrastructure. This provides certificate-based authentication with per-service identity, audit trails, and forward secrecy.

---

## Architecture Overview

### Certificate Hierarchy

```
certs/
├── ca/
│   ├── ca-cert.pem          # Root CA (10-year validity)
│   └── ca-key.pem           # CA private key (secured, 600 permissions)
├── main-host/               # Backend + Celery client certs
├── frontend/                # Frontend server cert (optional)
├── npu-worker/              # NPU Worker server cert
├── redis/                   # Redis Stack server cert
├── ai-stack/                # AI Stack server cert
└── browser/                 # Browser service cert
```

### Key Design Decisions

1. **Single Internal CA** - All certificates signed by one CA for simplified management
2. **Per-Service Identity** - Each VM gets a unique Common Name for audit trails
3. **mTLS for Redis** - `tls-auth-clients yes` enforces client certificate verification
4. **Dual-Auth Transition** - Password authentication retained as fallback during migration
5. **No Docker** - All services run natively via systemd

---

## Per-VM Service Inventory

### VM0: SLM Server (172.16.168.19) - Separate Machine

| Service | Port | Protocol | Certificate |
|---------|------|----------|-------------|
| SLM Backend | 8000 | HTTP (behind nginx) | nginx TLS termination |

- **Redis Connection:** None (uses local SQLite)
- **Note:** TLS already handled by nginx reverse proxy

### Main Host (172.16.168.20) - WSL

| Service | Port | TLS Port | Certificate |
|---------|------|----------|-------------|
| Backend FastAPI | 8001 | 8443 | `main-host/` |
| Celery Worker | N/A | N/A | `main-host/` (Redis client) |
| VNC Proxy | 6080 | 6080 | Optional |

- **Redis Connection:** Client cert required
- **Ports to REMOVE:** 8000, 8090 (not used on main-host)

### VM1: Frontend (172.16.168.21)

| Service | Port | Certificate |
|---------|------|-------------|
| Vite Dev Server | 5173 | `frontend/` (optional) |

- **Redis Connection:** None

### VM2: NPU Worker (172.16.168.22)

| Service | Port | Certificate |
|---------|------|-------------|
| autobot-npu-worker | 8081 | `npu-worker/` |

- **Redis Connection:** None

### VM3: Redis Stack (172.16.168.23)

| Service | Port | TLS Port | Certificate |
|---------|------|----------|-------------|
| Redis Stack | 6379 (transition) | 6380 | `redis/` (server) |

- **Transition:** 6379 (password) → 6380 (mTLS) → disable 6379

### VM4: AI Stack (172.16.168.24)

| Service | Port | Certificate |
|---------|------|-------------|
| autobot-ai-stack | 8080 | `ai-stack/` |

- **Redis Connection:** Client cert required

### VM5: Browser Service (172.16.168.25)

| Service | Port | Certificate |
|---------|------|-------------|
| Playwright Service | 3000 | `browser/` |

- **Redis Connection:** None

---

## Dual-Auth Transition Strategy

**Critical:** Password authentication is retained as fallback until mTLS is fully validated.

```
PHASE A: Current State
├── port 6379 (password auth)
└── No TLS

PHASE B: TLS Added, Password RETAINED
├── port 6379 (password auth still works) ◄── FALLBACK
├── tls-port 6380 (TLS available)
├── tls-auth-clients optional
└── requirepass <password> ◄── KEPT AS SAFETY NET

PHASE C: Validate All Clients on TLS
├── Monitor: All connections using 6380?
├── Test: Backend connects via TLS ✓
├── Test: Celery connects via TLS ✓
├── Test: Health checks pass ✓
└── Password still active (can revert instantly)

PHASE D: Disable Password (ONLY after 100% TLS confirmed)
├── port 0 (plain port disabled)
├── tls-port 6380 (only TLS)
├── tls-auth-clients yes (mTLS enforced)
└── requirepass "" (password removed)
```

### Validation Gates

| Gate | Requirement | Rollback Action |
|------|-------------|-----------------|
| B→C | TLS port responds to ping | Stay on password auth |
| C→D | 0 connections on port 6379 for 24 hours | Keep dual-auth |
| C→D | All services health checks pass via TLS | Keep dual-auth |
| C→D | Manual operator confirmation | Keep dual-auth |

---

## Implementation Phases

### Phase 0: Cleanup (Pre-requisite)

Remove stale port references:

| Task | File | Action |
|------|------|--------|
| Remove port 8000 refs from main-host | `ansible/inventory/group_vars/all.yml` | Remove from firewall rules |
| Remove port 8090 refs | `ansible/inventory/group_vars/aiml.yml:363` | Remove `port: "8090:8099"` |
| Remove port range 8000-8099 | `ansible/inventory/group_vars/all.yml:118` | Remove `port: "8000:8099"` |
| Audit legacy main.py | `main.py` (root) | Deprecate or remove |
| Archive docker directory | `docker/` | Mark as deprecated |

### Phase 1: Certificate Generation & Distribution

1. Run `PKIManager.setup(force=True)`
2. Verify certs in `certs/` directory
3. Distribute to `/etc/autobot/certs/` on each VM
4. Verify permissions (600 for keys, 644 for certs)

### Phase 2: Redis Dual-Auth Configuration

1. Backup Redis config
2. Add TLS configuration (keep password active)
3. Open firewall for port 6380
4. Restart Redis
5. Test both TLS and password connections

### Phase 3: Backend mTLS Client

1. Set `AUTOBOT_REDIS_TLS_ENABLED=true`
2. Restart backend
3. Verify TLS connection in logs
4. Monitor for 24 hours

### Phase 4: Celery mTLS Client

1. Update `celery_app.py` with SSL context
2. Restart Celery worker
3. Submit test task
4. Verify task completion

### Phase 5: AI Stack mTLS Client

1. Update Redis connection to `rediss://`
2. Restart AI Stack service
3. Verify health endpoint

### Phase 6: Disable Password Auth (MANUAL GATE)

**Pre-requisites (ALL must pass):**
- [ ] Zero connections on port 6379 for 24 hours
- [ ] All services healthy via TLS
- [ ] Operator explicit approval

1. Verify no 6379 connections
2. Update Redis: `port 0`, `tls-auth-clients yes`, remove `requirepass`
3. Restart Redis
4. Verify 6379 is closed
5. Full health check

### Phase 7: HTTPS for HTTP APIs

1. Add SSL params to Backend uvicorn.run()
2. Add SSL params to NPU Worker
3. Add SSL params to AI Stack
4. Update frontend VITE_HTTP_PROTOCOL=https

### Phase 8: Ansible Automation

1. Update Redis role template with TLS config
2. Add cert distribution tasks
3. Update firewall rules for 6380
4. Update health check playbook

---

## Files to Modify

### New Files

| File | Purpose |
|------|---------|
| `src/pki/transition.py` | TLS transition state machine |
| `scripts/tls-transition.py` | CLI for managing transition phases |
| `/usr/local/bin/autobot-tls-rollback.sh` | Emergency rollback script |

### Modified Files

| File | Change |
|------|--------|
| `src/pki/configurator.py` | Add `TLSTransitionMode`, dual-auth config |
| `src/pki/config.py` | Add `transition_mode` field |
| `backend/main.py` | Add SSL to uvicorn.run() |
| `backend/celery_app.py` | Build `rediss://` URL with SSL context |
| `.env` | Add TLS environment variables |
| `ansible/roles/redis/templates/redis-stack.conf.j2` | Add TLS config block |
| `ansible/roles/redis/tasks/main.yml` | Add cert distribution, firewall |

### Environment Variables

```bash
# TLS Transition Control
AUTOBOT_TLS_TRANSITION_MODE=dual_auth  # disabled|dual_auth|tls_only

# Redis TLS
AUTOBOT_REDIS_TLS_ENABLED=true
AUTOBOT_REDIS_TLS_PORT=6380

# Backend TLS
AUTOBOT_BACKEND_TLS_ENABLED=true
AUTOBOT_BACKEND_TLS_PORT=8443

# Certificate Paths
AUTOBOT_TLS_CERT_DIR=certs
```

---

## Rollback Procedures

### Quick Rollback (< 60 seconds)

```bash
#!/bin/bash
# /usr/local/bin/autobot-tls-rollback.sh

set -e
echo "=== AutoBot TLS Emergency Rollback ==="

# 1. Restore Redis config
ssh autobot@172.16.168.23 "sudo cp /etc/redis-stack.conf.backup /etc/redis-stack.conf"
ssh autobot@172.16.168.23 "sudo systemctl restart redis-stack-server"

# 2. Disable TLS in backend
sed -i 's/AUTOBOT_REDIS_TLS_ENABLED=true/AUTOBOT_REDIS_TLS_ENABLED=false/' /home/kali/Desktop/AutoBot/.env

# 3. Restart services
systemctl restart autobot-backend
systemctl restart autobot-celery

# 4. Verify
sleep 5
curl -s http://localhost:8001/api/health | jq .

echo "=== Rollback Complete ==="
```

### Per-Phase Rollback

| Phase | Rollback Action |
|-------|-----------------|
| Phase 2 | Restore Redis config backup, restart |
| Phase 3 | Set `AUTOBOT_REDIS_TLS_ENABLED=false`, restart backend |
| Phase 4 | Revert `celery_app.py`, restart Celery |
| Phase 5 | Revert AI Stack Redis URL, restart |
| Phase 6 | Re-enable password auth in Redis config |

---

## Testing Checklist

### Pre-Deployment

- [ ] All certificates generated and valid
- [ ] Certificate expiry > 30 days
- [ ] TLS handshake test passes
- [ ] Redis TLS ping returns PONG

### Post-Deployment

- [ ] Redis accepts TLS connections on 6380
- [ ] Redis still accepts password auth on 6379 (dual-auth)
- [ ] Backend connects via TLS
- [ ] Celery tasks complete successfully
- [ ] AI Stack health endpoint responds
- [ ] No circuit breaker trips for 24 hours
- [ ] Zero connections on 6379 (before Phase 6)

### Final Validation

- [ ] Port 6379 is disabled
- [ ] All services use mTLS
- [ ] Health checks pass
- [ ] Monitoring alerts configured
- [ ] Rollback script tested

---

## Security Benefits

| Aspect | Password Auth | mTLS Auth |
|--------|---------------|-----------|
| Credential exposure | Password in .env, logs, memory | Private key never transmitted |
| Authentication strength | Single shared secret | Per-service cryptographic identity |
| Revocation | Must rotate everywhere | Revoke single certificate |
| Audit trail | IP-based only | Certificate CN identifies client |
| Forward secrecy | No | Yes (with proper cipher suites) |

---

## Related Issues

- Closes #725 (mTLS migration)
- Supersedes password-based Redis auth from #724