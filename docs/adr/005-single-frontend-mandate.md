# ADR-005: Single Frontend Server Mandate

## Status

**Status**: Accepted

## Date

**Date**: 2025-01-01

## Context

During development, multiple issues arose from running frontend servers on different machines:

1. **Port Conflicts**: Multiple Vite servers fighting for port 5173
2. **State Confusion**: Which server has the latest code?
3. **WebSocket Issues**: Connections to wrong server caused silent failures
4. **CORS Problems**: Cross-origin requests between different origins
5. **Cache Inconsistency**: Different HMR states on different servers

Developers would accidentally start frontend servers locally while the VM was also running, causing hours of debugging "phantom" issues.

## Decision

**Only VM1 (172.16.168.21:5173) may run the frontend server.**

This is an absolute mandate with zero exceptions:

| Machine | Frontend Server | Status |
|---------|-----------------|--------|
| Main (172.16.168.20) | **FORBIDDEN** | Never start Vite here |
| VM1 (172.16.168.21) | **REQUIRED** | Only frontend server |
| All other VMs | **FORBIDDEN** | No frontend capability |

### Development Workflow

1. **Edit locally** in `/home/kali/Desktop/AutoBot/autobot-vue/`
2. **Sync to VM1** using `./sync-frontend.sh` or sync scripts
3. **VM1 serves** the frontend (dev or production mode)
4. **Access** via `http://172.16.168.21:5173`

### Alternatives Considered

1. **Local Development with Proxy**
   - Pros: Familiar workflow, fast HMR
   - Cons: Port conflicts, state confusion, CORS issues

2. **Multiple Frontend Instances with Load Balancer**
   - Pros: Redundancy, scaling
   - Cons: Overkill, state sync complexity, unnecessary for single user

3. **Single Authoritative Server (Chosen)**
   - Pros: No conflicts, clear source of truth, simple debugging
   - Cons: Requires sync step, slightly slower iteration

## Consequences

### Positive

- **No Port Conflicts**: Single server, single port
- **Clear Source of Truth**: Always know which code is running
- **Simplified Debugging**: Only one place to check logs
- **Consistent State**: All users see same frontend
- **WebSocket Reliability**: Single endpoint for real-time features

### Negative

- **Sync Step Required**: Must sync changes before seeing them
- **Slight Latency**: Network round-trip to VM
- **VM Dependency**: Frontend unavailable if VM1 is down

### Neutral

- HMR still works on VM1, just triggers after sync
- Can use watch mode with auto-sync for smoother workflow

## Implementation Notes

### Key Files

- `sync-frontend.sh` - Quick sync script for frontend changes
- `scripts/utilities/sync-to-vm.sh` - General purpose VM sync utility
- `run_autobot.sh` - Orchestrates frontend startup on VM1

### Forbidden Commands

**NEVER run these on the main machine (172.16.168.20):**

```bash
# ALL FORBIDDEN - Will cause conflicts
npm run dev
yarn dev
vite
vite dev
vite preview
pnpm dev
```

### Correct Workflow

```bash
# 1. Edit code locally
vim autobot-vue/src/components/MyComponent.vue

# 2. Sync to VM1
./sync-frontend.sh
# OR
./scripts/utilities/sync-to-vm.sh frontend autobot-vue/ /home/autobot/autobot-vue/

# 3. Access in browser
firefox http://172.16.168.21:5173
```

### Enforcement

The `run_autobot.sh` script enforces this by:
1. Never starting Vite on main machine
2. SSH to VM1 to start/restart frontend
3. Health checking VM1's frontend server

### Pre-commit Hook (Optional)

```bash
#!/bin/bash
# .git/hooks/pre-commit

# Warn if Vite process running locally
if pgrep -f "vite" > /dev/null; then
    echo "WARNING: Vite is running locally. This violates ADR-005."
    echo "Only VM1 (172.16.168.21) should run the frontend."
    exit 1
fi
```

### Troubleshooting

**Symptom**: Changes not appearing in browser
**Solution**: Run sync script, then hard refresh (Ctrl+Shift+R)

**Symptom**: WebSocket connection failed
**Solution**: Ensure connecting to 172.16.168.21:5173, not localhost

**Symptom**: Port 5173 already in use on main machine
**Solution**: Kill local process: `pkill -f vite`

## Related ADRs

- [ADR-001](001-distributed-vm-architecture.md) - VM1 is dedicated frontend server

---

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
