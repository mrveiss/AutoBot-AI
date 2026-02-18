# Runbook: System Package Update

**Issue #926 Phase 8** | Last updated: 2026-02-18

---

## Overview

This runbook describes how to apply OS package updates (`apt upgrade`) to fleet nodes. System updates are **independent** from code updates — they update Ubuntu packages, not AutoBot application code.

---

## Prerequisites

- SLM server (`.19`) is running and healthy
- SSH access from dev machine to target nodes
- `autobot-slm-backend/ansible/` is the working directory

---

## Quick Reference

```bash
# Check pending updates across all nodes
cd autobot-slm-backend/ansible
ansible-playbook playbooks/system-update.yml --tags check -i inventory/slm-nodes.yml

# Apply updates (respects per-node policy)
ansible-playbook playbooks/system-update.yml -i inventory/slm-nodes.yml

# Single node
ansible-playbook playbooks/system-update.yml \
  -i inventory/slm-nodes.yml \
  --limit 02-Frontend

# Force full update (override policy — emergency patching)
ansible-playbook playbooks/system-update.yml \
  -e "force_full=true" \
  -i inventory/slm-nodes.yml
```

---

## Update Policies

Each role declares its update policy in `autobot-infrastructure/autobot-<role>/manifest.yml`.

| Policy | Applies To | Packages Updated | Reboot Strategy |
|--------|-----------|-----------------|-----------------|
| `full` | `.21` (frontend), `.25` (browser), `.26`, `.27` | All packages | Immediate reboot if required |
| `security` | `.19` (SLM), `.20` (backend), `.22` (NPU), `.24` (AI stack) | Security packages only | Scheduled reboot (maintenance window) |
| `manual` | `.23` (database) | None — manual only | Manual with pre-approved downtime |

The `manual` policy means Ansible **will not** apply updates automatically. An operator must explicitly run with `--limit 04-Database` after scheduling downtime.

---

## Step-by-Step Procedure

### 1. Check Pending Updates

```bash
cd autobot-slm-backend/ansible
ansible-playbook playbooks/system-update.yml --tags check -i inventory/slm-nodes.yml
```

Output shows for each node:
- Number of pending updates
- Whether security updates are pending
- Whether a reboot is required (`/var/run/reboot-required`)

### 2. Review SLM Dashboard Alerts

Navigate to SLM → **System Updates** page.

Alerts are shown for:
- Nodes with pending security updates (critical)
- Nodes with pending full updates (warning)
- Nodes with reboot-required flag (warning)

### 3. Apply Updates

**Standard run (all eligible nodes, respects policy):**

```bash
ansible-playbook playbooks/system-update.yml -i inventory/slm-nodes.yml
```

**Security-only run (explicit):**

```bash
ansible-playbook playbooks/system-update.yml \
  -e "update_type=security" \
  -i inventory/slm-nodes.yml
```

**Database node (manual policy — schedule downtime first):**

```bash
# After scheduling downtime window
ansible-playbook playbooks/system-update.yml \
  -i inventory/slm-nodes.yml \
  --limit 04-Database \
  -e "force_full=true"

# Reboot if needed
ansible 04-Database -i inventory/slm-nodes.yml -m reboot --become
```

### 4. Handle Reboots

**`policy: full` nodes** (stateless, immediate reboot):

The playbook automatically reboots these nodes if `/var/run/reboot-required` exists, then waits for them to come back up.

**`policy: security` nodes** (stateful, scheduled reboot):

The playbook does NOT reboot automatically. Schedule reboot during a maintenance window:

```bash
# Check if reboot is needed
ansible slm_nodes -i inventory/slm-nodes.yml -m stat \
  -a "path=/var/run/reboot-required" \
  --become \
  | grep -v "stat": | grep "exists"

# Manual reboot (schedule one node at a time)
ansible 00-SLM-Manager -i inventory/slm-nodes.yml -m reboot --become
# → Wait for SLM to come back up before rebooting .20
ansible 01-Backend -i inventory/slm-nodes.yml -m reboot --become
# → Wait for backend to come back up (6 min startup)
```

**Backend `.20` reboot note:** The backend takes ~6 minutes to fully initialize after restart (loads GPUSemanticChunker, RAG optimizer, ChromaDB). Plan accordingly.

### 5. Verify

```bash
# Check no pending updates remain
ansible-playbook playbooks/system-update.yml --tags check -i inventory/slm-nodes.yml

# Check services are healthy
ssh autobot@172.16.168.19 "systemctl is-active autobot-slm-backend"
ssh autobot@172.16.168.19 'curl --insecure https://172.16.168.20:8443/api/health | jq .status'
```

---

## Kernel Updates

Kernel updates require a reboot to take effect. Use the same reboot procedure above, but note:

- Never reboot `.19` (SLM) and `.20` (backend) simultaneously
- Reboot `.23` (database/Redis) only during scheduled maintenance — all backends will lose Redis connection temporarily

After rebooting `.19`:
1. Wait for SLM health check: `curl -sk https://172.16.168.19/api/health`
2. Verify SLM agents reconnect: SLM GUI → Fleet Overview → all nodes reconnect within 60s

---

## Unattended Security Updates (Optional)

For nodes where `policy: security` is declared, unattended-upgrades can be enabled:

```bash
ansible-playbook playbooks/system-update.yml \
  --tags enable_unattended \
  -i inventory/slm-nodes.yml \
  --limit 00-SLM-Manager,01-Backend
```

This installs and configures `unattended-upgrades` for security-only packages. Full updates and reboots still require manual operator action.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `apt` lock error | Another apt process running | Wait or: `ssh autobot@<node> "sudo kill $(lsof /var/lib/dpkg/lock | awk 'NR>1{print $2}')"` |
| Node unreachable after reboot | Service failed to start | SSH to node, check `systemctl status autobot-<role>`, check logs |
| Backend 504 after reboot | Backend still initializing | Wait 6 min, then retry — check `/var/log/autobot/backend.log` |
| Redis clients disconnected | Redis restarted | Backends auto-reconnect; monitor for 60s |
| Package held back | `apt-mark hold` in place | Check: `apt-mark showhold`; unhold if safe |
| Reboot loop after kernel update | Faulty kernel | Boot to previous kernel from GRUB; report to team |

---

## Scheduling Maintenance Windows

For stateful nodes (`.19`, `.20`, `.22`, `.23`, `.24`), plan reboots around:

- **`.20` backend:** 6-minute startup time; avoid during peak chat usage
- **`.23` Redis:** Redis restart disconnects all clients for ~5 seconds; schedule at 02:00–04:00
- **`.19` SLM:** SLM restart disconnects all SLM agents for ~30 seconds; schedule during low-traffic period

Recommended maintenance window: **Tuesday 02:00–04:00** (weekly).

---

## Related

- `system-update.yml` — apt update playbook
- `docs/architecture/UPDATE_FLOWS.md` — update flow diagrams
- `docs/runbooks/CODE_UPDATE.md` — deploying application code (separate from OS updates)
- `docs/runbooks/EMERGENCY_RECOVERY.md` — if a node fails to come back after reboot
