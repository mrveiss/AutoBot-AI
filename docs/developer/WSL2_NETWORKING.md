# WSL2 Networking — Known Limitations

**TL;DR**: The backend at `172.16.168.20:8443` **cannot be reached from within .20 itself**.
Always test backend connectivity **from another VM** (e.g., .19 or .21).

---

## The Problem

When running `curl` or any TCP connection to `127.0.0.1:8443` or `172.16.168.20:8443`
from **within** the WSL2 host (172.16.168.20), you get immediate `ECONNREFUSED` even though
`ss -tlnp` shows the uvicorn socket in `LISTEN` state.

## Root Cause

WSL2 **mirrored networking** mode intercepts loopback traffic before it reaches the Linux
network stack. The kernel routing table reveals this:

```bash
$ ip route get 127.0.0.1
127.0.0.1 via 169.254.73.152 dev loopback0 table 127 src 127.0.0.1
```

Traffic to `127.0.0.1` is routed via `loopback0` — a Hyper-V virtual Ethernet adapter that
bridges to the **Windows host's loopback** — rather than through the standard Linux `lo`
interface where uvicorn actually listens.

Since Windows has no listener on port 8443, the connection is immediately refused.

The same applies to the machine's own external IP (`172.16.168.20`): WSL2's routing
intercepts the connection before it reaches the Linux socket.

## Evidence

| Check | Result |
|-------|--------|
| `ss -tlnp \| grep 8443` | `LISTEN 0 2048 0.0.0.0:8443` (socket exists) |
| `tcpdump -i lo port 8443` | **0 packets** (traffic bypasses lo) |
| `tcpdump -i any port 8443` | **0 packets** (goes through loopback0) |
| `ip route get 127.0.0.1` | Via `loopback0` → Windows host |
| `curl` from .19 → .20:8443 | TLS handshake + 200 OK |

## Impact

| Scenario | Status |
|----------|--------|
| Connect from within .20 (127.0.0.1 or 172.16.168.20) | ❌ Connection refused |
| Connect from .19, .21, or any other VM | ✅ Works normally |
| Frontend (.21) → Backend (.20) API calls | ✅ Works normally |
| Production use | ✅ Unaffected |

## Workaround — Test From Another VM

```bash
# Health check
ssh autobot@172.16.168.19 'curl --insecure https://172.16.168.20:8443/api/health'

# Authenticated endpoint
TOKEN=$(ssh autobot@172.16.168.19 'curl --insecure -s -X POST \
  https://172.16.168.20:8443/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\":\"admin\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)[\"token\"])"')

ssh autobot@172.16.168.19 "curl --insecure -s \
  https://172.16.168.20:8443/api/knowledge_base/categories/main \
  -H 'Authorization: Bearer $TOKEN'"
```

## Permanent Fix Options

### Option 1: Bind uvicorn to eth2 only (simplest)

Change the Ansible backend role to bind only to the eth2 interface:

```yaml
# autobot-slm-backend/ansible/roles/backend/defaults/main.yml
backend_host: "172.16.168.20"  # eth2 only, instead of 0.0.0.0
```

This makes local-loopback tests impossible but has no production impact since all
legitimate clients connect via 172.16.168.x.

### Option 2: nginx reverse proxy on .20

Add an nginx role for .20 that accepts connections on eth2 and proxies to uvicorn.
This requires a new Ansible role and increases operational complexity.

### Option 3: Disable WSL2 mirrored networking

Edit `C:\Users\<user>\.wslconfig` on the Windows host:

```ini
[wsl2]
networkingMode=nat
```

Requires WSL2 restart (`wsl --shutdown`). Changes the entire WSL2 network stack
and may affect other services.

### Recommended: No change needed

The backend is only accessed by other VMs in the fleet. WSL2 loopback is a developer
ergonomic issue, not a production problem. Use the workaround above when local testing
is needed.

## Background

Discovered during Issue #910 investigation (2026-02-17). WSL2 mirrored networking was
introduced in Windows 11 build 22621+ to share Windows network adapters with WSL2.
See Issue #914.
