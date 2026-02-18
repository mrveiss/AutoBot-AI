# Runbook: Rotate SSH Keys

**Issue #926 Phase 7** | Last updated: 2026-02-18

---

## Overview

This runbook describes how to rotate SSH authorized keys across the AutoBot fleet using the
`rotate-ssh-keys.yml` Ansible playbook. The rotation uses a staged approach with a temporary
safety-net key to prevent lockout.

---

## Prerequisites

- Ansible control node (dev machine) has current SSH access to all fleet VMs
- `autobot-slm-backend/ansible/` is the working directory
- `~/.ssh/` contains: `autobot_ed25519` (current key) and `autobot_admin_temp_ed25519` (safety net)
- SLM server (.19) is reachable

---

## Key File Locations

| Key | Location | Purpose |
|-----|----------|---------|
| Primary deploy key | `~/.ssh/autobot_ed25519` | Normal Ansible SSH access |
| Safety-net key | `~/.ssh/autobot_admin_temp_ed25519` | Break-glass if primary is revoked |
| SLM backup (encrypted) | `/etc/autobot/keys/autobot_admin_temp.pub.enc` | Encrypted copy on SLM server |

---

## Quick Reference

```bash
cd autobot-slm-backend/ansible

# Check current key fingerprints across fleet
ansible-playbook playbooks/rotate-ssh-keys.yml --tags check

# Full rotation (K0–K6 with safety net)
ansible-playbook playbooks/rotate-ssh-keys.yml -i inventory/slm-nodes.yml
```

---

## Understanding the Rotation Phases

The playbook uses a safe, staged key rotation to prevent lockout:

```
K0  Generate new key pair (if needed)
K1  Add safety-net key to all nodes (authorized_keys)
K2  Verify safety-net key works (test connection)
K3  Add new primary key to all nodes
K4  Verify new primary key works
K5  Remove old primary key from all nodes
K6  Optionally remove safety-net key from all nodes
```

**If K2 (safety-net verification) fails** → playbook aborts; old key still works.
**If K4 (new key verification) fails** → playbook aborts; safety-net key is still present.

---

## Step-by-Step Procedure

### 1. Pre-flight: Check Current Key State

```bash
cd autobot-slm-backend/ansible
ansible-playbook playbooks/rotate-ssh-keys.yml --tags check
```

This shows the current authorized key fingerprints on each node. **No changes are made.**

### 2. Generate New Key Pair (if not already done)

```bash
ssh-keygen -t ed25519 -C "autobot-fleet-$(date +%Y%m%d)" -f ~/.ssh/autobot_ed25519_new -N ""
```

### 3. Run the Full Rotation

```bash
ansible-playbook playbooks/rotate-ssh-keys.yml -i inventory/slm-nodes.yml
```

Monitor for failures at each phase. If a phase fails, the playbook stops — previous phases
are not rolled back (they are safe to leave in place).

### 4. Verify New Key Works

```bash
# Test direct SSH with new key
ssh -i ~/.ssh/autobot_ed25519 autobot@172.16.168.19 "hostname"
ssh -i ~/.ssh/autobot_ed25519 autobot@172.16.168.20 "hostname"
ssh -i ~/.ssh/autobot_ed25519 autobot@172.16.168.21 "hostname"

# Test Ansible connectivity
ansible all -i inventory/slm-nodes.yml -m ping
```

### 5. Post-rotation Cleanup

After verifying the new key works:

```bash
# Move new key to primary location (backup old first)
mv ~/.ssh/autobot_ed25519 ~/.ssh/autobot_ed25519.bak.$(date +%Y%m%d)
mv ~/.ssh/autobot_ed25519_new ~/.ssh/autobot_ed25519

# Update SSH agent
ssh-add ~/.ssh/autobot_ed25519
```

---

## autobot_admin Safety Net

The `rotate-ssh-keys.yml` playbook always installs an `autobot_admin_temp` safety-net key
during rotation (K1 phase). This key:
- Is added to `authorized_keys` on ALL nodes BEFORE the old primary is removed
- Uses the key from `~/.ssh/autobot_admin_temp_ed25519`
- Is stored encrypted on the SLM server at `/etc/autobot/keys/autobot_admin_temp.pub.enc`
- Should be **removed after rotation is confirmed** (K6 phase or manually)

**Never delete the safety-net key before verifying the new primary key works (K4).**

---

## Rollback: If New Key Is Broken

If you've rotated to a broken key but the safety-net key is still present:

```bash
# SSH in with safety-net key
ssh -i ~/.ssh/autobot_admin_temp_ed25519 autobot@172.16.168.19

# Restore old key (from backup)
cat ~/.ssh/autobot_ed25519.bak >> ~/.ssh/authorized_keys

# Remove broken new key
# (identify fingerprint from: ssh-keygen -l -f ~/.ssh/autobot_ed25519_new.pub)
ssh-keygen -R 172.16.168.19
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Phase K2 fails | Safety-net key not generated | Run: `ssh-keygen -t ed25519 -f ~/.ssh/autobot_admin_temp_ed25519 -N ""` |
| `UNREACHABLE` at K4 | New key wrong or permissions | Check `~/.ssh/autobot_ed25519` is correct key |
| Only some nodes updated | Network partition | Re-run with `--limit <failed-node>` |
| `Permission denied (publickey)` | Key not in authorized_keys | Check via safety-net: `cat ~/.ssh/authorized_keys` on node |
| SLM shows key_mismatch | Key hash mismatch after rotation | Re-run K0–K4 for affected node |

---

## Related

- `rotate-certs.yml` — rotate TLS certificates across the fleet
- `setup-internal-ca.yml` — generate CA and issue CA-signed certs
- `docs/runbooks/EMERGENCY_RECOVERY.md` — break-glass procedures when all keys fail
- `deploy-service-auth.yml` — service-to-service authentication key rotation
